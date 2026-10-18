"""mos-read's reader threads without Piper or sound, against a stand-in
voice and player: python3 -m unittest discover -s tests -p test_read.py"""
import importlib.util
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "mos-read.py")
with patch.dict(os.environ, {"MECCANICOS_READ_VOICE": "stand-in"}):
    spec = importlib.util.spec_from_file_location("mos_read", SCRIPT)
    read = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(read)


class Voice:
    def __init__(self, broken=False, seconds=0.1):
        self.config = types.SimpleNamespace(sample_rate=16000)
        self.broken = broken
        self.chunk = types.SimpleNamespace(audio_int16_bytes=b"\0\0" * int(16000 * seconds))

    def synthesize(self, text, syn_config=None):
        if self.broken:
            raise RuntimeError("onnxruntime fell over")
        return [self.chunk]


def until(test, seconds=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not test():
        time.sleep(0.02)
    return test()


class Reader(unittest.TestCase):
    def setUp(self):
        piper = types.ModuleType("piper")
        piper.SynthesisConfig = lambda **kw: kw
        p = patch.dict(sys.modules, {"piper": piper})
        p.start()
        self.addCleanup(p.stop)

    def start(self, reader):
        threads = [threading.Thread(target=reader.prefetch_loop, daemon=True),
                   threading.Thread(target=reader.play_loop, daemon=True)]
        for t in threads:
            t.start()
        return threads

    def test_synthesis_failure_ends_the_wait(self):
        reader = read.Reader(Voice(broken=True), ["One.", "Two."])
        threads = self.start(reader)
        self.assertTrue(until(lambda: reader.error), "no error shown")
        self.assertIn("onnxruntime fell over", reader.error)
        self.assertTrue(threads[0].is_alive())  # waiting for retry, not dead
        reader.stop()
        for t in threads:
            t.join(timeout=3)
            self.assertFalse(t.is_alive())
        self.assertTrue(reader.finished)

    def test_retry_after_a_failure(self):
        voice = Voice(broken=True)
        reader = read.Reader(voice, ["One."])
        with tempfile.TemporaryDirectory() as t, patch.object(read, "PW_PLAY", os.path.join(t, "player")):
            with open(read.PW_PLAY, "w") as f:
                f.write("#!/bin/sh\ncat >/dev/null\n")
            os.chmod(read.PW_PLAY, 0o755)
            threads = self.start(reader)
            self.assertTrue(until(lambda: reader.error))
            voice.broken = False
            reader.retry()
            self.assertTrue(until(lambda: reader.finished), "did not read after retry")
            self.assertIsNone(reader.error)
            for t_ in threads:
                t_.join(timeout=3)

    def test_failing_player_is_given_up(self):
        reader = read.Reader(Voice(seconds=5), ["One.", "Two."])  # longer than what is queued ahead
        with patch.object(read, "PW_PLAY", "true"):  # exits at once: every write breaks
            threads = self.start(reader)
            self.assertTrue(until(lambda: reader.error), "kept restarting the player")
        self.assertIn("keeps stopping", reader.error)
        reader.stop()
        for t in threads:
            t.join(timeout=3)
        self.assertTrue(reader.finished)
        self.assertIsNone(reader.proc)

    def test_missing_player(self):
        reader = read.Reader(Voice(), ["One."])
        with patch.object(read, "PW_PLAY", "/nonexistent/pw-play"):
            threads = self.start(reader)
            self.assertTrue(until(lambda: reader.error))
        self.assertIn("doesn't work", reader.error)
        reader.stop()
        for t in threads:
            t.join(timeout=3)


class Forget(unittest.TestCase):
    def test_forget_deletes_the_last_text(self):
        with tempfile.TemporaryDirectory() as t, patch.object(read, "CACHE", t), \
                patch.object(read, "LAST", os.path.join(t, "last.txt")), patch("builtins.print"):
            read.remember("secret")
            self.assertEqual(os.stat(read.LAST).st_mode & 0o777, 0o600)
            with self.assertRaises(SystemExit):
                read.get_text(["mos-read", "--forget"])
            self.assertFalse(os.path.exists(read.LAST))


if __name__ == "__main__":
    unittest.main()
