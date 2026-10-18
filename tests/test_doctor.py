"""mos-doctor without a VM: python3 -m unittest discover -s tests -p test_doctor.py"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "mos"))
import common as c
import doctor as d


class Doctor(unittest.TestCase):
    def test_a_failing_check_is_a_problem(self):
        with patch.dict(d.AREAS, {"network": lambda _: 1 / 0}):
            found = d.run_checks(["network"])
        self.assertIn("could not check", found[0].what)
        self.assertIsNone(c.TRACE)

    def test_a_missing_program_is_an_incomplete_check(self):
        def check(_):
            c.output("no-such-program-here")
            return []
        with patch.dict(d.AREAS, {"network": check}):
            found = d.run_checks(["network"])
        self.assertIn("no-such-program-here", found[0].what)
        self.assertEqual(d.RAN["network"][0][1], 127)

    def test_without_a_terminal_nothing_is_fixed(self):
        done = []
        p = d.Problem("disk", "broken", lambda: done.append(1), "repair")
        with patch.object(sys.stdin, "isatty", return_value=False):
            self.assertFalse(d.fix(p, False))
        self.assertEqual(done, [])

    def test_a_fix_is_checked_again(self):
        p = d.Problem("disk", "broken", lambda: None, "repair")
        with patch.object(c, "log"):
            with patch.object(d, "run_checks", return_value=[p]):
                self.assertFalse(d.fix(p, True))
            with patch.object(d, "run_checks", return_value=[]):
                self.assertTrue(d.fix(p, True))

    def test_fix_exit_code(self):
        p = d.Problem("disk", "broken", advice="delete things")
        with patch.dict(d.AREAS, {"disk": lambda _: [p]}):
            self.assertEqual(d.main(["disk", "--fix"]), 1)
        with patch.dict(d.AREAS, {"disk": lambda _: []}):
            self.assertEqual(d.main(["disk", "--fix"]), 0)

    def test_reconnect_by_uuid(self):
        with patch.object(c, "output", return_value="abc"), patch.object(c, "run") as run:
            d.reconnect()
        self.assertEqual(run.call_args_list[1].args, ("nmcli", "connection", "up", "uuid", "abc"))


if __name__ == "__main__":
    unittest.main()
