#!/usr/bin/env python3
"""Check mos-tutorial.py without running it: every scene's t.point(n) must
name one of its step's bullets (n < number of bullets). A wrong n crashes the
tour mid-recording, ~15 minutes in. Run: python3 tests/tutorial_points.py"""

import ast
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "scripts" / "mos-tutorial.py"


def main():
    tree = ast.parse(SOURCE.read_text(), str(SOURCE))
    # Highest constant t.point(n) in each top-level function (the scenes).
    highest = {}
    for fn in tree.body:
        if isinstance(fn, ast.FunctionDef):
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "point" and node.args
                        and isinstance(node.args[0], ast.Constant)):
                    highest[fn.name] = max(highest.get(fn.name, -1), node.args[0].value)
    # step(title, [bullets], scene, ...) calls.
    errors, checked = [], 0
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "step"
                and len(node.args) >= 3 and isinstance(node.args[1], ast.List)
                and isinstance(node.args[2], ast.Name)):
            scene, bullets = node.args[2].id, len(node.args[1].elts)
            if scene in highest:
                checked += 1
                if highest[scene] >= bullets:
                    errors.append(f"line {node.lineno}: scene {scene}() points at bullet {highest[scene]}, "
                                  f"but its step has {bullets} bullet(s)")
    if not checked:
        errors.append("no step(...) with a scene found: has mos-tutorial.py changed shape?")
    for e in errors:
        print(f"{SOURCE.name}: {e}", file=sys.stderr)
    if errors:
        sys.exit(1)
    print(f"{SOURCE.name}: {checked} scenes point only at their own bullets")


if __name__ == "__main__":
    main()
