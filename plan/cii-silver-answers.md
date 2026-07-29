---
status: working sheet
owner: vstantch
target: OpenSSF Best Practices Badge — SILVER level (on top of passing)
project_url: https://github.com/presidio-v/presidio-hardened-angellist
related:
  - cii-passing-answers.md
---

# CII Best Practices — SILVER answer sheet

Fill-in sheet for the **silver** tab at
<https://www.bestpractices.dev/en/projects/13877>. It covers
only the criteria silver *adds* on top of passing; passing answers carry over
unchanged (see `cii-passing-answers.md`).

This is a skeleton: rows backed by rendered project files are answered; rows that
depend on this codebase are left as `FILL` markers. Resolve every `FILL` honestly
before pasting — do not paste a marker into the BadgeApp.

Each row shows the **Status** to set in the dropdown and the **Justification** to
paste. `REPO` = `https://github.com/presidio-v/presidio-hardened-angellist`.

## Badge embed — no change needed

Silver uses the **same** embed code as passing; the badge image auto-renders the
current level:

```markdown
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/13877/badge)](https://www.bestpractices.dev/projects/13877)
```

If the README badge already uses this URL, it upgrades to "silver" automatically
once the badge cache refreshes — no edit required.

## Backing docs

These rendered files back the silver answers; confirm each is on `main`:

- `GOVERNANCE.md` — governance model, roles, continuity
- `ARCHITECTURE.md` — components, core flow, trust boundaries
- `ASSURANCE.md` — consolidated security assurance case (`assurance_case`)
- `allowed_signers` — public release signing key for local tag verification
- `CONTRIBUTING.md` — DCO sign-off requirement
- `SECURITY.md` — reporter credit, how to obtain signing keys, assurance-case link
- `README.md` — 12-month roadmap + links to GOVERNANCE/ARCHITECTURE/ASSURANCE

---

## Governance & continuity

| Criterion | Status | Justification to paste |
|---|---|---|
| `dco` | **Met** | Every commit must carry a DCO `Signed-off-by` line (`git commit -s`); enforced in review. Documented at `REPO/blob/main/CONTRIBUTING.md#licensing-and-developer-certificate-of-origin-dco`. Inbound = outbound `MIT`. |
| `code_of_conduct` | **Met** | Contributor Covenant at `REPO/blob/main/CODE_OF_CONDUCT.md` (standard location). |
| `governance` | **Met** | Governance model documented at `REPO/blob/main/GOVERNANCE.md` — decision-making, escalation, and security/API change rules. Confirmed: GOVERNANCE.md describes the model actually in force — a single maintainer under a steward organisation (PRESIDIO Group / the `presidio-v` org), ordinary changes decided by the reviewing maintainer on the PR, security-relevant changes requiring an explicit security rationale against the enumerated security-sensitive modules, compatibility changes governed by SEMVER.md, and unresolved disagreements escalated to the steward organisation. |
| `roles_responsibilities` | **Met** | Key roles (steward org, maintainer, security contact, release manager, contributor) documented at `REPO/blob/main/GOVERNANCE.md#roles-and-responsibilities`. |
| `access_continuity` | **Met** | Continuity is a property of the steward organisation, not of one person, and rests on custody arrangements that actually exist for this repository: (a) the repository is owned by the `presidio-v` GitHub **organisation**, not a personal account, so organisation owners can grant repository and release access to another member at any time; (b) publishing uses PyPI **Trusted Publishing (OIDC)** bound to `presidio-v/presidio-hardened-angellist` and the `pypi` deployment environment — which carries required-reviewer and branch-policy protection rules — so there is no personal, long-lived API token that dies with an individual; (c) the release **signing key**'s private half is held in the organisation's password manager, with custody ultimately with PRESIDIO Group leadership, rather than solely on one contributor's machine, so it is recoverable; (d) the release process is documented end to end (signed tag → tag-triggered `publish.yml` → OIDC publish → release assets), so any authorised engineer can cut a release by following it; and (e) the public half of the signing key is committed as `allowed_signers`, so tag verification does not depend on any individual either. Issues can therefore be triaged, contributions reviewed, and releases cut within a week if any single individual becomes unavailable. URL: `REPO/blob/main/GOVERNANCE.md#project-continuity`. |
| `bus_factor` (SHOULD) | **Met** | PRESIDIO Group is a staffed steward organisation with more than one person able to assume the maintainer, security-contact, and release-manager roles defined at https://github.com/presidio-v/presidio-hardened-angellist/blob/main/GOVERNANCE.md#roles-and-responsibilities. The bus factor is therefore not bounded by any single individual: the repository is owned by the presidio-v GitHub organisation rather than a personal account, so organisation owners can grant repository and release access to another member at any time; release credentials are org-held and recoverable rather than tied to one machine (PyPI Trusted Publishing via OIDC bound to this repository and a gated pypi environment, with the signing key's private half in the organisation's password manager); and the release process is documented end to end so any authorised engineer can cut a release. An external reviewer outside the maintainer's organisation is listed as a code owner in https://github.com/presidio-v/presidio-hardened-angellist/blob/main/.github/CODEOWNERS, extending review capability beyond a single person. Documented at https://github.com/presidio-v/presidio-hardened-angellist/blob/main/GOVERNANCE.md#project-continuity |

## Documentation

| Criterion | Status | Justification to paste |
|---|---|---|
| `documentation_roadmap` | **Met** | `REPO#roadmap` includes a "Planned direction (next 12 months)" section. Confirmed, and rewritten to be forward-looking rather than a release history: `REPO#next-12-months` names real work — in flight, the OpenSSF hardening layer (governance and assurance docs, Scorecard, Bandit, SBOM, the Atheris harness, the badge); next, v0.8.0 pluggable enrichment providers behind a stable interface plus queue export/digest, and the first signed release tag with SBOM and provenance attached; later and explicitly marked as under evaluation, a migration mechanism for the SQLite deal store, broader signal extraction, and an independent third-party security review. The release history is kept below it as a separate section. |
| `documentation_architecture` | **Met** | `REPO/blob/main/ARCHITECTURE.md` — components, core-flow pipeline, and trust boundaries; linked from the README. |
| `documentation_security` | **Met** | `REPO/blob/main/SECURITY.md` documents the security controls, threat model, and reporting process; `ARCHITECTURE.md#trust-boundaries` states the trust boundaries. The threat model and design rationale live in `REPO/blob/main/ASSURANCE.md` — §1 the threat model (each adversary mapped to its control, with an explicit out-of-scope list), §2 the trust boundaries, §3 the secure-design argument per principle, and §4 the weakness-class table. `REPO/blob/main/SECURITY.md#data-handling--trust-boundaries` documents the same boundaries operationally, control by control, and `REPO/blob/main/ARCHITECTURE.md#trust-boundaries` gives the canonical boundary table that the other two reference. |
| `documentation_quick_start` | **Met** | README "Quick Start" (before/after example) plus `docs/`. There is no section literally titled 'Quick Start' and no `docs/` tree — the README is the manual. The quick-start path is `REPO#installation` (one `pip install` line) followed immediately by `REPO#cli-usage`, which opens with a runnable one-liner (`angeltriage deal.eml`) and shows its actual output, and `REPO#library-usage`, which shows the three-line library equivalent. The deterministic path needs no API key and no configuration, so those examples work immediately after install. |
| `documentation_current` | **Met** | Docs track the current release line; per-version roadmap and hand-written `CHANGELOG.md` are kept in sync with each release. |
| `documentation_achievements` | **Met** | The OpenSSF Best Practices badge is displayed and hyperlinked on the README front page. |

## Change control & reporting

| Criterion | Status | Justification to paste |
|---|---|---|
| `contribution_requirements` | **Met** | `REPO/blob/main/CONTRIBUTING.md#requirements-for-acceptable-contributions` — style, tests, security-change rules, dependency bar. |
| `report_tracker` | **Met** | GitHub Issues: `REPO/issues`. |
| `maintenance_or_update` | **Met** | `REPO/blob/main/SECURITY.md#supported-versions` states which versions are supported and for how long; `REPO/blob/main/SEMVER.md` documents the upgrade path and what counts as a breaking change. |
| `vulnerability_report_credit` | **N/A** | No vulnerability has been reported against or resolved in this project's own code, in the last 12 months or at any point in its history — the repository has zero published security advisories, so there is no reporter to credit and the criterion's own N/A condition applies. The crediting policy is nevertheless already written down and will apply to the first such report: https://github.com/presidio-v/presidio-hardened-angellist/blob/main/SECURITY.md#reporting-a-vulnerability commits to crediting reporters of valid vulnerabilities by name in the published GitHub Security Advisory and in the CHANGELOG entry for the fix, unless the reporter asks to remain anonymous. For completeness: the dependency-side CVEs closed by floor bumps in v0.6.0 (PYSEC-2026-141, PYSEC-2026-142, CVE-2026-45409) were upstream advisories surfaced by pip-audit and Dependabot, not reports made to this project, so they carry no reporter to credit either. |
| `vulnerability_response_process` | **Met** | `REPO/blob/main/SECURITY.md#reporting-a-vulnerability` — private GitHub Security Advisory intake, acknowledgement and patch targets stated. |

## Quality & testing

| Criterion | Status | Justification to paste |
|---|---|---|
| `tests_documented_added` | **Met** | `REPO/blob/main/CONTRIBUTING.md#tests` states the policy that changes adding/modifying functionality ship with tests in the same PR. |
| `test_policy_mandated` | **Met** | Formal written policy at `REPO/blob/main/CONTRIBUTING.md#tests`: functionality changes ship with tests; bug fixes include a regression test. Enforced in review and by the coverage gate. |
| `automated_integration_testing` | **Met** | `REPO/blob/main/.github/workflows/ci.yml` runs the full suite on every push and pull request. The full suite (268 tests across 16 modules) runs on every push and pull request via `REPO/blob/main/.github/workflows/ci.yml`, on a matrix of CPython 3.10, 3.11, 3.12, and 3.13 on `ubuntu-latest`; all four must pass before merge, as required status checks on `main`. There is no separate partner or end-to-end suite: the tool is a local CLI/library with no service to integrate against, and the tests exercise the whole pipeline (intake → extraction → enrichment → scoring → memo → store → notify) against fixtures with network and LLM boundaries stubbed. Alongside the suite, the same events run CodeQL, Bandit, SBOM generation, and the Atheris fuzz job. |
| `regression_tests_added50` | **Met** | Policy requires a regression test with every bug fix. Worked example: PR #20 (v0.7.1) fixed the local-LLM backend returning empty content for reasoning models — +95 lines in `src/presidio_angellist/llm.py` shipped with +71 lines in `tests/test_llm.py` in the same change. Confirmed for the period: every functional fix merged in the last six months (PRs #17, #18, #19, #20) carried tests in the same pull request — well above 50%. The remaining merges in that window (PRs #21–#34) are dependency and CI-pinning changes with no behavioural surface to regress. The policy requiring this is written at `REPO/blob/main/CONTRIBUTING.md#tests`. |
| `test_statement_coverage80` | **Met** | Measured statement coverage 95.3%, branch coverage 86.0% at v0.7.1 — both above the 80% silver bar. CI enforces the two metrics independently in the `test` job of `REPO/blob/main/.github/workflows/ci.yml`: statement ≥ 90% and branch ≥ 80%, read from `coverage.json`, on all four Python versions. `pyproject.toml` additionally sets `fail_under = 90` as a local backstop. |
| `warnings_strict` | **Met** | Enabled ruff rule sets, well beyond the `E4`/`E7`/`E9`/`F` default: `E`, `F`, `W`, `I` (imports), `N` (naming), `UP` (pyupgrade), **`S` (flake8-bandit security rules)**, `B` (bugbear), `A` (builtin shadowing), `C4`, `SIM`, `TCH`. Both `ruff check .` and `ruff format --check .` run in CI on every push and pull request and fail the build on any finding — there is no warning-only mode. Documented exclusions: `S101` (bare `assert` in tests), `S603`/`S607` (inherited profile rules with nothing to suppress — the package invokes no subprocess), and `N802` under `fuzz/**` because Atheris dispatches on the exact name `TestOneInput`. |
| `coding_standards` | **Met** | `REPO/blob/main/CONTRIBUTING.md#style` names the required style/lint tool; config in the project's build/lint config. **ruff** for both linting and formatting, configured in `pyproject.toml` under `[tool.ruff]` (line length 99, target `py310`) and documented at `REPO/blob/main/CONTRIBUTING.md#style`. |
| `coding_standards_enforced` | **Met** | The style/lint check runs in CI on every PR (FLOSS enforcement). |
| `installation_common` | **Met** | Standard install from the package index. `pip install presidio-hardened-angellist` for the deterministic core, or `pip install 'presidio-hardened-angellist[llm]'` to add the Claude-backed extraction and memo. Standard PyPI install, no build step, no compiler. |
| `installation_development_quick` | **Met** | `REPO/blob/main/CONTRIBUTING.md#local-verification` — documents the one setup path that installs everything needed to build and test. |
| `build_repeatable` (SHOULD) | **N/A** | No compilation occurs: this is a pure-Python project, and the criterion's own N/A clause for scripting languages whose source is used directly rather than compiled applies. The wheel and sdist produced by `python -m build` package the same .py source files that are executed at runtime; there is no compiler, no linker, and no generated binary or generated source whose bit-for-bit reproducibility could differ between builds. Separately, and not claimed here: the project pins its GitHub Actions to commit SHAs but declares runtime dependencies as version floors rather than an exact-pinned lockfile, so the resolved dependency set is not reproducible across time. That is a dependency-pinning gap rather than a build-determinism one, and it is recorded against `external_dependencies` rather than dressed up here. |
| `build_standard_variables` | **N/A** | N/A confirmed: this is a pure-Python package built by `hatchling` through PEP 517. There is no compiler or linker invocation, so `CC`, `CFLAGS`, and `LDFLAGS` have nothing to apply to. |
| `build_preserve_debug` | **N/A** | N/A confirmed: there are no compiled artefacts — the wheel contains only Python source, so there is no debug information to separate or preserve. |
| `build_non_recursive` | **N/A** | N/A confirmed: there is no `make`, no subdirectory build, and no recursive build step of any kind. The entire build is one PEP 517 invocation. |
| `installation_standard_variables` | **N/A** | N/A confirmed: installation is via `pip`/`uv` from PyPI, which manages its own target paths. `DESTDIR` and `PREFIX` conventions do not apply to a Python package manager install. |

## Dependencies & components

| Criterion | Status | Justification to paste |
|---|---|---|
| `external_dependencies` | **Met** | Dependencies are listed machine-readably in the project manifest and fully pinned in a lockfile; a CycloneDX SBOM is generated per release in CI. Dependencies are declared machine-readably in `REPO/blob/main/pyproject.toml`: three runtime dependencies (`requests`, `urllib3`, `idna`), with optional groups for `llm`, `dev`, and `fuzz`. A CycloneDX SBOM (`sbom.cdx.json`) is generated in CI on every push and attached to each GitHub Release. To be precise about the limits: the manifest uses **version floors, not a lockfile** — there is no `uv.lock` in this repository, so the graph is not exactly pinned (see `build_repeatable`). Currency and vulnerability status are handled by Dependabot on both pip and GitHub Actions plus `pip-audit` gating every build. |
| `updateable_reused_components` | **Met** | All reused components are standard package-index packages installed via the package manager (no vendored copies); Dependabot tracks updates. |
| `interfaces_current` | **Met** | Dependencies are kept current (Dependabot + dependency floors), the public API is tracked in `SEMVER.md`, and the code does not rely on deprecated FLOSS functions where alternatives exist. |

## Security

| Criterion | Status | Justification to paste |
|---|---|---|
| `assurance_case` | **Met** (URL required) | URL: `REPO/blob/main/ASSURANCE.md`. Consolidated assurance case with all four required parts (threat model, trust boundaries, secure-design-principles argument, common-implementation-weakness argument). Confirmed: `REPO/blob/main/ASSURANCE.md` is written for this codebase with no unresolved markers. It names the two assets (the analyst's machine/network position, and their credentials plus deal data), maps twelve threats each to its control, states five out-of-scope items explicitly (prompt injection is mitigated not solved, DNS rebinding, endpoint/account security, the operator-configured LLM endpoint, and investment-judgement correctness), enumerates the eight trust boundaries, argues all five secure-design principles against real controls, and maps ten weakness classes each to a control and to the tool that checks it. It also records plainly that no independent third-party security review has been commissioned. |
| `implement_secure_design` | **Met** | Argued per principle, grounded in real controls, at `REPO/blob/main/ASSURANCE.md#3-secure-design-principles-applied`: **fail-safe defaults** — every network capability is off until the operator enables it (enrichment needs `--enrich`, LLM steps need a configured backend, IMAP/SMTP need environment credentials), and each security control raises rather than degrading (non-HTTPS scheme, non-public host, invalid weights file, plaintext IMAP); **complete mediation** — the scheme check, HTTPS upgrade, SSRF guard, and rate limiter live inside `HardenedSession.request` and log redaction is a `logging.Filter` on the package logger, so neither can be forgotten by a future caller; **least privilege** — no long-lived secret of its own, the IMAP mailbox is opened read-only, publishing uses short-lived OIDC credentials, and every workflow declares a read-only top-level token with only the one job that needs `security-events: write` elevating; **defence in depth** — transport hardening, destination validation, log hygiene, input hygiene, and supply-chain controls are independent layers, and because scoring is deterministic and model-free a successful prompt injection cannot alter the score, only the advisory prose; **economy of mechanism** — no cryptography is implemented (TLS comes from stdlib `ssl`/OpenSSL), stdlib parsers are used throughout, and the runtime dependency set is three packages. |
| `input_validation` | **Met** | Untrusted input is validated at the boundary, before use, and the boundaries are enumerated at `REPO/blob/main/ARCHITECTURE.md#trust-boundaries`. Concrete example: a forwarded deal email is parsed by the stdlib `email` module and, for HTML parts, by an `html.parser` subclass that drops `<script>`, `<style>`, `<head>`, and `<title>` rather than interpreting them; the extracted text only ever populates typed `Deal` dataclass fields, and is never executed, rendered, or interpolated into a shell, SQL, or filesystem operation. Second example, on the egress side: the company URL extracted from that same untrusted email is attacker-influenced, so before any fetch `assert_public_host` resolves it and refuses loopback, private, link-local (including `169.254.169.254`), reserved, multicast, and unspecified addresses — checking every resolved address, not just the first, and unwrapping IPv4-mapped IPv6. Third: operator-supplied `--weights`/`--rubric` JSON is whitelist-validated and fails closed with `WeightsConfigError` on an unknown key, a negative, non-numeric, or boolean value, a non-object document, or an all-zero weight set — a typo cannot silently change scoring. The intake path is additionally fuzzed with Atheris in CI. |
| `hardening` | **Met** | Applied and verifiable in the repository: **egress TLS enforced** — HTTP is upgraded to HTTPS and any other scheme refused, with a TLS 1.2 floor, mandatory certificate and hostname verification, and an ephemeral-EC-only cipher list; **SSRF guard** on every enrichment fetch; **secret scrubbing in logs** via a `RedactingFilter` installed on the package logger at import, so redaction happens at the sink for every record rather than at individual call sites; **credentials from the environment only**, never accepted as CLI arguments (which are visible in `ps` and shell history) and never persisted; **plaintext IMAP refused** unless explicitly overridden; **parameterized SQL** throughout the deal store; **bounded retries, per-host rate limiting, and explicit timeouts** on outbound calls; **every GitHub Action pinned to a commit SHA**; **read-only top-level workflow tokens**, with elevation only in the single job that needs it; **`persist-credentials: false`** on checkouts; **protected `main`** with required status checks and admin enforcement; **OIDC Trusted Publishing** with no stored PyPI token, behind a required-reviewer `pypi` environment; and **SBOM plus build provenance attestation** on releases. There is no container image, so no base-image digest pinning applies. |
| `crypto_weaknesses` | **Met** | The project implements no cryptography, so there is no security function of its own to check — the only crypto it selects is the outbound TLS suite, and that selection is deliberately narrowed in `hardening.py` to AEAD suites with ephemeral-EC key agreement (`ECDH+AESGCM:ECDH+CHACHA20`), explicitly excluding `aNULL`, `MD5`, `RC4`, `DSS`, `3DES`, and `EXPORT`, under a TLS 1.2 minimum. No MD5, SHA-1, or DES-based construction is used or accepted anywhere, and no CBC-mode suite is on the default path. |
| `crypto_algorithm_agility` (SHOULD) | **N/A** | N/A confirmed as the honest answer for this project: it negotiates no crypto suite of its own design and exposes no crypto-selection API to its callers. Algorithm choice is delegated to TLS, where the offered set is pinned to current strong primitives in one place (`_TLSHardenedAdapter._CIPHERS`) and migrating it is an ordinary versioned change to that constant, reviewed as a security-sensitive change — not a runtime switch. This is a SHOULD. |
| `crypto_credential_agility` | **Met** | Confirmed: no key, password, or token is hard-coded or defaulted anywhere in the source tree. Every credential is supplied from outside it and read at the moment of use — `ANTHROPIC_API_KEY` / `ANGELTRIAGE_LLM_API_KEY`, `IMAP_USER`/`IMAP_PASSWORD`, `ANGELTRIAGE_SMTP_*` — so rotation is an environment change with no code change, no rebuild, and no reinstall. Nothing is persisted to the deal store or written to disk, and `.gitignore` excludes `.env`. |
| `crypto_used_network` | **Met** | Network communication uses TLS. Confirmed: all network communication uses TLS. Enrichment goes through `HardenedSession`, which upgrades `http://` to `https://` and refuses any other scheme; IMAP defaults to `IMAP4_SSL` and refuses plaintext unless the operator explicitly sets `IMAP_ALLOW_INSECURE=1`; SMTP uses implicit TLS (465) or STARTTLS; the Anthropic SDK talks HTTPS. The one documented exception is an operator-configured local LLM endpoint (`ANGELTRIAGE_LLM_BASE_URL`), which is typically loopback on the operator's own machine and is trusted by configuration — recorded in SECURITY.md and ASSURANCE.md rather than left implicit. |
| `crypto_tls12` | **Met** | The HTTP client uses TLS ≥1.2. Confirmed: `_TLSHardenedAdapter` sets `ctx.minimum_version = ssl.TLSVersion.TLSv1_2`, so TLS 1.0 and 1.1 cannot be negotiated on any enrichment connection. Covered by tests in `tests/test_hardening.py`. |
| `crypto_certificate_verification` | **Met** | TLS certificate verification is on by default; verification is not disabled. Confirmed and enforced in two places: the session sets `self.verify = True`, and the TLS context sets `check_hostname = True` with `verify_mode = ssl.CERT_REQUIRED`. There is no flag, environment variable, or public parameter that disables verification, and `SEMVER.md` treats making verification optional as a breaking change. |
| `crypto_verification_private` | **Met** | Certificate verification precedes transmission of any private data. Confirmed: certificate and hostname verification happen during the TLS handshake, which completes before any request body, header, or credential is transmitted — verification is not deferred or performed post hoc. Combined with the HTTPS-only rule, no request this project makes can send data over an unverified channel. |
| `signed_releases` | **Unmet — until the next release ships** | The signing machinery is in place and the verification instructions live at `REPO/blob/main/SECURITY.md#verifying-releases-and-obtaining-public-signing-keys`: (a) **build provenance** — the release workflow produces a Sigstore-backed in-toto attestation over the artefacts via `actions/attest-build-provenance`, verifiable with `gh attestation verify <artefact> --repo presidio-v/presidio-hardened-angellist`, and the bundle is attached to the GitHub Release as `provenance.intoto.jsonl` alongside the SBOM; PyPI artefacts additionally carry PEP 740 attestations from Trusted Publishing. (b) **SSH-signed git tags** — signed with the organisation's release key, whose public half is committed as `REPO/blob/main/allowed_signers` for local verification with `git -c gpg.ssh.allowedSignersFile=allowed_signers verify-tag <tag>`. Stated plainly: tag signing was adopted after v0.7.1, so tags up to and including v0.7.1 are unsigned and signed tags begin with the next release — do not answer this row Met until that release has actually shipped. |
| `version_tags_signed` | **Unmet — until the next release ships** | Every release is a git tag (`v0.6.0`, `v0.7.0`, `v0.7.1`), and the signing key's public half is committed as `REPO/blob/main/allowed_signers` with verification instructions in `REPO/blob/main/SECURITY.md#verifying-releases-and-obtaining-public-signing-keys`. But stated plainly: tag signing was adopted after v0.7.1, so the three existing tags are **unsigned** and `gh api .../git/tags/<sha> --jq .verification.verified` returns false for them. Answer Met only once a signed tag has actually been pushed — retroactively re-signing a published tag is not an option. |
| `sites_password_security` | **N/A** | N/A confirmed: the project runs no site or service, and stores no user password. It has no authentication surface of its own — the only credentials involved are the operator's own mail and API credentials, read from the environment at point of use and never stored. |

## Analysis & monitoring

| Criterion | Status | Justification to paste |
|---|---|---|
| `static_analysis_common_vulnerabilities` | **Met** | CodeQL (`REPO/blob/main/.github/workflows/codeql.yml`) and OpenSSF Scorecard run on every push/PR. Alongside CodeQL (`security-extended`) and OpenSSF Scorecard, the project runs **Bandit** at medium severity / medium confidence over `src/` on every push and pull request (`bandit` job in `REPO/blob/main/.github/workflows/codeql.yml`), and ruff's **`S` (flake8-bandit)** rule set as part of the lint step, so the common Python security anti-patterns are caught inline at lint time as well. `pip-audit` covers the dependency-CVE side and fails the build. All are currently clean, with 0 open code-scanning alerts. |
| `dynamic_analysis_unsafe` | **N/A** | N/A confirmed for memory safety: Python is memory-safe and the package contains no native extension, no `ctypes`, and no `cffi`, so there is no memory-unsafe component to run a sanitizer against. Fuzzing runs regardless — `fuzz/fuzz_intake.py` drives the untrusted intake path with Atheris, time-boxed, on every push and pull request (`fuzz` job in `ci.yml`, Linux/Python 3.12). |
| `dependency_monitoring` | **Met** | Dependabot + dependency audit in CI + OpenSSF Scorecard continuously check external dependencies for known vulnerabilities. |

## Accessibility & internationalization

| Criterion | Status | Justification to paste |
|---|---|---|
| `accessibility_best_practices` | **N/A** | N/A confirmed: this is a developer library and a text-mode CLI with no graphical or end-user UI, so the WCAG/ATAG surface does not apply. Its terminal output is plain text and is also available as machine-readable JSON via `--json`. |
| `internationalization` | **N/A** | N/A confirmed: there are no localizable user-facing UI strings — the CLI emits English diagnostic and report text with no message catalogue, and the tool processes deal emails as opaque text rather than presenting a localized interface. Input is decoded per the email's declared charset, so non-English deal content is parsed correctly. |

---

## Notes

- Any silver criterion **not** listed here carries over unchanged from the passing
  sheet — leave those answers as they already are.
- If BadgeApp shows a silver-only criterion not covered above, it is almost
  certainly answerable **N/A** (library vs. website/app) or **Met** by an existing
  artefact; check `SECURITY.md` / `CONTRIBUTING.md` / `ci.yml` first.
- `bus_factor`, `build_repeatable`, and `crypto_algorithm_agility` are SHOULD
  criteria — "Met" / "N/A" with an honest justification is accepted; none is a
  hard blocker.
- `assurance_case` is the only silver MUST that requires a net-new document
  (`ASSURANCE.md`); resolve its own FILL markers before answering this row.
