"""mos-printers without CUPS: python3 -m unittest discover -s tests -p test_printers.py"""
import importlib.util
import os
import subprocess
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("mos_printers", os.path.join(HERE, "..", "scripts", "mos-printers.py"))
pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr)


def lpstat(stdout="", stderr="", code=0):
    """subprocess.run answering every command the same way."""
    return patch.object(pr.subprocess, "run", return_value=subprocess.CompletedProcess([], code, stdout, stderr))


class Printers(unittest.TestCase):
    def test_no_printers_is_an_empty_list(self):
        with lpstat(stderr="lpstat: No destinations added.\n", code=1):
            self.assertEqual(pr.printers(), [])
            self.assertEqual(pr.jobs(), [])

    def test_cups_not_running_is_an_error(self):
        with lpstat(stderr="lpstat: Scheduler is not running.\n", code=1):
            with self.assertRaises(pr.Unreachable) as e:
                pr.printers()
            self.assertIn("Scheduler is not running", str(e.exception))
            with self.assertRaises(pr.Failed):
                pr.jobs()

    def test_list_says_so_and_fails(self):
        with lpstat(stderr="lpstat: Scheduler is not running.\n", code=1), patch("builtins.print") as out:
            self.assertEqual(pr.main(["list"]), 1)
        said = " ".join(str(c) for c in out.call_args_list)
        self.assertIn("Can't reach the printing service", said)
        self.assertNotIn("No printers yet", said)

    def test_a_printer_is_listed(self):
        with lpstat(stdout="printer Office is idle.  enabled since Sat Oct 10 13:37:56 2026\n"
                           "\tDescription: Office laser\n"):
            ps = pr.printers()
        self.assertEqual([(p["name"], p["state"], p["info"]) for p in ps], [("Office", "idle", "Office laser")])


if __name__ == "__main__":
    unittest.main()
