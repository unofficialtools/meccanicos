"""mos-logins disconnect/reconnect and its state file without a VM, against
stand-in loginctl, systemctl, nmcli and rfkill:
python3 -m unittest discover -s tests -p test_logins.py"""
import contextlib
import importlib.util
import io
import json
import os
import stat
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "mos-logins.py")
spec = importlib.util.spec_from_file_location("mos_logins", SCRIPT)
logins = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logins)

# The machine is files in $FAKE: sshd (there = running), net (enabled or
# disabled), rfkill ("ID TYPE SOFT" lines). $FAKE_FAIL names the commands
# that do nothing and fail.
FAKES = {
    "loginctl": """
case "$1" in
list-sessions) echo "7 1000 bob" ;;
show-session) echo yes ;;
terminate-session) fails loginctl && exit 1; exit 0 ;;
esac""",
    "systemctl": """
case "$1" in
is-active) [ -e "$FAKE/sshd" ] ;;
stop) fails systemctl && exit 1; rm -f "$FAKE/sshd" ;;
start) fails systemctl && exit 1; touch "$FAKE/sshd" ;;
esac""",
    "nmcli": """
[ $# = 1 ] && { cat "$FAKE/net"; exit 0; }
fails nmcli && exit 1
[ "$2" = off ] && echo disabled >"$FAKE/net" || echo enabled >"$FAKE/net" """,
    "rfkill": """
case "$1" in
-rn) cat "$FAKE/rfkill" ;;
block|unblock)
  fails rfkill && exit 1
  to=blocked; [ "$1" = unblock ] && to=unblocked
  while read -r id kind soft; do
    if [ "$2" = all ] || [ "$2" = "$id" ]; then soft=$to; fi
    echo "$id $kind $soft"
  done <"$FAKE/rfkill" >"$FAKE/rfkill.new"; mv "$FAKE/rfkill.new" "$FAKE/rfkill" ;;
esac""",
}
HEAD = """#!/bin/sh
echo "$(basename "$0") $*" >>"$FAKE/log"
fails() { case " $FAKE_FAIL " in *" $1 "*) return 0 ;; esac; return 1; }
"""


class Disconnect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fake = os.path.join(self.tmp.name, "machine")
        bin_ = os.path.join(self.tmp.name, "bin")
        os.makedirs(self.fake)
        os.makedirs(bin_)
        for name, body in FAKES.items():
            with open(os.path.join(bin_, name), "w") as f:
                f.write(HEAD + body + "\n")
            os.chmod(os.path.join(bin_, name), 0o755)
        self.put("sshd", "")
        self.put("net", "enabled\n")
        self.put("rfkill", "0 bluetooth blocked\n1 wlan unblocked\n")  # Bluetooth was off already
        self.env = {"PATH": bin_ + os.pathsep + os.environ["PATH"], "FAKE": self.fake, "FAKE_FAIL": ""}

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, name, text):
        with open(os.path.join(self.fake, name), "w") as f:
            f.write(text)

    def get(self, name):
        with open(os.path.join(self.fake, name)) as f:
            return f.read()

    def root(self, cmd, **env):
        out = io.StringIO()
        code = 0
        with patch.dict(os.environ, dict(self.env, **env)), patch("os.geteuid", return_value=0), \
                patch.object(logins, "RUN", os.path.join(self.tmp.name, "run")), \
                patch.object(logins, "BEFORE", os.path.join(self.tmp.name, "lib", "before.json")), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                code = logins.root_main([cmd])
            except SystemExit as e:
                code = e.code
        return code, out.getvalue()

    def test_disconnect_then_reconnect(self):
        code, out = self.root("disconnect")
        self.assertEqual(code, 0, out)
        self.assertIn("Disconnected", out)
        self.assertEqual(self.get("net"), "disabled\n")
        self.assertFalse(os.path.exists(os.path.join(self.fake, "sshd")))
        self.assertEqual(self.get("rfkill"), "0 bluetooth blocked\n1 wlan blocked\n")
        code, out = self.root("reconnect")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.get("net"), "enabled\n")
        self.assertTrue(os.path.exists(os.path.join(self.fake, "sshd")))
        self.assertEqual(self.get("rfkill"), "0 bluetooth blocked\n1 wlan unblocked\n")  # Bluetooth stays off
        self.assertIn("bluetooth", out)

    def test_failing_commands_are_reported(self):
        code, out = self.root("disconnect", FAKE_FAIL="systemctl nmcli rfkill loginctl")
        self.assertEqual(code, 1)
        self.assertNotIn("Disconnected:", out)
        last = out.strip().splitlines()[-1]  # what the full-screen view and the alert show
        self.assertIn("Only partly disconnected", last)
        for what in ("SSH is still running", "networks still on", "radios still on", "would not end"):
            self.assertIn(what, last)

    def test_one_failure_is_enough(self):
        code, out = self.root("disconnect", FAKE_FAIL="nmcli")
        self.assertEqual(code, 1)
        self.assertIn("networks still on", out)
        self.assertIn("SSH stopped", out)

    def test_reconnect_without_record_turns_everything_on(self):
        self.put("net", "disabled\n")
        code, out = self.root("reconnect")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.get("rfkill"), "0 bluetooth unblocked\n1 wlan unblocked\n")
        self.assertEqual(self.get("net"), "enabled\n")

    def test_failed_reconnect_is_reported(self):
        self.root("disconnect")
        code, out = self.root("reconnect", FAKE_FAIL="nmcli")
        self.assertEqual(code, 1)
        self.assertIn("Only partly reconnected", out)


class State(unittest.TestCase):
    def test_save_is_atomic_and_keeps_permissions(self):
        with tempfile.TemporaryDirectory() as t:
            path = os.path.join(t, "meccanicos", "logins.json")
            with patch.object(logins, "STATE", path):
                logins.save_state({"ips": ["10.0.0.2"]})
                os.chmod(path, 0o600)
                logins.save_state({"ips": ["10.0.0.3"]})
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            with open(path) as f:
                self.assertEqual(json.load(f)["ips"], ["10.0.0.3"])
            self.assertEqual(os.listdir(os.path.dirname(path)), ["logins.json"])  # no temporary file left


if __name__ == "__main__":
    unittest.main()
