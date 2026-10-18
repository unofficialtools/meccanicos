"""get-iso.sh (and get-iso.ps1, when pwsh is installed) against a release in a
local folder: python3 -m unittest discover -s tests -p test_get_iso.py"""
import functools
import hashlib
import http.server
import os
import shutil
import subprocess
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SH = os.path.join(HERE, "..", "scripts", "get-iso.sh")
PS1 = os.path.join(HERE, "..", "scripts", "get-iso.ps1")
ISO = "MeccanicOS-test.iso"
DATA = bytes(range(256)) * 40 + b"the end"


def sha(data):
    return hashlib.sha256(data).hexdigest()


class GetIso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.release, self.work = os.path.join(self.tmp.name, "release"), os.path.join(self.tmp.name, "work")
        os.makedirs(self.release)
        os.makedirs(self.work)
        self.parts = {f"{ISO}.part{i:02d}": DATA[(i - 1) * 4000:i * 4000] for i in (1, 2, 3)}
        for name, data in self.parts.items():
            self.put(name, data)
        self.sums([(sha(DATA), ISO)] + [(sha(d), n) for n, d in self.parts.items()])

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, name, data, where=None):
        with open(os.path.join(where or self.release, name), "wb") as fh:
            fh.write(data)

    def sums(self, lines):
        self.put("SHA256SUMS", "".join(f"{h}  {n}\n" for h, n in lines).encode())

    def files(self):
        out = {}
        for name in sorted(os.listdir(self.work)):
            with open(os.path.join(self.work, name), "rb") as fh:
                out[name] = fh.read()
        return out

    def run_(self):
        return subprocess.run(["sh", SH], capture_output=True, text=True, cwd=self.work,
                              env={**os.environ, "MECCANICOS_RELEASE": "file://" + self.release})

    def test_parts_are_joined_checked_and_deleted(self):
        r = self.run_()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(self.files()), sorted(["SHA256SUMS", ISO]))
        self.assertEqual(self.files()[ISO], DATA)

    def test_stale_parts_and_other_files_are_left_out_and_kept(self):
        self.put(ISO + ".part04", b"stale, from an earlier release", self.work)
        self.put(ISO + ".part02.bak", b"mine", self.work)
        self.put(ISO + ".part01", DATA[:4000], self.work)  # downloaded before: kept and used
        r = self.run_()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("already downloaded", r.stdout)
        f = self.files()
        self.assertEqual(f[ISO], DATA)
        self.assertEqual(sorted(f), sorted(["SHA256SUMS", ISO, ISO + ".part02.bak", ISO + ".part04"]))

    def test_only_the_selected_isos_parts(self):
        other = b"another iso"
        self.put("Other.iso.part01", other)
        self.sums([(sha(DATA), ISO)] + [(sha(d), n) for n, d in self.parts.items()] + [(sha(other), "Other.iso.part01")])
        r = self.run_()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.files()[ISO], DATA)
        self.assertNotIn("Other.iso.part01", self.files())

    def test_parts_in_number_order(self):
        # Listed out of order (and one without a leading zero): joined 1, 2, 3.
        names = list(self.parts)
        shutil.move(os.path.join(self.release, names[2]), os.path.join(self.release, ISO + ".part3"))
        self.sums([(sha(DATA), ISO), (sha(self.parts[names[2]]), ISO + ".part3"), (sha(self.parts[names[1]]), names[1]),
                   (sha(self.parts[names[0]]), names[0])])
        r = self.run_()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.files()[ISO], DATA)

    def bad_manifest(self, text, says):
        self.put("SHA256SUMS", b"what I had\n", self.work)
        self.put("SHA256SUMS", text.encode())
        r = self.run_()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn(says, r.stderr)
        self.assertEqual(self.files(), {"SHA256SUMS": b"what I had\n"})  # nothing downloaded, nothing left behind

    def test_malformed_manifests_are_refused(self):
        good = sha(DATA)
        for text, says in (
                (f"{good[:-1]}  {ISO}\n", "not a SHA256"),
                (f"{'z' * 64}  {ISO}\n", "not a SHA256"),
                (f"{good}  {ISO} extra\n", "not \"SHA256  NAME\""),
                (f"{good}  ../{ISO}\n", "not a plain file name"),
                (f"{good}  sub/{ISO}\n", "not a plain file name"),
                (f"{good}  sub\\{ISO}\n", "not a plain file name"),
                (f"{good}  ..{ISO}\n", "not a plain file name"),
                (f"{good}  -{ISO}\n", "not a plain file name"),
                (f"{good}  {ISO}\n{good}  {ISO}\n", "listed twice"),
                (f"{good}  {ISO}\n{good}  {ISO}.part01\n{good}  {ISO}.part1\n", "twice"),
                (f"{good}  {ISO}\n", "no parts"),
                (f"{good}  readme.pdf\n", "no .iso")):
            with self.subTest(text=text):
                self.bad_manifest(text, says)

    def test_an_old_iso_survives_a_failed_download(self):
        self.put(ISO, b"an older ISO of the same name", self.work)
        os.remove(os.path.join(self.release, ISO + ".part03"))
        r = self.run_()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.files()[ISO], b"an older ISO of the same name")

    def test_a_join_that_does_not_check_out_replaces_nothing(self):
        self.put(ISO, b"an older ISO of the same name", self.work)
        self.sums([("0" * 64, ISO)] + [(sha(d), n) for n, d in self.parts.items()])
        r = self.run_()
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not match", r.stderr)
        f = self.files()
        self.assertEqual(f[ISO], b"an older ISO of the same name")
        self.assertFalse([n for n in f if "joining" in n or "download" in n])
        self.assertEqual(len([n for n in f if ".part" in n]), 3)  # the good parts stay for the next try


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(shutil.which("pwsh"), "pwsh not installed")
class GetIsoPowerShell(GetIso):
    """The same, for get-iso.ps1 over HTTP (Invoke-WebRequest does not read file://)."""

    def setUp(self):
        super().setUp()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=self.release))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def run_(self):
        # A throw is exit 1, its message on stderr.
        return subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File", PS1], capture_output=True, text=True,
                              cwd=self.work, env={**os.environ, "MECCANICOS_RELEASE": f"http://127.0.0.1:{self.server.server_port}"})


if __name__ == "__main__":
    unittest.main()
