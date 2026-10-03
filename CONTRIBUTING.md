# Contributing

Thanks for looking. This plugin is small on purpose: a few skills, one command and two dependency-free Python
scripts. Please keep it that way: no runtime packages, no network access, and scripts that never execute the tool
whose snapshots they read.

## Development setup

Python 3.9 or newer. There is nothing to install.

    python -m unittest discover -s tests -t . -v

Use `python3` where that is the name of the interpreter. `python tests/run_tests.py` runs the same tests. Use
synthetic data only: the fixtures describe a made-up tool.

## Pull requests

- One logical change per pull request, with a test that fails without it. For a new classification rule add both a
  case that must be flagged and one that must stay quiet.
- Keep `README.md`, `PRIVACY.md`, `SECURITY.md` and the skill text true: if behaviour changes, the words change in
  the same pull request.
- Keep the scripts on the standard library and working on Python 3.9.
- Run `claude plugin validate .` if you have Claude Code installed.

## Reporting problems

Bugs and ideas: open an issue. Security problems: see `SECURITY.md` and do not open a public issue.
