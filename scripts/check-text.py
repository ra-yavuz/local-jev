#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PATHS = [
    "README.md",
    "docs",
    "bin",
    "lib",
    "scripts",
    "debian",
    ".github",
    "Makefile",
    "LICENSE",
]
NEEDLES = [
    chr(0x2014),
    "generated" + " with",
    "made" + " by " + "ai",
    "co-authored-by: " + "claude",
    "co-authored-by: " + "codex",
]


def iter_files(path: Path):
    if path.is_file():
        yield path
    elif path.is_dir():
        for child in path.rglob("*"):
            if child.is_file():
                yield child


def main() -> int:
    failed = False
    for item in PATHS:
        for path in iter_files(ROOT / item):
            text = path.read_text(errors="ignore").lower()
            for needle in NEEDLES:
                if needle.lower() in text:
                    print(f"forbidden text in {path.relative_to(ROOT)}", file=sys.stderr)
                    failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
