---
status: working sheet
owner: vstantch
target: OpenSSF Best Practices Badge — passing level
project_url: https://github.com/presidio-v/presidio-hardened-angellist
---

# CII Best Practices — passing-level answer sheet

Fill-in sheet for <https://www.bestpractices.dev> (passing level). This is a
skeleton: rows already backed by rendered project files are answered; rows that
depend on the specifics of this codebase are left as `FILL` markers for you to
complete after reading the repo. Do not paste a `FILL` marker into the BadgeApp —
resolve it first, honestly, or set the row to N/A with a real reason.

## Before you start

1. **Register the URL as exactly** `https://github.com/presidio-v/presidio-hardened-angellist`.
   Scorecard does a literal DB string match. A trailing slash, `www.`, or the
   package-index URL returns `NotFound` → score 0 despite a real badge.
2. **Log in with GitHub but decline the org grant.** BadgeApp requests `read:org`
   and no code path consumes it. Entry ownership is internal to its database.
3. **Confirm the community-health and process docs are on `main` first** —
   `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`,
   `SEMVER.md`. Every URL cited below must resolve on `main` before you answer.
4. Record your badge id in `hardening.toml` (`[badge] bestpractices_id`) once the
   project is created; this sheet's silver counterpart references it as
   `0`.

Shorthand below: `REPO` = `https://github.com/presidio-v/presidio-hardened-angellist`.

---

## Basics — project website content

| Criterion | Status | Justification / URL |
|---|---|---|
| `description_good` | **Met** | `REPO#readme` — README opens with what `presidio-hardened-angellist` does and the problem it solves. Confirmed: the README's first paragraph states both what the tool is (a deal-flow triage and due-diligence toolkit) and the problem it solves, and the note below it explains why it triages forwarded emails rather than calling the shut-down AngelList API. |
| `interact` | **Met** | `REPO#readme` — README covers obtaining (presidio_angellist on the package index), feedback (issues), security reports (`SECURITY.md`), and contributing. |
| `contribution` | **Met** | URL: `REPO/blob/main/CONTRIBUTING.md` — documents the fork → branch → PR flow against `main`. |
| `contribution_requirements` | **Met** | URL: `REPO/blob/main/CONTRIBUTING.md#requirements-for-acceptable-contributions` — style config, test policy, security-change rules, dependency bar. |

## Basics — FLOSS license

| Criterion | Status | Justification / URL |
|---|---|---|
| `floss_license` | **Met** | `MIT`. |
| `floss_license_osi` | **Met** | `MIT` is OSI-approved. MIT is on the OSI approved list. |
| `license_location` | **Met** | URL: `REPO/blob/main/LICENSE` |

## Basics — documentation

| Criterion | Status | Justification / URL |
|---|---|---|
| `documentation_basics` | **Met** | README plus `docs/`. `REPO#installation`, `REPO#cli-usage`, and `REPO#library-usage` cover installation and basic use. There is no separate `docs/` tree — the README is the manual, and it also documents the rubric, IMAP intake, the local-LLM backend, notifications, and the deal queue. |
| `documentation_interface` | **Met** | README API section; the public interface is documented and, for a library, enumerated in `SEMVER.md` (`presidio_angellist.__all__` or equivalent). The external interface is documented in three places: `REPO#library-usage` (worked examples), `REPO/blob/main/SEMVER.md#what-is-the-public-api` (the precise surface — everything in `presidio_angellist.__all__`, the dataclass fields, the exception hierarchy, the `angeltriage` CLI contract, and the environment variables), and the docstrings on every public function. |

## Basics — other

| Criterion | Status | Justification / URL |
|---|---|---|
| `sites_https` | **Met** | GitHub and the package index are HTTPS. The project runs no hosted site or service of its own. Its only web presence is `REPO` (GitHub) and the PyPI project page, both HTTPS-only with HSTS. |
| `discussion` | **Met** | GitHub Issues: `REPO/issues` — searchable, URL-addressable, open, no proprietary client. |
| `english` | **Met** | All docs and issue handling in English. |
| `maintained` | **Met** | Actively maintained. Latest release v0.7.1 (tagged 2026-06-06); most recent commit to `main` 2026-07-29. Eight feature/security releases shipped between 2026-04-11 and 2026-06-06, and dependency/CI maintenance has continued weekly since. |

## Change control — repository

| Criterion | Status | Justification / URL |
|---|---|---|
| `repo_public` | **Met** | `REPO` |
| `repo_track` | **Met** | git. |
| `repo_interim` | **Met** | Feature and fix branches are pushed between releases; PR-based flow. |
| `repo_distributed` | **Met** | git. |

## Change control — versioning

| Criterion | Status | Justification / URL |
|---|---|---|
| `version_unique` | **Met** | Semver per release, tagged. |
| `version_semver` | **Met** | URL: `REPO/blob/main/SEMVER.md` — documents the semver profile. |
| `version_tags` | **Met** | Every release is a git tag: `v0.6.0`, `v0.7.0`, `v0.7.1`. (Tag *signing* was adopted after v0.7.1, so those three tags are unsigned; signed tags start with the next release. The criterion itself asks only that releases be tagged.) |

## Change control — release notes

| Criterion | Status | Justification / URL |
|---|---|---|
| `release_notes` | **Met** | URL: `REPO/blob/main/CHANGELOG.md` — Keep a Changelog format, hand-written, not VCS log output. |
| `release_notes_vulns` | **Met** | CHANGELOG names each CVE/GHSA fixed. No security advisory has ever been filed against this project's own code, so there is no project CVE to record. The CHANGELOG does record the dependency-side fixes: the v0.6.0 entry names the runtime floors raised above known CVEs (`requests>=2.32.0`, `urllib3>=2.7.0`, `idna>=3.15`), which close PYSEC-2026-141, PYSEC-2026-142, and CVE-2026-45409 transitively. |

## Reporting — bug reports

| Criterion | Status | Justification / URL |
|---|---|---|
| `report_process` | **Met** | URL: `REPO/blob/main/CONTRIBUTING.md#reporting-bugs-and-requesting-features` |
| `report_tracker` | **Met** | GitHub Issues. |
| `report_responses` | **N/A** | No external bug report has ever been opened against this project — the issue tracker has zero issues to date (`REPO/issues?q=is%3Aissue`). The reporting process and the 5-business-day acknowledgement commitment are documented, but there is no response record to cite, so claiming Met here would be unfounded. Revisit once real reports arrive. |
| `enhancement_responses` | **N/A** | No enhancement or feature request has been received from an external contributor. All feature work to date originated with the maintainer and shipped through the PR flow (PRs #12–#20). |
| `report_archive` | **Met** | URL: `REPO/issues?q=is%3Aissue` — public and searchable. |

## Reporting — vulnerability reports

| Criterion | Status | Justification / URL |
|---|---|---|
| `vulnerability_report_process` | **Met** | URL: `REPO/blob/main/SECURITY.md#reporting-a-vulnerability` |
| `vulnerability_report_private` | **Met** | URL: `REPO/blob/main/SECURITY.md#reporting-a-vulnerability` — private GitHub Security Advisory via the Security tab; acknowledgement and patch targets stated. |
| `vulnerability_report_response` | **N/A** | Confirmed: zero security advisories have been filed against this project (`REPO/security/advisories`), so there is no response record in the last 6 months. N/A is the honest answer. |

## Quality — build system

| Criterion | Status | Justification / URL |
|---|---|---|
| `build` | **Met** | PEP 517 build: `python -m build` produces the sdist and wheel from source, with `hatchling` as the backend (`pyproject.toml` `[build-system]`). This is the same command the release workflow runs (`.github/workflows/publish.yml`). |
| `build_common_tools` | **Met** | Built with common, widely available tools. CPython 3.10–3.13, `pip`, `build`, and `hatchling` — all widely available and installable from PyPI on Linux, macOS, and Windows. `uv` is used for local development convenience but is not required to build. |
| `build_floss_tools` | **Met** | The entire toolchain is FLOSS. |

## Quality — automated test suite

| Criterion | Status | Justification / URL |
|---|---|---|
| `test` | **Met** | Test suite under `tests/`, licensed with the project. How to run: `CONTRIBUTING.md#local-verification` and `.github/workflows/ci.yml`. The suite lives in `tests/` and is licensed with the project (MIT). It is 16 test modules — one per source module, plus shared fixtures under `tests/fixtures/` — totalling 268 tests. How to run: `REPO/blob/main/CONTRIBUTING.md#local-verification` and `.github/workflows/ci.yml`. |
| `test_invocation` | **Met** | `pytest tests/` — a single standard command, with no arguments needed (options come from `[tool.pytest.ini_options]` in `pyproject.toml`). |
| `test_most` | **Met** | Measured statement coverage 95.3% and branch coverage 86.0% at v0.7.1. CI enforces both floors independently in the `test` job — statement ≥ 90%, branch ≥ 80% — read from `coverage.json`, because `--cov-fail-under` blends the two metrics into one number. |
| `test_continuous_integration` | **Met** | GitHub Actions on every push and PR (`.github/workflows/ci.yml`). Matrix: CPython 3.10, 3.11, 3.12, and 3.13 on `ubuntu-latest`; every version must pass. Alongside it, CodeQL and Bandit run on the same events, plus SBOM generation and the Atheris fuzz job. |

## Quality — new functionality testing

| Criterion | Status | Justification / URL |
|---|---|---|
| `test_policy` | **Met** | URL: `REPO/blob/main/CONTRIBUTING.md#tests` — written policy that functional changes ship with tests and fixes ship with regression tests. |
| `tests_are_added` | **Met** | PR #18 (v0.6.0, the security-hardening release) is the worked example. It added the SSRF guard, sink-level log redaction, retry/backoff, and the plaintext-IMAP refusal — +197 lines in `src/presidio_angellist/hardening.py`, +20 in `intake/imap.py`, +24 in `llm.py` — and shipped their tests in the same change: +152 lines in `tests/test_hardening.py`, +34 in `tests/test_imap.py`, +27 in `tests/test_llm.py`. `REPO/pull/18` |
| `tests_documented_added` | **Met** | The policy is stated in the contribution instructions themselves (`CONTRIBUTING.md#tests`). |

## Quality — warning flags

| Criterion | Status | Justification / URL |
|---|---|---|
| `warnings` | **Met** | Lint/warnings enforced in CI. `ruff check .` and `ruff format --check .` run in the `test` job on every push and pull request, on all four Python versions, and fail the build on any finding. There is no warning-only mode: a lint finding is a red build. |
| `warnings_fixed` | **Met** | CI fails on any finding; `main` is clean. |
| `warnings_strict` | **Met** | Well beyond ruff's defaults (which are `E4`, `E7`, `E9`, `F`). Enabled: `E`, `F`, `W` (pycodestyle/pyflakes), `I` (import sorting), `N` (naming), `UP` (pyupgrade), **`S` (flake8-bandit security rules)**, `B` (bugbear), `A` (builtin shadowing), `C4` (comprehensions), `SIM` (simplification), `TCH` (type-checking imports). Documented exclusions, all three deliberate: `S101` (bare `assert` is correct in tests), and `S603`/`S607` (inherited from the shared Presidio ruff profile; this package invokes no subprocess at all, so neither rule has anything to suppress here). The `fuzz/**` tree additionally ignores `N802` because Atheris dispatches on the exact name `TestOneInput`. |

## Security — secure development knowledge

| Criterion | Status | Justification / URL |
|---|---|---|
| `know_secure_design` | **Met** | The design argument is written out per principle in `REPO/blob/main/ASSURANCE.md#3-secure-design-principles-applied`, applied to this codebase rather than in the abstract: fail-safe defaults (every network capability is off until enabled, and each security control raises rather than degrading); complete mediation (the scheme check, HTTPS upgrade, SSRF guard, and rate limiter live inside `HardenedSession.request`, and log redaction is a filter on the package logger, so neither depends on a future author remembering them); least privilege (no long-lived secret of its own, read-only IMAP mailbox, OIDC publishing, read-only workflow tokens); defence in depth (transport hardening, destination validation, output hygiene, input hygiene, and supply-chain controls are independent layers, and the deterministic rubric means a successful prompt injection cannot change the score); and economy of mechanism (no cryptography implemented, three runtime dependencies, stdlib parsers throughout). Trust boundaries are enumerated in `REPO/blob/main/ARCHITECTURE.md#trust-boundaries`. No external review has been commissioned, and none is claimed. |
| `know_common_errors` | **Met** | The threat model in `REPO/blob/main/ASSURANCE.md#1-threat-model` maps each adversary to its control, and `ASSURANCE.md#4-common-implementation-weaknesses-countered` maps the weakness classes to both a control and the tool that checks it: improper input validation and injection (CWE-20, CWE-74, including prompt injection), SQL injection (CWE-89), memory safety (N/A — memory-safe language, no native extension), cryptographic misuse (CWE-327, CWE-916), hard-coded and leaked secrets (CWE-798, CWE-532), insecure transport and SSRF (CWE-319, CWE-295, CWE-918), unsafe deserialization (CWE-502), resource exhaustion (CWE-400), vulnerable dependencies (CWE-1104), and build compromise (CWE-1357). |

## Security — cryptographic practices

<!-- If this project performs NO cryptographic operations of its own, most of these
are N/A — say so explicitly per row rather than leaving them blank. If it does,
resolve each FILL against the actual primitives used. -->

| Criterion | Status | Justification / URL |
|---|---|---|
| `crypto_published` | **Met** | The project implements no cryptography of its own. The only crypto it selects is the TLS suite for outbound connections, restricted in `hardening.py` to published, standard algorithms: ECDHE key agreement with AES-GCM or ChaCha20-Poly1305 (`ECDH+AESGCM:ECDH+CHACHA20`), under TLS 1.2 or better. |
| `crypto_call` | **Met** | All crypto comes from CPython's `ssl` module (OpenSSL) via `requests`/`urllib3`, plus `smtplib`/`imaplib` for mail transport. No primitive is re-implemented — the entire crypto footprint is `ssl.create_default_context()` with a raised minimum version and a restricted cipher list. `CONTRIBUTING.md` makes never re-implementing a primitive an explicit review rule. |
| `crypto_floss` | **Met** | The crypto libraries used are FLOSS. Confirmed: CPython, OpenSSL, `requests`, and `urllib3` are all FLOSS. |
| `crypto_keylength` | **Met** | The offered suites are AES-128/256-GCM and ChaCha20-Poly1305 with ECDHE key agreement — at least 128-bit symmetric strength and ECDH curves of 256 bits or more, which exceeds the NIST 2030 minimum (112-bit equivalent). Non-EC finite-field DH is excluded outright. |
| `crypto_working` | **Met** | No MD4, MD5, single DES, RC4, or Dual_EC_DRBG. Confirmed for this codebase: the cipher string explicitly excludes `aNULL`, `MD5`, `RC4`, `DSS`, `3DES`, and `EXPORT`, and the TLS floor is 1.2, so TLS 1.0/1.1 and their weak suites cannot be negotiated. MD4, single DES, and Dual_EC_DRBG do not appear anywhere in the package. |
| `crypto_weaknesses` | **Met** | No SHA-1 and no CBC-mode dependency in default paths. Confirmed: the only suites offered are AEAD (`ECDH+AESGCM`, `ECDH+CHACHA20`), so no CBC-mode suite is on the default path, and no SHA-1-based construction is used or accepted. Certificate verification and hostname checking are always on (`CERT_REQUIRED`, `check_hostname = True`). |
| `crypto_pfs` | **Met** | Stronger than the library default this sheet assumes: `_TLSHardenedAdapter` offers *only* ephemeral-EC key-agreement suites (`ECDH+AESGCM:ECDH+CHACHA20`), so every enrichment connection has forward secrecy by construction, and static-RSA and non-EC finite-field DH suites are excluded. |
| `crypto_password_storage` | **N/A** | Stores no external-user passwords. Confirmed: the project stores no external-user password and has no authentication system. The IMAP and SMTP passwords it uses are the operator's own, read from the environment at the moment of use and never persisted, transmitted elsewhere, or logged. |
| `crypto_random` | **N/A** | The package generates no security-relevant randomness: there is no `random`, `secrets`, `os.urandom`, or `uuid` call anywhere in `src/presidio_angellist/`. Nonces and session keys are generated inside TLS by OpenSSL. |

## Security — delivery

| Criterion | Status | Justification / URL |
|---|---|---|
| `delivery_mitm` | **Met** | Distributed over HTTPS via the package index and GitHub. Distributed over HTTPS from PyPI and GitHub. The publish path is PyPI Trusted Publishing (OIDC) from a tag-triggered workflow, so no long-lived API token exists to steal; artefacts carry PEP 740 attestations and a GitHub build-provenance attestation, and the SBOM plus the in-toto provenance bundle are attached to the GitHub Release (`.github/workflows/publish.yml`). |
| `delivery_unsigned` | **Met** | Nothing is downloaded over plain HTTP and no hash or signature is fetched over an unverified channel: PyPI and GitHub are HTTPS-only, and `pip` verifies the index TLS certificate. Artefacts additionally carry PEP 740 and build-provenance attestations. |

## Security — known vulnerabilities

| Criterion | Status | Justification / URL |
|---|---|---|
| `vulnerabilities_fixed_60_days` | **Met** | No known unpatched medium+ vulnerabilities. Dependabot plus dependency audit in CI. `pip-audit` runs in the `test` job on every push and pull request and fails the build on any known-vulnerable dependency; Dependabot opens PRs weekly for both pip and GitHub Actions. Currently clean: `pip-audit` reports no known vulnerabilities, and there are 0 open code-scanning alerts. |
| `vulnerabilities_critical_fixed` | **Met** | Recent dependency criticals were closed by floor bumps within days. The dependency-side criticals that have arisen were closed by floor bumps in the v0.6.0 release: `urllib3>=2.7.0` (PYSEC-2026-141, PYSEC-2026-142) and `idna>=3.15` (CVE-2026-45409), with `requests>=2.32.0`. No vulnerability has been reported in this project's own code. |

## Security — other

| Criterion | Status | Justification / URL |
|---|---|---|
| `no_leaked_credentials` | **Met** | Verified against the full history, not just the working tree: `git log --all --diff-filter=A --name-only` shows no `.env`, `.pem`, `.key`, `.p12`, `.pfx`, keystore, or otherwise credential-shaped file has ever been added on any branch. By design the package accepts no credential as a CLI argument and persists none — all secrets are read from environment variables at point of use. `.gitignore` excludes `.env`. (Note: GitHub secret scanning is not yet enabled on the repository; enabling it is tracked as a hardening follow-up.) |

## Analysis — static

| Criterion | Status | Justification / URL |
|---|---|---|
| `static_analysis` | **Met** | CodeQL (results uploaded to GitHub code scanning), `.github/workflows/codeql.yml`. Two passes, both on every push and pull request: CodeQL with the `security-extended` query suite, uploading to GitHub code scanning (`.github/workflows/codeql.yml`, job `analyze`), and Bandit at medium severity / medium confidence over `src/` (same workflow, job `bandit`). Both are currently clean. |
| `static_analysis_common_vulnerabilities` | **Met** | CodeQL's security query suite targets common vulnerability classes. In addition to CodeQL's security suite, ruff's `S` (flake8-bandit) rule set runs as part of the lint step on every push, so the common Python security anti-patterns are caught inline at lint time as well as by the two SAST passes. `pip-audit` covers the dependency-CVE side. |
| `static_analysis_fixed` | **Met** | Findings are triaged and fixed before release. |
| `static_analysis_often` | **Met** | CodeQL runs on every push and PR to `main`, plus a weekly scheduled run. |

## Analysis — dynamic

| Criterion | Status | Justification / URL |
|---|---|---|
| `dynamic_analysis` | **Met** | Coverage-guided fuzzing with Atheris. `fuzz/fuzz_intake.py` drives the untrusted intake path end to end — RFC822 parsing, the HTML-to-text extractor, the deterministic field heuristics, and the scoring rubric that consumes their output — via `parse_email` → `is_complete` → `score_deal` on fuzzer-supplied bytes. That path is the project's primary input-validation boundary, since a forwarded deal email is written by whoever sent it. It runs time-boxed in CI on every push and pull request (`fuzz` job in `.github/workflows/ci.yml`, Linux/Python 3.12 — Atheris ships no macOS or cp310 wheel). The harness catches nothing, so any exception fails the build. |
| `dynamic_analysis_unsafe` | **N/A** | N/A confirmed: Python is memory-safe, and the package contains no native extension, no `ctypes`, and no `cffi`. The only C code in the dependency tree is inside CPython and `urllib3`, which are covered by dependency floors and `pip-audit` rather than by a sanitizer here. |
| `dynamic_analysis_enable_assertions` | **Met** | The suite is assertion-based; assertions stay enabled in tests. Confirmed: the suite is assertion-based (`pytest`, 268 tests) and nothing runs under `-O`, so assertions are checked. The fuzz job likewise invokes `python` without `-O` and does not set `PYTHONOPTIMIZE`, so runtime assertions stay enabled during dynamic analysis. |
| `dynamic_analysis_fixed` | **Met** | No unfixed medium+ findings. |

---

## Notes

- Any passing criterion not listed here is answerable **Met** by an existing
  rendered artefact or **N/A** (library vs. website/app). Check
  `SECURITY.md` / `CONTRIBUTING.md` / `ci.yml` before writing anything new.
- Silver (score 7) is generally **not** honestly reachable while a project is
  single-maintainer: `access_continuity` is a silver MUST requiring the project to
  survive the loss of any one person within a week, and `bus_factor`,
  `governance`, and `roles_responsibilities` share that root cause. A second
  person with org access and release capability resolves all four and also moves
  Scorecard's Code-Review check off 0. See the silver sheet for how the reference
  project answered these via organisational continuity rather than a lone
  maintainer.
