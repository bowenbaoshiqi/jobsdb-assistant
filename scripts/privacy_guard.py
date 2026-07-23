#!/usr/bin/env python3
"""Fail when tracked repository files appear to contain private data."""

from __future__ import annotations

from pathlib import Path

from src.privacy import scan_tracked_files


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = scan_tracked_files(root)
    if not findings:
        print("Privacy guard passed.")
        return 0

    print("Privacy guard failed:")
    for finding in findings:
        print(f"- {finding.path}: {finding.reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
