"""mos-fleet's agent and server without VMs: python3 -m unittest discover -s tests -p test_fleet.py
(the server's tests need pydal: they are skipped without it; tests/fleet.nix runs the rest)."""
import datetime
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

STATE = tempfile.mkdtemp(prefix="mos-fleet-test-")
os.environ["MOS_FLEET_STATE"] = STATE
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from mos_fleet import agent as ag  # noqa: E402
from mos_fleet.common import MAX_LINE, dumps, parse  # noqa: E402

try:
    import pydal  # noqa: F401
    from mos_fleet import server as sv
except ImportError:
    sv = None

SYSTEM = "/nix/store/" + "a" * 32 + "-nixos-system-ws1-26.05"


def new_agent():
    a = ag.Agent.__new__(ag.Agent)
    a.cfg = {"server": "hq", "interval": 300}
    a.proc, a.want, a.failed, a.pending, a.req = None, (SYSTEM, None), set(), {}, 0
    a.wlock, a.deploying, a.pw_lock = threading.Lock(), threading.Lock(), threading.Lock()
    a.cursor_sent, a.restart, a.was_refused = None, False, False
    a.sent = []
    a.try_send = lambda m: a.sent.append(m) or True
    a.send = a.try_send
    return a


def clean():
    for f in os.listdir(STATE):
        p = os.path.join(STATE, f)
        if os.path.isfile(p):
            os.remove(p)


class Deploy(unittest.TestCase):
    def deploy(self, code, running):
        a, ev, res = new_agent(), threading.Event(), []
        with patch.object(a, "fetch", create=True), patch.object(a, "switch", create=True, return_value=(code, "out")), \
                patch.object(ag, "current_system", return_value=SYSTEM if running else "/nix/store/old"), \
                patch.object(ag, "log"):
            a.deploy(force=True, done=lambda ok: (res.append(ok), ev.set()))
            ev.wait(5)
        return a, res[0], a.sent[-1]

    def test_failed_activation_is_a_failed_deployment(self):
        a, ok, msg = self.deploy(1, running=True)
        self.assertFalse(ok)
        self.assertEqual(msg["state"], "failed")
        self.assertIn("the new system is running, but switching failed", msg["output"])
        self.assertTrue(a.restart)  # its agent is the new system's

    def test_good_activation(self):
        _, ok, msg = self.deploy(0, running=True)
        self.assertTrue(ok)
        self.assertEqual(msg["state"], "ok")

    def test_link_not_changed(self):
        a, ok, _ = self.deploy(0, running=False)
        self.assertFalse(ok)
        self.assertFalse(a.restart)


class FakeJournal:
    def __init__(self, lines, code=0):
        self.stdout, self.returncode = iter(lines), code

    def kill(self):
        pass

    def wait(self):
        return self.returncode


class Logs(unittest.TestCase):
    def setUp(self):
        clean()

    def test_a_batch_fits_one_message(self):
        # 3000 entries of 4096 control characters: each escaped to 6 bytes.
        lines = [json.dumps({"__CURSOR": f"c{i}", "PRIORITY": "3", "MESSAGE": "\x01" * 4096,
                             "__REALTIME_TIMESTAMP": "1"}).encode() + b"\n" for i in range(3000)]
        a = new_agent()
        with patch.object(ag.subprocess, "Popen", return_value=FakeJournal(lines)):
            a.send_logs()
        m = a.sent[-1]
        self.assertLess(len((dumps(m) + "\n").encode()), MAX_LINE)
        parse((dumps(m)).encode())
        n = len(m["entries"])
        self.assertTrue(0 < n < 3000)
        self.assertEqual(m["cursor"], f"c{n - 1}")  # the next batch starts after the last one sent

    def test_a_cursor_the_journal_refuses_is_dropped(self):
        with open(ag.CURSOR, "w") as fh:
            fh.write("garbage")
        a = new_agent()
        with patch.object(ag.subprocess, "Popen", return_value=FakeJournal([], code=1)), patch.object(ag, "log"):
            a.send_logs()
        self.assertFalse(os.path.exists(ag.CURSOR))
        self.assertEqual(a.sent, [])

    def test_the_servers_cursor_is_adopted(self):
        new_agent().handle({"t": "logs-ok", "cursor": "s=1;i=2"})
        with open(ag.CURSOR) as fh:
            self.assertEqual(fh.read(), "s=1;i=2")


class Jobs(unittest.TestCase):
    def setUp(self):
        clean()

    def test_a_job_sent_again_runs_once(self):
        a, ran = new_agent(), []
        a.job = lambda m: ran.append(m["id"])
        for _ in range(2):
            a.handle({"t": "job", "id": 7, "kind": "run", "args": {"argv": ["true"]}})
        for t in threading.enumerate():
            if t is not threading.current_thread() and t.daemon:
                t.join(1)
        self.assertEqual(ran, [7])
        self.assertEqual([m for m in a.sent if m["t"] == "job-got"], [{"t": "job-got", "id": 7}] * 2)


class Passwords(unittest.TestCase):
    def test_a_failure_is_reported_and_retried(self):
        h = "$y$j9T$" + "a" * 22 + "$" + "b" * 43
        a = new_agent()
        with patch.object(ag.pwd, "getpwnam", return_value=SimpleNamespace(pw_uid=2001)), \
                patch.object(ag.subprocess, "run", return_value=SimpleNamespace(returncode=1, stderr="nope")), \
                patch.object(ag, "log_error") as err:
            self.assertEqual(a.apply_passwords({"lbianchi": h}), ["lbianchi"])
        self.assertIn("lbianchi", err.call_args.args[0])
        self.assertEqual(a.current_hashes(), {"lbianchi": h})  # kept: applied again later


class FakeSSH:
    """The server's end of a session: says one thing, then bye."""

    def __init__(self, *a, **k):
        self.stdin = io.BytesIO()
        self.stdout = iter([b'{"t":"desired"}\n', b'{"t":"bye","reason":"test"}\n'])
        self.stderr = iter([])

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0


class Enrollment(unittest.TestCase):
    def setUp(self):
        clean()

    def test_a_lost_answer_ends_when_the_session_gets_in(self):
        for f in (ag.ENROLL_KEY, ag.RECOVERY):
            open(f, "w").close()
        a = new_agent()
        del a.send, a.try_send
        with patch.object(ag.subprocess, "Popen", FakeSSH), patch.object(ag, "facts", return_value={}), \
                patch.object(ag, "log"):
            self.assertEqual(a.session(), "bye")
        self.assertTrue(os.path.exists(ag.ENROLLED))
        self.assertFalse(os.path.exists(ag.ENROLL_KEY) or os.path.exists(ag.RECOVERY))


class Io:
    def __init__(self):
        self.sent = []

    def send(self, m):
        self.sent.append(m)


@unittest.skipIf(sv is None, "needs pydal")
class Server(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="mos-fleet-server-")
        self.patches = [patch.object(sv, "STATE", self.dir), patch.object(sv, "main_rev", return_value="r"),
                        patch.object(sv, "main_repo", return_value=SimpleNamespace(hosts={"ws1": {}},
                                                                                   allowed=lambda h: set())),
                        patch.object(sv, "TRIGGER", os.path.join(self.dir, "build.trigger")),
                        patch.object(sv, "ROOTS", os.path.join(self.dir, "roots"))]
        for p in self.patches:
            p.start()
        self.db = sv.open_state(migrate=True)
        sv.open_secrets(migrate=True)
        self.db.host.insert(name="ws1", in_repo=True, branch="main")
        self.db.commit()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def session(self, version="3"):
        s = sv.HostSession("ws1")
        s.io = Io()
        s.handle({"t": "hello", "agent": version, "facts": {}})
        s.tick()
        return s

    def job(self):
        jid = self.db.job.insert(host="ws1", kind="run", args="{}", created_on=sv.now())
        self.db.commit()
        return jid

    def jobs_sent(self, s):
        return [m["id"] for m in s.io.sent if m["t"] == "job"]

    def test_a_job_not_acknowledged_is_sent_again(self):
        jid = self.job()
        self.assertEqual(self.jobs_sent(self.session()), [jid])
        s = self.session()  # the connection dropped before job-got
        self.assertEqual(self.jobs_sent(s), [jid])
        s.handle({"t": "job-got", "id": jid})
        self.assertEqual(self.jobs_sent(self.session()), [])
        self.db.commit()
        self.assertEqual(sv.job_state(self.db.job(jid)), "running")

    def test_old_agents_get_a_job_once(self):
        jid = self.job()
        self.assertEqual(self.jobs_sent(self.session("2")), [jid])
        self.assertEqual(self.jobs_sent(self.session("3")), [])

    def test_the_log_cursor_comes_first(self):
        self.db(self.db.host.name == "ws1").update(log_cursor="s=1")
        self.db.commit()
        self.assertIn({"t": "logs-ok", "cursor": "s=1"}, self.session().io.sent)

    def test_jobs_from_before_acknowledgments_are_not_sent_again(self):
        d = tempfile.mkdtemp(prefix="mos-fleet-old-")
        with patch.object(sv, "STATE", d):
            from pydal import Field
            old = sv._dal("state.db", True)
            old.define_table("job", Field("host"), Field("kind"), Field("delivered_on", "datetime"),
                             Field("finished_on", "datetime"))
            old.job.insert(host="ws1", kind="reboot", delivered_on=datetime.datetime(2026, 1, 1))
            old.commit()
            old.close()
            for f in os.listdir(d):  # as restored from a backup: only the database file
                if f.endswith(".table"):
                    os.remove(os.path.join(d, f))
            db = sv.open_state(migrate=True)
            self.assertEqual(db.job(1).received_on, datetime.datetime(2026, 1, 1))
            self.assertEqual(db(db.host.id > 0).count(), 0)  # a table it didn't have: created

    def test_a_restored_database_is_adopted(self):
        d = tempfile.mkdtemp(prefix="mos-fleet-restored-")
        self.db.executesql("PRAGMA wal_checkpoint(TRUNCATE)")  # as SQLite's backup does
        shutil.copy(os.path.join(self.dir, "state.db"), d)
        with patch.object(sv, "STATE", d):
            db = sv.open_state(migrate=True)  # no pydal records next to it: not created again
            self.assertEqual(db.host(name="ws1").branch, "main")
            db.job.insert(host="ws1", kind="facts", created_on=sv.now())
            db.commit()
            sv.open_state(migrate=True)  # and again, now with them

    def test_a_failed_switch_shows(self):
        row = SimpleNamespace(name="ws1", in_repo=True, desired_system=SYSTEM, current_system=SYSTEM,
                              desired_rev="r", branch="main")
        failed = SimpleNamespace(to_system=SYSTEM, result="failed")
        self.assertIn("switch failed", sv.host_state(row, None, True, failed))
        self.assertEqual(sv.host_state(row, None, True, None), "up to date")

    def test_build_retry(self):
        rev, built = "f" * 40, []

        def nix(cmd, **k):
            built.append(cmd)
            return SimpleNamespace(returncode=1, stdout="", stderr="network down")

        repo = SimpleNamespace(hosts={"ws1": {"branch": "main"}})
        with patch.object(sv, "refresh", return_value=repo), patch.object(sv, "heads", return_value={"main": rev}), \
                patch.object(sv.subprocess, "run", nix), patch.object(sv, "warn"), patch.object(sv, "say"):
            sv.build_once()
            sv.build_once()  # failed: not again by itself
            self.assertEqual(len(built), 1)
            admin = sv.Admin("admin", "mrossi")
            admin.cmd_build_retry(SimpleNamespace(hosts=["ws1"]))
            sv.build_once()
            self.assertEqual(len(built), 2)
            db = sv.open_state()
            self.assertEqual(db(db.build.host == "ws1").count(), 2)  # the retry used the row it asked for
            db(db.build.id > 0).update(ok=True)
            db.commit()
            with self.assertRaises(sv.Fail):  # only a failed build is retried
                admin.cmd_build_retry(SimpleNamespace(hosts=["ws1"]))


if __name__ == "__main__":
    unittest.main()
