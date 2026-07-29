# Contributing to presidio-hardened-angellist

Thanks for your interest. This project is held to a stricter bar than a typical library — the
checklist below is what a change needs to clear before it can be merged.

## Reporting a security vulnerability

**Do not open a public issue for a security vulnerability.** Use the private reporting
process in [SECURITY.md](SECURITY.md) — GitHub Security Advisories, via the repository's
"Security" tab, or contact security@presidio-group.eu. You will get an acknowledgement
within 5 business days.

## Reporting bugs and requesting features

Open a [GitHub issue](https://github.com/presidio-v/presidio-hardened-angellist/issues). Search existing issues first.
For a bug, include:

- the installed version (`pip show presidio_angellist`) and language-runtime version
- what you expected to happen, and what happened instead
- a minimal reproduction if you can produce one

Please strip any secrets, credentials, or personal data from anything you paste into a
public issue.

## New to the project?

Issues labelled [`good first issue`](https://github.com/presidio-v/presidio-hardened-angellist/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
are scoped to be approachable without deep knowledge of the codebase and are a good place to
start.

## How changes are made

All changes go through a pull request against `main`. Direct pushes to `main` are blocked by
branch protection, and every PR must pass the required status checks before it can merge.

1. Fork the repository and create a branch off `main`.
2. Make your change, with tests (see the test policy below).
3. Run the local verification block until it is clean.
4. Update `CHANGELOG.md` under `## [Unreleased]`.
5. Open a PR describing what changed and why.

## Code review

Every pull request — including a maintainer's own — is reviewed before it merges. This is
not advisory: `main` requires an approving review from a code owner
([CODEOWNERS](.github/CODEOWNERS)) who is **not** the author of the change, enforced by
branch protection (required review, code-owner review, stale-approval dismissal, and
last-push re-approval; admins are included).

What a reviewer confirms before approving:

- **Tests** — new or changed functionality ships with tests; bug fixes include a regression
  test; the coverage floors hold.
- **Security reasoning** — for changes to a security-sensitive area (see below), the PR
  explains the reasoning, and no existing default is weakened without an explicit rationale.
- **Compatibility** — changes to the public API surface, event/record shapes, or exception
  types follow [SEMVER.md](SEMVER.md); breaking changes are called out.
- **Style and scope** — the linter is clean, the change is focused, and `CHANGELOG.md` is
  updated.

Reviewers approve via GitHub's review flow. A change that needs rework is returned with
specific requested changes rather than merged with caveats.

## Requirements for acceptable contributions

A change is merged when it meets all of the following.

### Style

Formatting and linting are enforced by the project linter and are not a matter of taste — CI
rejects anything that does not conform.

This project uses **ruff** for both linting and formatting, configured in
`pyproject.toml` under `[tool.ruff]`: line length 99, target version `py310`. The enabled
rule sets are `E`, `F`, `W` (pycodestyle/pyflakes), `I` (import sorting), `N` (naming),
`UP` (pyupgrade), **`S` (flake8-bandit — security)**, `B` (bugbear), `A` (builtin
shadowing), `C4` (comprehensions), `SIM` (simplification), and `TCH` (type-checking
imports). `S101` is ignored so tests can use bare `assert`; `S603`/`S607` are ignored
project-wide as a legacy of the shared Presidio ruff profile — this package invokes no
subprocesses at all, so neither rule has anything to suppress here.

Do not add a blanket `# noqa` to silence an `S` finding. Either fix it, or narrow it to the
specific rule with a comment explaining why the pattern is safe.

Each module uses a single consistent import (or include) style. Do not mix conventions for
the same dependency within one module.

### Tests

**Test policy: any change that adds or modifies functionality must ship with tests in the
same pull request.** Bug fixes must include a regression test that fails before the fix and
passes after it. This is enforced in review, and by the coverage gate.

Two floors are enforced in CI, both in the `test` job of
[`.github/workflows/ci.yml`](.github/workflows/ci.yml), on every supported Python version:

- **Statement coverage ≥ 90%**, via `pytest --cov=presidio_angellist --cov-fail-under=90`.
- **Branch coverage ≥ 80%**, checked from the emitted `coverage.json` in a separate step,
  because `--cov-fail-under` blends the two metrics into one number and would let branch
  coverage sag behind a high statement figure.

A pull request that drops either figure below its floor fails CI and cannot merge.


### Security-sensitive changes

This project's security controls are the product. If your change touches any of the
security-sensitive modules, then the reviewer bar above applies in full:

- **`hardening.py`** — TLS enforcement, HTTPS upgrade, the SSRF guard
  (`assert_public_host`, `_is_blocked_ip`), secret redaction (`SecretRedactor`,
  `RedactingFilter`), retry, and per-host rate limiting. Every outbound enrichment request
  passes through here.
- **`intake/email.py`, `intake/csv.py`** — the primary untrusted-input parsers, including
  the HTML stripper. Anything that changes what gets parsed, or how, is security-relevant.
- **`intake/imap.py`** — mail credentials, the TLS default, and the plaintext refusal.
- **`llm.py`** — the untrusted-content wrapping and injection-guard system prompts, the
  API-key handling, and the OpenAI-compatible request path that deliberately bypasses
  `HardenedSession`.
- **`enrich/web.py`** — the only code that fetches an attacker-influenced URL.
- **`config.py`, `rubric_config.py`** — strict validation of operator-supplied JSON; these
  fail closed and must keep doing so.
- **`store.py`** — SQL construction and the on-disk queue.
- **`notify.py`** — SMTP credentials and transport security.

- explain the security reasoning in the PR description, not only the mechanics
- do not weaken a default. New controls are opt-in; relaxations of existing controls need
  an explicit rationale
- never re-implement cryptographic primitives — call a vetted standard library or crypto
  dependency instead
- functions that produce a stable serialized or digest output are byte-stability contracts.
  Changing their output for existing input is a breaking change even if no signature changes

### Public API and compatibility

The public API surface and what counts as a breaking change are defined in
[SEMVER.md](SEMVER.md). Read it before changing anything exported from the public API, and
note that event/record shapes and exception types are part of the contract that downstream
consumers depend on.

### Dependencies

New runtime dependencies are a high bar for a security-focused library and need justification
in the PR. Prefer the standard library. Optional functionality belongs in an optional
dependency group rather than the core dependency set.

## Local verification

Run this before opening a PR, and fix anything it reports:

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m ruff check . \
  && .venv/bin/python -m ruff format --check . \
  && .venv/bin/python -m pytest tests/ -x -q --tb=short
```

To reproduce the CI coverage gates locally before pushing:

```bash
.venv/bin/python -m pytest tests/ \
  --cov=presidio_angellist --cov-branch --cov-fail-under=90 --cov-report=term-missing
```

The Atheris fuzz harness under `fuzz/` runs in CI on Linux only — Atheris publishes no
macOS wheel, and none for Python 3.10 — so there is no local equivalent on a developer Mac.

CI runs the test suite across every supported runtime version. A change must pass on all of
them.

## Commit messages

Write in the imperative mood ("add TTL bound", not "added" or "adds"). Explain *why* the
change is being made where that is not obvious from the diff.

## Licensing and Developer Certificate of Origin (DCO)

The project is MIT licensed, and contributions are accepted under the same
terms (inbound = outbound).

To assert that you have the right to submit your contribution, every commit must
be **signed off** under the [Developer Certificate of Origin](https://developercertificate.org/)
1.1. Signing off means adding a `Signed-off-by` line to the commit message with
your real name and email:

```
Signed-off-by: Jane Developer <jane@example.com>
```

`git commit -s` adds this line for you. By signing off you certify the DCO —
in short, that you wrote the change or otherwise have the right to submit it
under the project's MIT license. Pull requests whose commits are not signed off
will be asked to amend before merge.

## Code of conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
