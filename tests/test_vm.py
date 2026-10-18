"""mos-vm without QEMU, against stand-in qemu-img and qemu-system-x86_64:
python3 -m unittest discover -s tests -p test_vm.py"""
import os
import pty
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "mos-vm.sh")
# qemu-img create ... FILE SIZE: makes FILE (saying "new"); QEMU itself just says it ran.
QEMU_IMG = """#!/bin/sh
for a; do f=$prev; prev=$a; done
echo new >"$f"
"""
QEMU = "#!/bin/sh\necho booted >>\"$FAKE_LOG\"\n"


class VM(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.state, self.bin, self.log = os.path.join(t, "state"), os.path.join(t, "bin"), os.path.join(t, "log")
        os.makedirs(self.bin)
        os.makedirs(self.state)
        for name, text in (("qemu-img", QEMU_IMG), ("qemu-system-x86_64", QEMU), ("pactl", "#!/bin/sh\nexit 1\n")):
            with open(os.path.join(self.bin, name), "w") as fh:
                fh.write(text)
            os.chmod(os.path.join(self.bin, name), 0o755)
        self.iso, self.code, self.vars = (os.path.join(t, n) for n in ("a.iso", "code.fd", "vars.fd"))
        for f in (self.iso, os.path.join(t, "b.iso"), self.code, self.vars):
            open(f, "w").close()
        # A VM used before: a stick made from a.iso (with a persistent home), an installed disk, firmware settings.
        for name, text in (("stick.qcow2", "home and vaults"), ("disk.qcow2", "installed"),
                           ("OVMF_VARS.fd", "settings"), ("stick.iso", self.iso + "\n")):
            with open(os.path.join(self.state, name), "w") as fh:
                fh.write(text)

    def tearDown(self):
        self.tmp.cleanup()

    def state_now(self):
        out = {}
        for name in sorted(os.listdir(self.state)):
            with open(os.path.join(self.state, name)) as fh:
                out[name] = fh.read()
        return out

    def env(self):
        return {"PATH": self.bin + os.pathsep + os.environ["PATH"], "HOME": self.tmp.name, "FAKE_LOG": self.log,
                "MECCANICOS_VM_ISO": self.iso, "MECCANICOS_VM_OVMF_CODE": self.code, "MECCANICOS_VM_OVMF_VARS": self.vars}

    def run_(self, *args):
        return subprocess.run(["bash", SCRIPT, "--state", self.state, *args], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, env=self.env())

    def run_in_terminal(self, answer, *args):
        """With a terminal on stdin (so it asks), answering ANSWER."""
        main, side = pty.openpty()
        try:
            p = subprocess.Popen(["bash", SCRIPT, "--state", self.state, *args], stdin=side, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, env=self.env())
            os.write(main, (answer + "\n").encode())
            out, err = p.communicate(timeout=30)
        finally:
            os.close(main)
            os.close(side)
        return p.returncode, out, err

    def test_dry_run_with_fresh_changes_nothing(self):
        before = self.state_now()
        r = self.run_("--fresh", "--disk", "64G", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Would delete", r.stdout)
        self.assertIn("qemu-system-x86_64", r.stdout)
        self.assertEqual(self.state_now(), before)
        self.assertFalse(os.path.exists(self.log))

    def test_dry_run_with_a_new_iso_keeps_the_stick(self):
        before = self.state_now()
        r = self.run_("--iso", os.path.join(self.tmp.name, "b.iso"), "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.state_now(), before)

    def test_dry_run_makes_no_state_folder(self):
        state = os.path.join(self.tmp.name, "none")
        r = subprocess.run(["bash", SCRIPT, "--state", state, "--disk", "8G", "--dry-run"], capture_output=True,
                           text=True, stdin=subprocess.DEVNULL, env=self.env())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(state))

    def test_fresh_without_a_terminal_goes_ahead_and_says_what_is_lost(self):
        r = self.run_("--fresh")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("persistent home and vaults", r.stdout)
        self.assertIn("installed", r.stdout)
        s = self.state_now()
        self.assertEqual(s["stick.qcow2"], "new\n")
        self.assertNotIn("disk.qcow2", s)  # no --disk: not made again
        self.assertEqual(s["OVMF_VARS.fd"], "")  # a fresh copy

    def test_fresh_in_a_terminal_asks_and_no_keeps_everything(self):
        before = self.state_now()
        code, out, err = self.run_in_terminal("n", "--fresh")
        self.assertEqual(code, 1)
        self.assertIn("nothing deleted", err)
        self.assertEqual(self.state_now(), before)
        self.assertFalse(os.path.exists(self.log))

    def test_a_new_iso_in_a_terminal_asks_and_yes_resets_the_stick(self):
        b = os.path.join(self.tmp.name, "b.iso")
        code, out, err = self.run_in_terminal("y", "--iso", b)
        self.assertEqual(code, 0, err)
        self.assertIn("persistent home and vaults", out)
        s = self.state_now()
        self.assertEqual((s["stick.qcow2"], s["stick.iso"], s["disk.qcow2"]), ("new\n", b + "\n", "installed"))

    def test_fresh_and_installed_is_refused(self):
        before = self.state_now()
        r = self.run_("--fresh", "--installed")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.state_now(), before)


if __name__ == "__main__":
    unittest.main()
