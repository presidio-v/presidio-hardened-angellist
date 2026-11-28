# Changelog

All notable changes to `presidio-hardened-angellist` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) under the
pre-1.0 profile described in [SEMVER.md](SEMVER.md).

Entries before `v0.6.0` are reconstructed from the git history and release tags; from
`v0.6.0` onward they were written at release time.

## [Unreleased]

Nothing yet.

## [0.8.0] — Unreleased

Minor release: a new, additive `angeltriage digest` command family and the
`presidio_angellist.digest` subpackage. Nothing in the triage path changes.

### Added

- **Quarterly portfolio digest** (`presidio_angellist.digest`, `angeltriage digest build`).
  Reads the AngelList investments export (tolerates the disclaimer line, `Locked`
  values, empty caps, non-USD caps) and builds branded PDFs with an external `xelatex`:
  a *vintage* digest (one year, per-company cards, entry-cap and per-lead charts,
  outlook chart, gate retro-check) and an *aggregate* digest (a band of years: TVPI with
  locked positions at cost and marked-only, DPI, 0x share, concentration, invested vs
  value by year, multiple distribution, top positions, per-lead and per-thesis-bucket
  tables, and an aggregated gate retro-check — "would the gate have helped?").
- **Gate retro-check** driven by an operator gate-config JSON (stage and round size,
  sector bucket, post-money cap with pre-money counted as pre + round, top-lead
  substitute, per-lead limit per calendar year in date order). The config is validated
  strictly and fails closed (`GateConfigError`).
- **Brand config** (TOML/JSON): name, tagline, logo, colours, font with fallback,
  classification label (default `TLP:AMBER`), document-id prefix, header text.
- **Advisor refresh** (`angeltriage digest refresh`, `[llm]` extra): drafts per-company
  editorial content with the Anthropic Messages API and the server-side web search tool
  (default model `claude-fable-5-2`, configurable; server-side refusal fallback enabled
  where supported). Output goes to `<content>.draft.json`; approved content is never
  written.
- **Scheduled run** (`angeltriage digest run --config digest.toml`): newest export,
  current quarter, optional refresh, one PDF per vintage and band, optional email notice
  via `notify.send_plain` (file names only unless `attach_pdf = true`). Neutral examples
  in `contrib/digest/` and a weekly launchd template in `contrib/launchd/`.
- **Locked-value estimates** (`--locked-estimates FILE`, `locked_estimates` in the run
  config): advisor estimates for positions whose AngelList value is locked (evidence,
  event, post-money, estimated multiple, range, confidence, sources). Gross value is
  invested × m; net value deducts carry on the gain (the export's `Carry`, 20% where
  empty). Vintage and aggregate digests gain a "TVPI incl. locked estimates" tile (net,
  gross in the label), a "Locked positions: estimated value" table and cost-vs-estimate
  chart, a method note, and an "Est. locked value" line on vintage cards. Positions
  without an estimate stay at cost and are flagged. The file is validated strictly
  (unknown evidence, negative multiple, `low > high` are errors); a name not in the
  export warns. Example: `contrib/digest/locked-estimates.example.json`.
- **Portfolio Digest** (`--portfolio`, `portfolio = true`): one more PDF,
  `<prefix>-Portfolio-Digest-<quarter>.pdf`, comparing every vintage and band requested
  in the run plus a total (each position once): KPI tiles, a comparison table (positions,
  invested, realized, unrealized, TVPI marked / at cost / incl. estimates, DPI, 0x share,
  top-1 share, gate pass/borderline/fail, segment verdict), TVPI per segment, capital by
  thesis bucket per segment, TVPI by vintage year (J-curve), DPI per segment, gate
  verdicts per segment with each group's TVPI, top value drivers and biggest locked
  estimates. Editorial text comes from `portfolio.json` in the content directory.
  Segments carry the requested label (a band `2015-2020` stays `2015-2020` even if its
  first position is in 2017).
- **VC market comparison** (`--market FILE`, `market = "…"` in the run config): reads an
  operator benchmark file (sources, vintage TVPI quartiles and median DPI, stage round and
  post-money medians, graduation rates, sector and regional shares of dollars/deals, a
  company-location map, commentary) and builds `<prefix>-Market-Comparison-<quarter>.pdf`
  for the run's segments plus a total: KPI tiles (TVPI at cost against the market median
  for the vintage mix, capital outside the US, on-thesis share against the market,
  entry post-money against the stage/year median), TVPI and DPI by invest year against
  the market p25–p75 band and median, capital by region and by thesis bucket per segment
  against the market, over/under-weight bars, AI shown separately, capital by entry stage,
  an entry-price strip chart, graduation rates (with the portfolio's own share when locked
  estimates are given), commentary, a numbered sources list, glossary and method. Every
  market number cites its source id. A segment is compared with the market period that
  shares the most years with it. The file is validated strictly (unknown source id, share
  or rate outside 0–1, quartiles out of order, unknown stage/scope, bad period); a
  `company_geo` name not in the export warns. The Portfolio Digest's J-curve chart also
  draws the market median TVPI when `--market` is given. Example:
  `contrib/digest/market.example.json`.
- Glossary terms for quartiles (p25/p75), median, vintage, graduation rate and
  over/under-weight.
- Environment variables `ANGELTRIAGE_XELATEX` and `ANGELTRIAGE_DIGEST_MODEL`.

### Security

- All CSV, content, gate-config and brand text is LaTeX-escaped (including `\ { } $ & #
  ^ _ ~ % [ ] < > |` and control characters); `\href` targets are restricted to
  `http(s)` and percent-encoded. A pre-flight scan refuses to compile any document
  containing a file-, shell- or catcode-level primitive (`\input`, `\write`, `\openin`,
  `\catcode`, `\csname`, `^^`, …). `xelatex` runs with `-no-shell-escape`,
  `shell_escape=f`, `openout_any=p`, `openin_any=p`, a minimal environment and a
  timeout, in a throwaway directory. Injection tests cover company names such as
  `\input{/etc/passwd}` and `\write18{…}`.
- **Payload minimisation** for the refresh: a request carries only the company name,
  sector and stage labels, and prior editorial text scrubbed of amounts, multiples,
  leads, fund vehicles and the investing entity; it is re-checked against every amount
  and name in the export before it is sent, and a hit skips that company.
- Digest PDFs, `.tex` sources and drafts are written owner-only (`0600`).
- Locked-estimate and portfolio text (events, method, segment verdicts, source labels)
  goes through the same escaping and pre-flight scan; estimate source links are limited to
  `http(s)`. Estimates are local inputs only and are never sent to a model.
- Market-file text (labels, commentary, regions, buckets, basis, source labels) is escaped
  like all other content; source links are limited to `http(s)`. The market file is a
  local input and is never sent anywhere.

### Changed

- Every digest ends with a **Glossary** of the venture terms it actually uses (TVPI, DPI,
  LP, SPV, SAFE, cap, pre/post-money, carry, mark, locked, 0x, P(up-round), pro-rata),
  including terms used inside other definitions. Company names and sectors are never listed.
- Digest tables break across pages (`xltabular`) with a repeated header, so long tables no
  longer strand their section heading at the foot of a page.
- A locked position that has already paid out cash keeps that cash in the "locked at cost"
  and "incl. estimates" values (previously only the invested amount was counted).
- `contrib/` added. CONTRIBUTING no longer says the package invokes no subprocesses:
  the digest runs `xelatex`.

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
