"""mos-backup without a VM, against a stand-in restic:
python3 -m unittest discover -s tests -p test_backup.py"""
import os
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "mos-backup.sh")
# Exits with $FAKE_<COMMAND> (default 0), and says what it was asked.
RESTIC = """#!/bin/sh
echo "restic $*" >>"$FAKE_LOG"
var=FAKE_$(echo "$1" | tr a-z A-Z)
eval "code=\\${$var:-0}"
exit "$code"
"""


class Backup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.home, self.bin, self.log = os.path.join(t, "home"), os.path.join(t, "bin"), os.path.join(t, "log")
        os.makedirs(self.bin)
        os.makedirs(self.home)
        with open(os.path.join(self.bin, "restic"), "w") as fh:
            fh.write(RESTIC)
        os.chmod(os.path.join(self.bin, "restic"), 0o755)
        self.conf = os.path.join(self.home, ".config", "meccanicos")

    def tearDown(self):
        self.tmp.cleanup()

    def run_(self, *args, stdin="", **fake):
        env = {"HOME": self.home, "USER": "tester", "PATH": self.bin + os.pathsep + os.environ["PATH"], "FAKE_LOG": self.log,
               "XDG_RUNTIME_DIR": self.tmp.name, **{f"FAKE_{k.upper()}": str(v) for k, v in fake.items()}}
        env.pop("DISPLAY", None)
        return subprocess.run(["bash", SCRIPT, *args], input=stdin, capture_output=True, text=True, env=env)

    def read(self, name):
        with open(os.path.join(self.conf, name)) as fh:
            return fh.read()

    def init(self, dest, password, **fake):
        return self.run_("init", dest, stdin=f"{password}\n{password}\n", **fake)

    def test_a_failed_init_keeps_the_old_settings(self):
        old = os.path.join(self.tmp.name, "old")
        self.assertEqual(self.init(old, "old-password-1", cat=1).returncode, 0)
        env, pw = self.read("backup.env"), self.read("backup.pass")
        r = self.init(os.path.join(self.tmp.name, "new"), "new-password-2", cat=1, init=1)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Nothing changed", r.stderr)
        self.assertEqual((self.read("backup.env"), self.read("backup.pass")), (env, pw))
        self.assertEqual([f for f in os.listdir(self.conf) if f.startswith(".backup")], [])  # no leftovers

    def test_a_wrong_password_for_a_backup_already_there(self):
        dest = os.path.join(self.tmp.name, "d")
        self.assertEqual(self.init(dest, "right-password-1", cat=1).returncode, 0)
        pw = self.read("backup.pass")
        repo = self.read("backup.env").split("=", 1)[1].strip()
        os.makedirs(repo, exist_ok=True)
        open(os.path.join(repo, "config"), "w").close()
        r = self.init(dest, "wrong-password-2", cat=1)
        self.assertIn("doesn't open it", r.stderr)
        self.assertEqual(self.read("backup.pass"), pw)
        self.assertEqual(oct(os.stat(os.path.join(self.conf, "backup.pass")).st_mode & 0o777), "0o600")

    def test_an_incomplete_backup_says_so(self):
        dest = os.path.join(self.tmp.name, "d")
        self.init(dest, "a-password-1", cat=1)
        r = self.run_("now", backup=3)
        self.assertEqual(r.returncode, 5)
        self.assertIn("INCOMPLETE", r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.conf, "backup.incomplete")))
        self.assertEqual(self.run_("now").returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.conf, "backup.incomplete")))

    def test_restores_never_share_a_folder(self):
        self.init(os.path.join(self.tmp.name, "d"), "a-password-1", cat=1)
        for _ in range(2):
            self.assertEqual(self.run_("restore", "latest").returncode, 0)
        made = sorted(f for f in os.listdir(self.home) if f.startswith("Restored-"))
        self.assertEqual(len(made), 2)
        self.assertTrue(made[1].endswith("-2"), made)
        full = os.path.join(self.home, made[0])
        open(os.path.join(full, "x"), "w").close()
        r = self.run_("restore", "latest", full)
        self.assertEqual(r.returncode, 2)
        self.assertIn("already has files", r.stderr)


if __name__ == "__main__":
    unittest.main()
