"""mos-upgrade without a network or a rebuild, against stand-in nix, nixos-rebuild
and git (as root in a user namespace: unshare -r):
python3 -m unittest discover -s tests -p test_upgrade.py"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "mos-upgrade.sh")
OLD_LOCK = {"nodes": {"meccanicos": {"original": {"owner": "o", "repo": "r"}, "locked": {"rev": "a" * 40}},
                      "nixpkgs": {"original": {"ref": "nixos-26.05"}}}}
NEW_LOCK = {"nodes": {"meccanicos": {"original": {"owner": "o", "repo": "r"}, "locked": {"rev": "b" * 40}},
                      "nixpkgs": {"original": {"ref": "nixos-26.05"}}}}
FLAKE = '{ inputs.meccanicos.url = "github:o/r/latest"; }\n'
# nix flake update writes $FAKE_NEW_LOCK; the rest answers as little as it can.
NIX = """#!/bin/sh
echo "nix $*" >>"$FAKE_LOG"
case "$1 $2" in
    "flake update") cp "$FAKE_NEW_LOCK" "$4/flake.lock" ;;
    "flake archive") echo '{}' ;;
    "flake metadata") echo '{"revision": "bbbb", "lastModified": 0}' ;;
esac
"""
# Waits for $FAKE_DIR/go when $FAKE_WAIT is set (to overlap two runs), moves
# the system profile when $FAKE_ACTIVATE is set, exits $FAKE_REBUILD.
REBUILD = """#!/bin/sh
echo "nixos-rebuild $*" >>"$FAKE_LOG"
if [ -n "${FAKE_WAIT:-}" ]; then
    : >"$FAKE_DIR/building"
    while [ ! -e "$FAKE_DIR/go" ]; do sleep 0.05; done
fi
[ -z "${FAKE_ACTIVATE:-}" ] || ln -sfn "$FAKE_DIR/new-system" "$MECCANICOS_SYSTEM_PROFILE"
exit "${FAKE_REBUILD:-0}"
"""


@unittest.skipUnless(shutil.which("unshare") and shutil.which("jq") and shutil.which("flock"), "needs unshare, jq, flock")
class Upgrade(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.dest, self.bin, self.log = os.path.join(t, "nixos"), os.path.join(t, "bin"), os.path.join(t, "log")
        os.makedirs(self.dest)
        os.makedirs(self.bin)
        # systemctl is-enabled sshd: exits $FAKE_SSHD (not enabled by default).
        systemctl = '#!/bin/sh\nexit "${FAKE_SSHD:-1}"\n'
        for name, text in (("nix", NIX), ("nixos-rebuild", REBUILD), ("git", "#!/bin/sh\nexit 0\n"),
                           ("systemctl", systemctl)):
            with open(os.path.join(self.bin, name), "w") as fh:
                fh.write(text)
            os.chmod(os.path.join(self.bin, name), 0o755)
        self.write("flake.nix", FLAKE)
        self.write("flake.lock", json.dumps(OLD_LOCK))
        self.new_lock = os.path.join(t, "new.lock")
        with open(self.new_lock, "w") as fh:
            fh.write(json.dumps(NEW_LOCK))
        self.profile = os.path.join(t, "system")
        os.symlink(os.path.join(t, "old-system"), self.profile)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        with open(os.path.join(self.dest, name), "w") as fh:
            fh.write(text)

    def read(self, name):
        with open(os.path.join(self.dest, name)) as fh:
            return fh.read()

    def env(self, **fake):
        return {"PATH": self.bin + os.pathsep + os.environ["PATH"], "HOME": self.tmp.name, "TMPDIR": self.tmp.name,
                "MECCANICOS_NIXOS_DIR": self.dest, "MECCANICOS_SYSTEM_PROFILE": self.profile,
                "MECCANICOS_SSH_KEYS": os.path.join(self.tmp.name, "authorized_keys"),
                "FAKE_LOG": self.log, "FAKE_DIR": self.tmp.name, "FAKE_NEW_LOCK": self.new_lock,
                **{f"FAKE_{k.upper()}": str(v) for k, v in fake.items()}}

    def start(self, *args, **fake):
        return subprocess.Popen(["unshare", "-r", "bash", SCRIPT, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, env=self.env(**fake))

    def run_(self, *args, **fake):
        return subprocess.run(["unshare", "-r", "bash", SCRIPT, *args], capture_output=True, text=True, env=self.env(**fake))

    def leftovers(self):
        return [f for f in os.listdir(self.tmp.name) if f.startswith("tmp")]

    def test_an_update_works_and_keeps_the_lock_before(self):
        r = self.run_()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(self.read("flake.lock")), NEW_LOCK)
        self.assertEqual(json.loads(self.read("flake.lock.previous")), OLD_LOCK)  # for mos-updates
        self.assertFalse(os.path.exists(os.path.join(self.dest, "flake.nix.previous")))
        self.assertEqual(self.leftovers(), [])

    def test_ssh_in_use_stays_on(self):
        with open(os.path.join(self.tmp.name, "authorized_keys"), "w") as fh:
            fh.write("# a comment\nssh-ed25519 AAAA me@laptop\n")
        self.write("meccanicos.toml", "# Written by mos-config\nlid = \"lock\"\n")
        r = self.run_(sshd=0)
        self.assertEqual(r.returncode, 0, r.stderr)
        toml = self.read("meccanicos.toml")
        self.assertTrue(toml.startswith("ssh = true"), toml)
        self.assertIn('lid = "lock"', toml)
        self.assertIn("SSH stays on", r.stdout)
        self.assertEqual(self.run_(sshd=0).returncode, 0)  # only once
        self.assertEqual(self.read("meccanicos.toml").count("ssh ="), 1)

    def test_ssh_without_keys_or_already_chosen_is_left_alone(self):
        r = self.run_(sshd=0)  # running, but no keys to log in with
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.dest, "meccanicos.toml")))
        with open(os.path.join(self.tmp.name, "authorized_keys"), "w") as fh:
            fh.write("ssh-ed25519 AAAA me@laptop\n")
        self.write("meccanicos.toml", "ssh = false\n")
        self.write("flake.lock", json.dumps(OLD_LOCK))
        self.assertEqual(self.run_(sshd=0).returncode, 0)
        self.assertEqual(self.read("meccanicos.toml"), "ssh = false\n")

    def test_a_second_update_is_refused_while_one_runs(self):
        first = self.start("--boot", wait=1)
        try:
            for _ in range(200):
                if os.path.exists(os.path.join(self.tmp.name, "building")):
                    break
                time.sleep(0.05)
            else:
                self.fail("the first update never got to the rebuild")
            during = (self.read("flake.nix"), self.read("flake.lock"))
            second = self.run_("--to", "main", rebuild=1)
            self.assertEqual(second.returncode, 1)
            self.assertIn("another update is running", second.stderr)
            self.assertIn("Nothing changed", second.stderr)
            self.assertEqual((self.read("flake.nix"), self.read("flake.lock")), during)
        finally:
            open(os.path.join(self.tmp.name, "go"), "w").close()
            out, err = first.communicate(timeout=30)
        self.assertEqual(first.returncode, 0, err)
        self.assertEqual(json.loads(self.read("flake.lock")), NEW_LOCK)
        with open(self.log) as fh:
            self.assertEqual(fh.read().count("nixos-rebuild"), 1)  # the second never got there

    def test_a_failed_build_puts_back_its_own_files_only(self):
        # Another run's (or an old run's) leftovers in /etc/nixos are not ours to restore.
        self.write("flake.lock.previous", "someone else's\n")
        self.write("flake.nix.previous", "someone else's\n")
        r = self.run_("--to", "main", rebuild=1)
        self.assertEqual(r.returncode, 1)
        self.assertIn("did not build", r.stderr)
        self.assertEqual(self.read("flake.nix"), FLAKE)
        self.assertEqual(json.loads(self.read("flake.lock")), OLD_LOCK)
        self.assertEqual(self.read("flake.lock.previous"), "someone else's\n")
        self.assertEqual(self.read("flake.nix.previous"), "someone else's\n")
        self.assertEqual(self.leftovers(), [])

    def test_a_partly_activated_system_says_how_to_go_back(self):
        r = self.run_(rebuild=1, activate=1)
        self.assertEqual(r.returncode, 1)
        self.assertIn("partly put in place", r.stderr)
        self.assertIn("boot menu", r.stderr)
        self.assertEqual(json.loads(self.read("flake.lock")), OLD_LOCK)

    def test_check_needs_no_lock(self):
        fd = os.open(self.dest, os.O_RDONLY)
        try:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
            r = self.run_("--check")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Following:", r.stdout)
        finally:
            os.close(fd)


if __name__ == "__main__":
    unittest.main()
