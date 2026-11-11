"""mos-config without a VM: python3 -m unittest discover -s tests -p test_config.py"""
import contextlib
import io
import os
import shutil
import stat
import sys
import tarfile
import tempfile
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
    def test_port_rules(self):
        self.assertEqual(cfg.port_rules("8443/udp, 22 8443/TCP 5353/udp"), ["22/tcp", "5353/udp", "8443/tcp+udp"])
        self.assertEqual(cfg.port_rules("60000/both"), ["60000/tcp+udp"])
        self.assertEqual(cfg.port_rules("none"), [])
        for bad in ("-1", "0", "65536", "http", "80/sctp", "80/"):
            with self.subTest(bad=bad), self.assertRaises(c.UsageError):
                cfg.port_rules(bad)
        rules = ["22/tcp", "5353/udp", "8080/tcp+udp"]
        self.assertEqual(cfg.split_rules(rules), ([22, 8080], [5353, 8080]))
        self.assertEqual(cfg.join_rules(*cfg.split_rules(rules)), rules)
        self.assertEqual(cfg.port_rules(cfg.show(rules)), rules)  # what import reads back


class Firewall(unittest.TestCase):
    """security.firewall and its ports, in a fake /etc/nixos/meccanicos.toml."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.toml = os.path.join(self.tmp.name, "meccanicos.toml")
        self.stack = contextlib.ExitStack()
        for p in (patch.object(c, "SYSTEM_TOML", self.toml),
                  patch.object(cfg, "FIREWALL_DEFAULTS", os.path.join(self.tmp.name, "firewall.json")),
                  patch.object(c, "run", side_effect=self.fake_run), contextlib.redirect_stderr(io.StringIO())):
            self.stack.enter_context(p)

    def tearDown(self):
        self.stack.close()
        self.tmp.cleanup()

    def fake_run(self, *cmd, **kw):  # install -m 644 TMP DEST, without sudo
        assert cmd[:3] == ("install", "-m", "644"), cmd
        shutil.copy(cmd[3], cmd[4])
        return 0, ""

    def system(self, text):
        write(self.tmp.name, "meccanicos.toml", text)

    def test_managed_by_default_with_the_systems_ports(self):
        write(self.tmp.name, "firewall.json", '{"tcp": [22], "udp": [5353]}')
        self.assertEqual(cfg.BY_KEY["security.firewall"].get(), "managed")
        self.assertEqual(cfg.get_firewall_ports(), ["22/tcp", "5353/udp"])

    def test_managing_starts_from_what_is_open_now(self):
        write(self.tmp.name, "firewall.json", '{"tcp": [22], "udp": [5353]}')
        self.system("tcp_ports = [8080]\n")  # added by an older mos-config
        cfg.set_firewall("managed")
        self.assertEqual(cfg.system_toml(), {"tcp_ports": [22, 8080], "udp_ports": [5353], "firewall": "managed"})
        self.assertEqual(cfg.get_firewall_ports(), ["22/tcp", "5353/udp", "8080/tcp"])

    def test_not_managed_and_back_keeps_your_ports(self):
        self.system('firewall = "not-managed"\ntcp_ports = [443]\nudp_ports = []\n')
        cfg.set_firewall("managed")
        self.assertEqual(cfg.system_toml(), {"firewall": "managed", "tcp_ports": [443], "udp_ports": []})
        cfg.set_firewall("not-managed")
        self.assertEqual(cfg.system_toml()["tcp_ports"], [443])  # kept, unused while not managed
        for bad in ("on", "off", "true"):
            with self.subTest(bad=bad), self.assertRaises(c.UsageError):
                cfg.BY_KEY["security.firewall"].parse(bad)

    def test_ports_are_stored_as_two_lists(self):
        cfg.BY_KEY["security.firewall_ports"]._set(cfg.port_rules("8080/tcp+udp 5353/udp"))
        self.assertEqual(cfg.system_toml(), {"tcp_ports": [8080], "udp_ports": [5353, 8080], "firewall": "managed"})

    def test_ssh_on_lets_22_in_when_managed(self):
        self.system('firewall = "managed"\ntcp_ports = [443]\n')
        cfg.set_ssh(True)
        self.assertEqual(cfg.system_toml()["tcp_ports"], [22, 443])
        self.system("tcp_ports = [443]\n")  # not managed: the system opens 22 itself
        cfg.set_ssh(True)
        self.assertEqual(cfg.system_toml()["tcp_ports"], [443])

    def test_old_names(self):
        with self.assertRaises(c.UsageError) as e:
            cfg.setting("security.tcp_ports")
        self.assertIn("security.firewall_ports", str(e.exception))
        data = cfg.renamed({"security": {"tcp_ports": [22, 80], "udp_ports": [80], "ssh": True}})
        self.assertEqual(data, {"security": {"ssh": True, "firewall_ports": ["22/tcp", "80/tcp+udp"]}})

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
