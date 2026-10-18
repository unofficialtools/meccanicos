"""mos-dropbox sync without a VM, against stand-in rclone, systemctl, flock
and mountpoint: python3 -m unittest discover -s tests -p test_dropbox.py"""
import os
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "mos-dropbox.sh")
# Each says what it was asked; rclone bisync exits with $FAKE_BISYNC and
# systemctl with $FAKE_SYSTEMCTL (default 0).
FAKES = {
    "rclone": 'case "$1" in listremotes) echo dropbox: ;; bisync) exit "${FAKE_BISYNC:-0}" ;; esac',
    "systemctl": 'exit "${FAKE_SYSTEMCTL:-0}"',
    "flock": 'shift 2; exec "$@"',
    "mountpoint": "exit 1",
}


class Sync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.home, bin_, self.log = os.path.join(t, "home"), os.path.join(t, "bin"), os.path.join(t, "log")
        os.makedirs(self.home)
        os.makedirs(bin_)
        for name, body in FAKES.items():
            with open(os.path.join(bin_, name), "w") as f:
                f.write(f'#!/bin/sh\necho "{name} $*" >>"$FAKE_LOG"\n{body}\n')
            os.chmod(os.path.join(bin_, name), 0o755)
        self.state = os.path.join(self.home, ".config", "mos-dropbox")
        self.env = {"PATH": bin_ + os.pathsep + os.environ["PATH"], "HOME": self.home, "FAKE_LOG": self.log}

    def tearDown(self):
        self.tmp.cleanup()

    def run_(self, *args, **env):
        return subprocess.run(["bash", SCRIPT, *args], env=dict(self.env, **env),
                              capture_output=True, text=True, stdin=subprocess.DEVNULL)

    def read(self, name):
        try:
            with open(os.path.join(self.state, name)) as f:
                return f.read().strip()
        except FileNotFoundError:
            return None

    def bisyncs(self):
        with open(self.log) as f:
            return [l.split() for l in f if l.startswith("rclone bisync")]

    def test_custom_folder_is_used_by_the_timer(self):
        mine = os.path.join(self.home, "Work", "Box")
        p = self.run_("sync", MECCANICOS_DROPBOX_DIR=mine)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.read("folder"), mine)
        self.assertEqual(self.read("sync"), "on")
        self.assertEqual(self.read("resynced"), f"dropbox: {mine}")
        p = self.run_("tick")  # the timer: no MECCANICOS_DROPBOX_DIR
        self.assertEqual(p.returncode, 0, p.stderr)
        last = self.bisyncs()[-1]
        self.assertEqual(last[3], mine)
        self.assertNotIn("--resync", last)

    def test_another_folder_needs_resync(self):
        self.assertEqual(self.run_("sync").returncode, 0)
        other = os.path.join(self.home, "Other")
        p = self.run_("sync", MECCANICOS_DROPBOX_DIR=other)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("--resync", p.stderr)
        self.assertEqual(self.read("folder"), os.path.join(self.home, "Dropbox"))  # the timer's folder is unchanged
        p = self.run_("sync", "--resync", MECCANICOS_DROPBOX_DIR=other)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("--resync", self.bisyncs()[-1])
        self.assertEqual(self.read("folder"), other)

    def test_failed_first_sync_is_not_on(self):
        p = self.run_("sync", FAKE_BISYNC="1")
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("every 5 minutes", p.stdout)
        self.assertIsNone(self.read("sync"))
        self.assertIsNone(self.read("resynced"))
        with open(self.log) as f:
            self.assertNotIn("systemctl", f.read())

    def test_failed_timer_is_not_on(self):
        p = self.run_("sync", FAKE_SYSTEMCTL="1")
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("every 5 minutes", p.stdout)
        self.assertIn("could not enable", p.stderr)
        self.assertIsNone(self.read("sync"))

    def test_failed_resume_stays_paused(self):
        self.assertEqual(self.run_("sync").returncode, 0)
        self.assertEqual(self.run_("pause").returncode, 0)
        p = self.run_("resume", FAKE_SYSTEMCTL="1")
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(self.read("sync"), "paused")


if __name__ == "__main__":
    unittest.main()
