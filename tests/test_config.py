"""mos-config without a VM: python3 -m unittest discover -s tests -p test_config.py"""
import contextlib
import io
import os
import stat
import sys
import tarfile
import tempfile
import tomllib
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "mos"))
import common as c
import config as cfg


def write(folder, name, text):
    path = os.path.join(folder, name)
    with open(path, "w") as f:
        f.write(text)
    return path


class Values(unittest.TestCase):
    def test_ports(self):
        self.assertEqual(cfg.ports("8443, 8080"), [8080, 8443])
        self.assertEqual(cfg.ports("none"), [])
        for bad in ("-1", "0", "65536", "http"):
            with self.subTest(bad=bad), self.assertRaises(c.UsageError):
                cfg.ports(bad)

    def test_time_zone_is_not_a_path(self):
        for bad in ("/etc/passwd", "../../etc/passwd", "Europe/../../etc/passwd"):
            with self.subTest(bad=bad), self.assertRaises(c.UsageError):
                cfg.zone_choice(bad)

    def test_suspend_checked_before_anything_changes(self):
        self.assertEqual(cfg.BY_KEY["power.suspend"].parse("never"), 0)
        with self.assertRaises(c.UsageError):
            cfg.BY_KEY["power.suspend"].parse("5")

    def test_toml_round_trip(self):
        data = {"a": {"s": 'quote " back \\ tab \t new\nline ünï', "n": 3, "b": False, "l": [1, 2]}}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.toml")
            cfg.write_toml(path, data, "# header")
            self.assertEqual(cfg.read_toml(path), data)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o644)
            self.assertEqual(os.listdir(tmp), ["x.toml"])

    def test_audio_needs_one_match(self):
        found = {41: "Speakers", 42: "USB Speakers", 43: "Headset"}
        with patch.object(cfg, "nodes", return_value=found), patch.object(c, "run") as run:
            cfg.set_audio("Sinks", "speakers")  # exact name wins
            self.assertEqual(run.call_args.args[-1], 41)
            with self.assertRaises(c.UsageError):
                cfg.set_audio("Sinks", "speak")

    def test_vpn_by_uuid(self):
        rows = [["work", "u1", "vpn"], ["home", "u2", "wireguard"], ["home", "u3", "vpn"]]
        with patch.object(cfg, "nm_rows", return_value=rows):
            self.assertEqual(cfg.vpn_uuid("work"), "u1")
            with self.assertRaises(c.UsageError):
                cfg.vpn_uuid("home")


class Import(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.set = []
        ssh, lid = cfg.BY_KEY["security.ssh"], cfg.BY_KEY["power.lid"]
        self.stack = contextlib.ExitStack()
        for p in (patch.object(c, "installed", return_value=True),
                  patch.object(cfg, "remember"), patch.object(cfg, "rebuild"), patch.object(c, "log"),
                  patch.object(ssh, "_get", return_value=True), patch.object(lid, "_get", return_value="suspend"),
                  patch.object(ssh, "_set", side_effect=lambda v: self.set.append(("ssh", v))),
                  patch.object(lid, "_set", side_effect=lambda v: self.set.append(("lid", v))),
                  patch.object(sys.stdin, "isatty", return_value=False),
                  contextlib.redirect_stderr(io.StringIO())):
            self.stack.enter_context(p)

    def tearDown(self):
        self.stack.close()
        self.tmp.cleanup()

    def run_import(self, text, *flags):
        cfg.cmd_import([write(self.tmp.name, "s.toml", text), *flags])

    def test_text_is_checked_like_set(self):
        self.run_import('[security]\nssh = "off"\n', "--yes")
        self.assertEqual(self.set, [("ssh", False)])  # a bool for settings.nix, not "off"

    def test_wrong_and_unknown_values_left_out(self):
        with self.assertRaises(c.Failed):
            self.run_import('[security]\nssh = false\nwhatever = 1\n[power]\nlid = "sleep"\n', "--yes")
        self.assertEqual(self.set, [("ssh", False)])

    def test_a_failure_is_exit_code_1(self):
        with patch.object(cfg.BY_KEY["security.ssh"], "_set", side_effect=c.Failed("no")):
            with self.assertRaises(c.Failed):
                self.run_import("[security]\nssh = false\n", "--yes")

    def test_without_a_terminal_only_with_yes(self):
        with self.assertRaises(c.Failed):
            self.run_import("[security]\nssh = false\n")
        self.assertEqual(self.set, [])


class Dotfiles(unittest.TestCase):
    def test_secrets_never_unencrypted(self):
        """age gets the archive on its stdin: none is written unencrypted, even in an odd folder."""
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as bin_:
            write(home, ".bashrc", "alias x=y\n")
            os.makedirs(os.path.join(home, ".ssh"))
            write(home, ".ssh/id_ed25519", "KEY\n")
            folder = os.path.join(home, "it's $(here)")
            os.makedirs(folder)
            fake = write(bin_, "age", '#!/bin/sh\n[ "$1" = -p ] && [ "$2" = -o ] && exec cat > "$3"\nexit 1\n')
            os.chmod(fake, 0o755)
            with patch.object(c, "HOME", home), patch.dict(os.environ, {"PATH": bin_ + os.pathsep + os.environ["PATH"]}), \
                    contextlib.redirect_stderr(io.StringIO()):
                cfg.export_dotfiles(folder, [".bashrc"], True)
            self.assertEqual(os.listdir(folder), ["dotfiles.tar.gz.age"])
            with tarfile.open(os.path.join(folder, "dotfiles.tar.gz.age")) as tar:  # the fake age doesn't encrypt
                self.assertEqual(sorted(tar.getnames()), [".bashrc", ".ssh/id_ed25519"])


if __name__ == "__main__":
    unittest.main()
