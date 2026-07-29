# Changelog

All notable changes to `presidio-hardened-angellist` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) under the
pre-1.0 profile described in [SEMVER.md](SEMVER.md).

Entries before `v0.6.0` are reconstructed from the git history and release tags; from
`v0.6.0` onward they were written at release time.

## [Unreleased]

Nothing yet.

## [0.7.3] — 2026-07-30

**Security release.** Fixes a redirect-based SSRF bypass found by an independent
third-party audit. Anyone using `--enrich`, `--imap`, or `--watch` on untrusted deal
mail should upgrade; the deterministic path without enrichment was never affected.

### Security

- **SSRF guard now covers redirect hops (High, CWE-918).** The scheme check, HTTPS
  upgrade, and non-public-address refusal moved from `HardenedSession.request` to
  `HardenedSession.send`. `requests` resolves redirects inside `Session.send` →
  `resolve_redirects`, which calls `send()` per hop and never re-enters `request()`,
  so the previous placement validated only the first hop: a public site answering
  `302 Location: https://169.254.169.254/` was followed into the cloud-metadata
  endpoint and its body could reach `deal.one_liner`, the deal store, `--notify`
  mail, and the LLM. Every hop is now validated before it is fetched.
- **Redirect depth capped at 5** (`HardenedSession.DEFAULT_MAX_REDIRECTS`), down from
  the `requests` default of 30. Configurable via `max_redirects=`.
- **Alternative address notations refused** (CWE-918). A host whose labels are all
  numeric but which does not parse strictly as an IP — `0177.0.0.1`, `0x7f.0.0.1`,
  `2130706433` — is now refused rather than handed to the resolver, whose reading of
  them is platform-dependent. IPv6 zone ids (`127.0.0.1%eth0`) and brackets are
  stripped before the check.
- **Enrichment responses are capped at 512 KiB** and streamed (CWE-400); only
  textual content types are scanned. A hostile site can no longer answer a
  multi-gigabyte body that the wall-clock timeout does not bound.
- **The deal store is created owner-only** (CWE-732): mode `0o600` on a database this
  tool creates, `0o700` on a directory it creates. Pre-existing files are left as the
  operator set them — see SECURITY.md.
- **Secret redaction extended** (CWE-532) to `password=` / `passwd:` / `pwd` forms and
  to credential-shaped environment names such as `IMAP_PASSWORD=`. `ImapConfig.password`
  and `NotifyConfig.password` are excluded from `repr()`, so a stray
  `logger.debug(config)` or a stringified exception cannot print a mail password.
- **Watch mode no longer logs the mailbox username** to stderr.

### Changed

- `store.py` raises `DealStoreError` where it previously used `assert` for control
  flow, so behaviour is unchanged under `python -O`.

### Documentation

- `ASSURANCE.md` and `SEMVER.md` corrected: both previously claimed the hardening
  layer mediated *every* request with no bypass path. That was wrong for redirects
  until this release, and the corrected text explains where the guard actually sits
  and why.
- First independent third-party security audit recorded (2026-07-29, against commit
  `e9e8b60`).

## [0.7.2] — 2026-07-29

**First signed release.** This is the first release carrying a signed git tag, a
build-provenance attestation, and an SBOM as release assets. Tags up to and including
v0.7.1 are unsigned — tag signing was adopted after v0.7.1 and a published tag cannot be
re-signed. See
[SECURITY.md](SECURITY.md#verifying-releases-and-obtaining-public-signing-keys) for how to
verify. No functional change to the library: everything below is governance, CI, and
supply-chain work.

### Added

- OpenSSF governance and assurance layer: `ARCHITECTURE.md`, `ASSURANCE.md`,
  `GOVERNANCE.md`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SEMVER.md`, this changelog,
  `.github/CODEOWNERS`, and `allowed_signers`.
- OpenSSF Scorecard workflow, publishing results to the public OpenSSF store.
- Bandit SAST pass alongside the existing CodeQL analysis.
- CycloneDX SBOM generation in CI and attached to releases; PEP 740 build-provenance
  attestations on published artefacts.
- Atheris fuzz harness (`fuzz/fuzz_intake.py`) over the untrusted email/CSV intake path,
  run time-boxed in CI on Linux.
- Branch-coverage floor (≥ 80%) enforced in CI alongside the existing statement floor
  (≥ 90%).

### Changed

- `SECURITY.md` gains reporter credit, release-verification and signing-key instructions,
  and links to the assurance case.

## [0.7.1] — 2026-06-06

### Added

- Reasoning-model support on the local LLM backend via `ANGELTRIAGE_LLM_EXTRA_BODY`, for
  server-specific request-body parameters the OpenAI schema does not cover.
- Loose-JSON field coercion when a model returns near-miss types.

## [0.7.0] — 2026-06-06

### Added

- Local / self-hosted LLM backend over any OpenAI-compatible endpoint
  (`ANGELTRIAGE_LLM_BASE_URL`), selectable without an Anthropic key.
- SMTP deal notifications (`--notify`), with credentials read from the environment only and
  delivery over implicit TLS or STARTTLS.
- Exactly-once polling: a `processed_messages` table so `--watch` does not re-triage a
  message it has already seen.

## [0.6.0] — 2026-06-06

Security-hardening release.

### Added

- SSRF guard (`assert_public_host`): enrichment refuses loopback, private, link-local
  (including the `169.254.169.254` cloud-metadata endpoint), reserved, multicast, and
  unspecified destinations, for IP literals and for every resolved address.
- Sink-level log redaction: a `RedactingFilter` installed on the `presidio_angellist`
  logger at import scrubs bearer tokens, `access_token=` / `api_key=` parameters,
  `Authorization` headers, and `sk_live_*` / `sk-ant-*` keys from every record.
- LLM prompt-injection defence: deal text is wrapped in a delimited untrusted-content block
  with nested delimiters stripped, under a system prompt that declares it data.
- Retry with exponential backoff honouring `Retry-After`, and per-host rate limiting.
- Plaintext IMAP is refused unless the operator sets `IMAP_ALLOW_INSECURE=1`.

### Changed

- Runtime dependency floors raised above known CVEs: `requests>=2.32.0`, `urllib3>=2.7.0`,
  `idna>=3.15`.

## [0.5.2] — 2026-06-06

### Changed

- Better company-name and one-liner extraction; growth-stage flagging in the rubric.

## [0.5.1] — 2026-06-04

### Added

- `--watch`: interval polling of the IMAP mailbox, auto-triaging new deals.

## [0.5.0] — 2026-06-04

### Added

- IMAP intake (`--imap`) for deal emails, with credentials from `IMAP_*` environment
  variables and a read-only mailbox.

## [0.4.0] — 2026-06-04

### Added

- SQLite-backed persistent deal queue (`--save`, `--queue`, `--set-status`), deduping deals
  across runs by website domain or normalised company name.

## [0.3.0] — 2026-06-04

### Added

- CSV intake, full rubric configuration (`--rubric`), and a more robust HTML extractor.

## [0.2.0] — 2026-06-04

### Changed

- Pivot from the (now shut down) AngelList API client to a deal-flow triage toolkit. The
  Presidio hardening layer is retained and reused for outbound enrichment.

## [0.1.0] — 2026-04-11

### Added

- Initial scaffold: hardened HTTP session, project layout, CI.

[Unreleased]: https://github.com/presidio-v/presidio-hardened-angellist/compare/v0.7.3...HEAD
[0.7.3]: https://github.com/presidio-v/presidio-hardened-angellist/compare/v0.7.2...v0.7.3
[0.7.2]: https://github.com/presidio-v/presidio-hardened-angellist/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/presidio-v/presidio-hardened-angellist/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/presidio-v/presidio-hardened-angellist/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/presidio-v/presidio-hardened-angellist/releases/tag/v0.6.0
