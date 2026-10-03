#!/usr/bin/env python3
"""Fake CLI used to test the snapshot-capture recipes.

Usage:
    fake_tool.py <subcommand>

Writes two lines to stdout, two lines to stderr, and exits with code 2.
The numbers are kept distinct so the test can assert which stream each
line came from.
"""
import sys


def main() -> int:
    sys.stdout.write("Usage: fake-tool [options]\n")
    sys.stdout.write("\nOptions:\n  --help  Show this help\n")
    sys.stderr.write("WARN: deprecated flag --foo\n")
    sys.stderr.write("INFO: connecting\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
