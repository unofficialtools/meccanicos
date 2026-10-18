"""mos-open's %f / %d filling, with a stand-in app that records what it got:
python3 -m unittest discover -s tests -p test_open.py"""
import json
import os
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "mos-open.sh")
# Writes its arguments, as JSON, to $FAKE_LOG.
APP = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_LOG"], "w") as fh:
    json.dump(sys.argv[1:], fh)
"""
NAMES = ["50%d.txt", "%f", "%d%f%%d", "a b.txt", "it's.txt", 'say "hi".txt', "back\\slash.txt", "$(touch PWNED);`id`&|<>*?.txt",
         "line\nbreak.txt", "-dash.txt"]


class Open(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.bin, self.log = os.path.join(t, "bin"), os.path.join(t, "log")
        self.dir = os.path.join(t, "my %d folder")
        os.makedirs(self.bin)
        os.makedirs(self.dir)
        with open(os.path.join(self.bin, "app"), "w") as fh:
            fh.write(APP)
        os.chmod(os.path.join(self.bin, "app"), 0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def open_with(self, template, name):
        path = os.path.join(self.dir, name)
        open(path, "w").close()
        env = {"PATH": self.bin + os.pathsep + os.environ["PATH"], "HOME": self.tmp.name, "FAKE_LOG": self.log,
               "MECCANICOS_OPEN_SYSTEM_CONF": os.path.join(self.tmp.name, "none")}
        r = subprocess.run(["bash", SCRIPT, "-W", "-a", template, "--", path], capture_output=True, text=True,
                           env=env, cwd=self.tmp.name)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.log) as fh:
            return path, json.load(fh)

    def test_file_and_folder_arrive_unchanged(self):
        for name in NAMES:
            with self.subTest(name=name):
                path, got = self.open_with("app --in %d --file %f", name)
                self.assertEqual(got, ["--in", self.dir, "--file", path])
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "PWNED")))

    def test_without_f_the_file_goes_at_the_end(self):
        for name in NAMES:
            with self.subTest(name=name):
                path, got = self.open_with("app %d", name)
                self.assertEqual(got, [self.dir, path])

    def test_f_twice(self):
        path, got = self.open_with("app %f %f", "50%d.txt")
        self.assertEqual(got, [path, path])


if __name__ == "__main__":
    unittest.main()
