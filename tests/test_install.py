"""mos-install's checks without a VM: python3 -m unittest discover -s tests -p test_install.py"""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
os.environ["MECCANICOS_INSTALL_TEST"] = "1"
spec = importlib.util.spec_from_file_location("mos_install", os.path.join(ROOT, "scripts", "mos-install.py"))
mi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mi)

DISKS = [("HARD DRIVE (/dev/vda)  51.5 GB  disk", "/dev/vda", 51539607552, "")]
GOOD = {"fullname": "Test User", "username": "tester", "password": "user-pass-1", "hostname": "testbox",
        "luks_password": "luks-test-pass-sixteen", "disk": "/dev/vda", "wifi": "", "wifi_security": "",
        "wifi_password": ""}


def fake_run(outputs):
    """subprocess.run answering by the command's first two words."""
    def run(cmd, **k):
        return SimpleNamespace(stdout=outputs.get(" ".join(cmd[:2]), ""), returncode=0)
    return run


class BootDisk(unittest.TestCase):
    def test_ventoy_is_followed_to_the_disk(self):
        out = {"findmnt -n": "/dev/mapper/ventoy\n",
               "lsblk -nspo": "/dev/mapper/ventoy dm\n/dev/sda1  part\n/dev/sda   disk\n"}
        with patch.object(mi.subprocess, "run", fake_run(out)):
            self.assertEqual(mi.boot_disk(), "/dev/sda")

    def test_a_plain_stick(self):
        out = {"findmnt -n": "/dev/sdb1\n", "lsblk -nspo": "/dev/sdb1 part\n/dev/sdb  disk\n"}
        with patch.object(mi.subprocess, "run", fake_run(out)):
            self.assertEqual(mi.boot_disk(), "/dev/sdb")


class Config(unittest.TestCase):
    def main(self, answers, stdin="yes\n"):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(answers, fh)
        out = io.StringIO()
        with patch.object(sys, "argv", ["mos-install", "--config", fh.name]), \
                patch.object(sys, "stdin", io.StringIO(stdin)), patch.object(mi, "list_disks", return_value=DISKS), \
                patch.object(mi, "install") as install, contextlib.redirect_stdout(out):
            code = mi.main()
        os.unlink(fh.name)
        return code, install.called, out.getvalue()

    def test_good_answers_install(self):
        code, installed, _ = self.main(GOOD)
        self.assertEqual((code, installed), (0, True))

    def test_answers_are_checked_like_the_form(self):
        for bad in ({"username": "Bad Name"}, {"password": ""}, {"luks_password": "x"}, {"username": "x; rm -rf /"}):
            with self.subTest(bad=bad):
                code, installed, _ = self.main({**GOOD, **bad})
                self.assertEqual((code, installed), (1, False))

    def test_only_a_disk_that_may_be_erased(self):
        code, installed, out = self.main({**GOOD, "disk": "/dev/sda"})
        self.assertEqual((code, installed), (1, False))
        self.assertIn("can't be erased", out)
        self.assertIn("/dev/vda", out)

    def test_not_text(self):
        code, installed, _ = self.main({**GOOD, "password": 12345678})
        self.assertEqual((code, installed), (1, False))


class Erase(unittest.TestCase):
    def test_the_disk_is_checked_again_before_erasing(self):
        with patch.object(mi, "list_disks", return_value=[]), patch.object(mi, "run") as run:
            with self.assertRaises(RuntimeError) as e:
                mi.partition_disk("/dev/vda")
        self.assertIn("Nothing was erased", str(e.exception))
        run.assert_not_called()

    def test_the_username_is_quoted(self):
        cmds = []
        with patch.object(mi, "enter", side_effect=lambda c, input=None: cmds.append(c)), \
                contextlib.redirect_stdout(io.StringIO()):
            mi.create_user({**GOOD, "username": "a'b"})
        self.assertIn("'a'\"'\"'b'", cmds[0])


class Preflight(unittest.TestCase):
    def bundle(self, method):
        return {"server": "hq", "server_host_key": "ssh-ed25519 AAAA", "unlock": {"method": method}}

    def test_the_stick_must_take_the_recovery_key(self):
        with tempfile.TemporaryDirectory() as d:
            os.chmod(d, 0o500)
            try:
                if os.access(d, os.W_OK):
                    self.skipTest("running as root")
                with self.assertRaises(RuntimeError) as e, contextlib.redirect_stdout(io.StringIO()):
                    mi.preflight(self.bundle("fido2"), d)
                self.assertIn("Nothing was erased", str(e.exception))
            finally:
                os.chmod(d, 0o700)

    def test_tpm_needed_for_the_pin(self):
        with tempfile.TemporaryDirectory() as d, patch.object(mi, "TEST", False), \
                patch.object(mi.shutil, "which", return_value="/bin/x"), \
                patch.object(mi.os.path, "exists", return_value=False):
            with self.assertRaises(RuntimeError) as e:
                mi.preflight(self.bundle("tpm-pin"), d)
        self.assertIn("TPM", str(e.exception))


if __name__ == "__main__":
    unittest.main()
