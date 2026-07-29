# SPDX-License-Identifier: MIT
# Copyright (c) 2026 PRESIDIO Group
"""Atheris coverage-guided fuzz harness for the untrusted intake path.

This drives the code that actually touches attacker-controlled bytes: RFC822
parsing, the HTML-to-text extractor, the deterministic field heuristics, and the
scoring rubric that consumes their output. A forwarded deal email is written by
whoever sent it, so this is the project's primary input-validation boundary (see
ARCHITECTURE.md#trust-boundaries).

Nothing is caught: `parse_email`, `is_complete`, and `score_deal` are documented
to accept arbitrary input without raising, so any exception is a real finding and
is left to propagate so Atheris records it.

GOTCHAS (read before running):
  - No macOS Atheris wheel: run this under Linux CI only (the fuzz job), never
    on a developer Mac.
  - No cp310 wheel: Atheris 3.x dropped Python 3.10. Run under Python 3.12.
  - Editable installs can shadow the package: a `pip install -e .` checkout may
    win over the installed distribution on sys.path. Install the built wheel (or
    verify the import resolves to the real target module) before fuzzing, so the
    code under coverage is the code you think it is.
"""

import sys

import atheris

from presidio_angellist import is_complete, parse_email, score_deal


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    raw = fdp.ConsumeBytes(fdp.remaining_bytes())

    deal = parse_email(raw)
    is_complete(deal)
    score_deal(deal)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
