# Fuzzing

Coverage-guided fuzzing of `presidio-hardened-angellist` with Atheris.

`fuzz_intake.py` drives the untrusted intake path — RFC822 parsing, the HTML-to-text
extractor, the deterministic field heuristics, and the scoring rubric that consumes them.
That path is where attacker-written bytes enter the program (see
[ARCHITECTURE.md](../ARCHITECTURE.md#trust-boundaries)), which is why it is the one fuzzed.

```bash
python -m pip install '.[fuzz]'
python fuzz/fuzz_intake.py                        # runs until a crash or Ctrl-C
python fuzz/fuzz_intake.py -max_total_time=60     # time-boxed, as CI runs it
```

CI runs the harness time-boxed on every push and pull request (the `fuzz` job in
[`ci.yml`](../.github/workflows/ci.yml)).

Gotchas: Atheris publishes no macOS wheel, so this is Linux-only and cannot be run on a
developer Mac; there is no cp310 wheel either, so run it under Python 3.12. An editable
install can shadow the installed package, so fuzz the built wheel when it matters which
copy is under coverage. The harness must import and drive the real target module — that is
what makes both OpenSSF Scorecard's literal `import atheris` detection and the
`dynamic_analysis` criterion hold.

The harness catches nothing: `parse_email`, `is_complete`, and `score_deal` accept
arbitrary input without raising, so any exception is a finding.
