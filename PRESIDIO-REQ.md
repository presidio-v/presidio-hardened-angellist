# Presidio-Hardened AngelList – Requirements & Deliberation Log

## Overview

Build a production-ready Python package `presidio-hardened-angellist` that provides a
security-hardened client for the **AngelList Startup/Funding Data API**.

Users adopt it with a single import change and automatically receive strong Presidio
security defaults with no changes to their calling code.

---

## Mandatory Presidio Security Extensions

- **Strict TLS 1.2+ enforcement** — Rejects TLS 1.0/1.1; enforces strong cipher suites
  (`ECDH+AESGCM`, `ECDH+CHACHA20`, etc.); `verify=True` always; `check_hostname=True`
- **HTTP → HTTPS auto-upgrade** — Insecure `http://` base URLs silently upgraded to HTTPS;
  non-HTTP(S) schemes refused
- **SSRF guard** — Outbound targets resolving to loopback/private/link-local (incl.
  `169.254.169.254`)/reserved/multicast/unspecified addresses are refused, bounding the
  attacker-influenced enrichment URL
- **API key / secret redaction** — Bearer tokens, `sk_live_*` / `sk-ant-*` keys,
  `access_token=`, `api_key=`, and `Authorization:` headers are scrubbed from all log
  output at the sink via a `RedactingFilter` installed on the `presidio_angellist` logger
- **Per-host rate limiting** — Token-bucket limiter (`RateLimiter`) with configurable
  req/s cap; prevents accidental DoS against the AngelList API
- **Retry with exponential backoff** — Retries on 5xx and connection errors; raises
  immediately on 401/403 (no wasted attempts)
- **API-level 429 handling** — Respects `Retry-After` header from AngelList rate-limit
  responses; waits and retries automatically
- **Structured security-event logging** — Every hardening action emits a structured
  log entry via the `presidio_angellist` logger (HTTPS upgrade, TLS error, rate limit
  wait, auth failure)
- **Full GitHub security posture** — SECURITY.md, `.github/dependabot.yml`,
  `.github/workflows/codeql.yml`, `.github/workflows/ci.yml`

---

## Technical Requirements

- Python 3.9+
- `pyproject.toml` + `hatchling` build backend
- `src/presidio_angellist/__init__.py` layout — wrapper only, no copying of upstream source
- High test coverage with `pytest` + `pytest-cov` (target ≥ 90%)
- `ruff` formatting and linting enforced in CI
- `responses` library used for mocking HTTP in tests (no real API calls)
- README.md with usage examples and security feature table
- LICENSE = MIT
- Version = 0.1.0

---

## API Coverage (v0.1.0)

| Method | Endpoint | Description |
|---|---|---|
| `get_startup(startup_id)` | `GET /startups/{id}` | Fetch a single startup |
| `search_startups(query, market, location, page)` | `GET /startups` | Search/filter startups |
| `get_startup_roles(startup_id)` | `GET /startups/{id}/roles` | Fetch team members |
| `get_funding_rounds(startup_id)` | `GET /startups/{id}/funding` | All funding rounds for a startup |
| `get_funding_round(funding_id)` | `GET /funding/{id}` | Single funding round |
| `get_user(user_id)` | `GET /users/{id}` | User / investor profile |
| `search_users(query, role, page)` | `GET /users/search` | Search users / investors |
| `get_tags(tag_type)` | `GET /tags` | Fetch market / location tags |

---

## Version History & Deliberation

### v0.1.0 — Initial scaffold (2026-04-11)

**Scope decisions:**
- Implement the core client (`AngelListClient`) as a thin wrapper around a hardened
  `requests.Session` subclass (`HardenedSession`).
- Expose `SecretRedactor` and `RateLimiter` as public classes so callers can customise
  redaction placeholders and rate-limit settings without subclassing.
- Keep `AngelListError`, `RateLimitError`, and `AuthError` as the full exception
  hierarchy for v0.1; more granular errors (e.g. `NotFoundError`) deferred to v0.2.
- Do NOT implement OAuth flow in v0.1; AngelList API key (Bearer token) auth is
  sufficient for the public read-only API endpoints.
- `_TLSHardenedAdapter` uses `ssl.create_default_context()` augmented with an explicit
  minimum version and cipher list; does not rely on system-level TLS policy.
- Rate limiter is per-host (dictionary keyed by `urlparse(url).netloc`) to avoid
  cross-host interference when callers override `base_url`.
- CI matrix covers Python 3.9–3.13; coverage threshold set to 90%.

**Requirements delivered in v0.1.0:**
- Strict TLS 1.2+ via `_TLSHardenedAdapter` — Delivered
- HTTP → HTTPS auto-upgrade in `HardenedSession.request` — Delivered
- API key / secret redaction via `SecretRedactor` — Delivered
- Per-host rate limiting via `RateLimiter` — Delivered
- Retry with exponential backoff for 5xx and connection errors — Delivered
- 429 / `Retry-After` handling — Delivered
- Structured security-event logging via `presidio_angellist` logger — Delivered
- Full GitHub security posture (SECURITY.md, dependabot, CodeQL, CI) — Delivered
- MIT LICENSE — Delivered
- pyproject.toml + hatchling + src/ layout — Delivered

---

## Roadmap

> Note: 0.1.0 was an API-client scaffold; the project pivoted at 0.2.0 (the
> AngelList API was shut down). The pre-pivot 0.2.0/0.3.0 plans below are kept
> for history; the live roadmap is the post-pivot one.

| Version | Planned features |
|---|---|
| **0.1.0** | Initial scaffold (hardened AngelList API client) — see above |
| **0.2.0** *(pivot)* | Deal-flow triage: email intake, deterministic rubric, `--weights`, LLM extraction fallback + memo, `angeltriage` CLI |
| **0.3.0** | CSV/batch import, full rubric config (`--rubric`), HTML-email robustness, enrichment fallbacks |
| **0.4.0** | SQLite deal queue (`--save`/`--queue`/`--set-status`), dedup across runs, workflow statuses |
| **0.5.0** | IMAP intake (`--imap`, key-gated) |
| **0.5.1** | IMAP watch mode (`--watch`: interval polling, in-session dedup, auto-save) |
| **0.5.2** | Better company/one-liner extraction (body cues); growth-stage out-of-scope detection |
| **0.6.0** | Security-hardening release: SSRF guard, sink-enforced log redaction, LLM prompt-injection defense, restored retry/backoff, plaintext-IMAP refusal, CVE-floored deps + `pip-audit` in CI |
| **0.7.0** _(planned)_ | Pluggable enrichment providers (Crunchbase/Harmonic), queue export/digest |
| _superseded_ | (pre-pivot 0.2/0.3: `AsyncAngelListClient`, cert pinning, Pydantic models, pagination — dropped with the API client) |

---

### v0.2.0 — Deliberation Log (2026-04-11)

**Scope decisions:**

- **Test coverage first** — current coverage is ~60-70% despite 90% threshold in config; 5 of 8
  endpoints lack tests entirely. No new features ship until the threshold is genuinely met.
- **`NotFoundError(AngelListError)`** added for HTTP 404; previously fell through as generic
  `AngelListError`. Consistent `status_code` propagation across all raise sites.
- **Configurable timeout** exposed as `timeout: float = 30.0` on `AngelListClient.__init__`;
  currently hardcoded at 30 s inside `_get()`. Zero breaking change.
- **`AsyncAngelListClient`** backed by `httpx.AsyncClient` (new dependency: `httpx`). Mirrors all
  8 endpoints as `async def`. Shares `SecretRedactor`; introduces `AsyncRateLimiter` using
  `asyncio.Lock` instead of `threading.Lock`. Does NOT replace the sync client — additive only.
  Decision to include in v0.2.0 rather than defer: async is a core capability, not DX sugar.
- **Certificate pinning** — `HardenedSession(pin_fingerprints: list[str] | None = None)` verifies
  SHA-256 cert fingerprints post-handshake. `truststore` deferred to v0.3.0 (adds OS complexity,
  low demand).
- **PyPI publish workflow** — `.github/workflows/publish.yml`, triggered on `v*` tag push, uses
  `uv publish`. v0.2.0 is the first public PyPI release (not v0.1.0).

**Pydantic stance (v0.3.0 decision):**
- Default return type stays `dict[str, Any]` (zero extra dependencies).
- `AngelListClient(validate=True)` opts into Pydantic model returns; `pydantic >= 2.0` becomes an
  optional dependency under `[project.optional-dependencies]`.

**CLI target (v0.3.0 decision):**
- Primary audience: both analysts (ad-hoc queries) and CI pipelines (scripting).
- JSON output by default (pipe-friendly); `--format table` for human-readable display.
- Auth exclusively via `ANGELLIST_API_KEY` environment variable — no key ever passed on the
  command line.

### v0.2.0 — Pivot to deal-flow triage (2026-06-04)

**Why the pivot:** The legacy AngelList Startup/Funding Data API (`api.angel.co/1`)
that v0.1.0 wrapped has been shut down. AngelList today is fund/SPV back-office
infrastructure (SPVs, Rolling Funds, fund admin), not an open data API, and there
is no drop-in successor for the old `/startups`, `/funding`, `/users` endpoints.
A straight "swap the base URL" refactor is therefore impossible — the data source
is gone, not renamed.

The project's center of gravity moves from a *transport library* (a hardened API
client) to a *triage/DD pipeline* (ingest a deal → enrich → score → memo). The
Presidio hardening layer is retained and reused as infrastructure for outbound
enrichment calls.

**Decisions (deliberated with the requester):**

- **Intake = forwarded syndicate emails.** This is the deal flow an angel actually
  receives. Accepts both `.eml` files and pasted text. (Rejected: scraping
  AngelList — against ToS and no stable surface; a third-party data API — deferred
  until a paid source is in hand.)
- **Extraction = deterministic first, LLM fallback.** Regex/heuristics parse the
  obvious fields with zero dependencies; Claude is invoked only when
  `is_complete()` reports the parse is too thin. Keeps the common path keyless and
  reproducible while staying robust to messy email layouts.
- **Triage = hybrid (rules + LLM).** A deterministic, auditable rubric (six
  weighted dimensions + risk flags) does the scoring; Claude drafts the
  qualitative memo on top. The deterministic core ships first and runs without a
  key; the LLM layer is purely additive. Fits the "Presidio hardened" ethos of
  reproducible, inspectable results.
- **Form factor = CLI (`angeltriage`).** JSON by default option for pipelines;
  human-readable scorecard otherwise. Batch mode ranks by composite score. LLM
  auth exclusively via `ANTHROPIC_API_KEY` — never passed on the command line.
- **Claude integration.** Opus 4.8 via the Anthropic SDK; structured outputs for
  extraction, adaptive thinking, prompt caching on the frozen system prompts.
  `anthropic` is an optional `[llm]` extra; the templated memo fallback means
  `--memo` degrades gracefully with no key.

**Delivered in v0.2.0:**
- Email intake (`intake/email.py`) — deterministic `.eml`/text → `Deal`
- LLM extraction fallback + memo (`llm.py`, key-gated, optional dependency)
- Hardened website enrichment (`enrich/web.py`)
- Deterministic pre-seed/seed rubric (`triage/rubric.py`) + memo (`triage/memo.py`)
- Configurable rubric weights via JSON file (`config.py`, `angeltriage --weights`)
- End-to-end pipeline (`pipeline.py`) and `angeltriage` CLI (`cli.py`)
- Retained hardening primitives, extracted to `hardening.py`
- Test suite rewritten; coverage ≥ 90%; ruff clean
- Removed the dead `AngelListClient` and its endpoint methods

**`--weights` config decision:**
- **Format = JSON.** Dependency-free on Python 3.9+ (TOML would need `tomllib`,
  3.11+ only, or a new dependency) and matches the pipe-friendly CLI ethos.
- **Partial overrides merge over `DEFAULT_WEIGHTS`** — a user can bump one
  dimension (e.g. `{"team": 0.5}`) without re-specifying all five; this also
  guarantees `score_deal` always sees every dimension key.
- **Validation is strict and fails closed:** unknown dimensions, negative/
  non-numeric/boolean weights, non-object JSON, and an all-zero set all raise
  `WeightsConfigError`; the CLI maps it to exit code 2. Untrusted config never
  silently degrades the rubric.

---

### v0.3.0 — Deliberation Log (2026-06-04)

Delivered the four roadmap items for 0.3.0. Scope decisions:

- **CSV/batch intake (`intake/csv.py`).** Each row → one `Deal` via the same
  scoring path as emails. Headers are matched case-insensitively against an alias
  table so exports from different trackers work without remapping; money cells
  accept `$1.2M` / `1,200,000` / `500k`; founders split on `;`/`,`; rows with no
  company are skipped. The row's text is stuffed into `Deal.raw_text` so the
  rubric's keyword scan (credentials, traction) still has something to read.
- **Full rubric config (`--rubric`).** Introduced `RubricConfig` (weights, tier
  thresholds, cap ceilings, per-flag `risk_penalty`) in a new leaf module
  `rubric_config.py` to break a config↔rubric import cycle. `Scorecard` gained
  `tier_thresholds` and `risk_penalty` fields **with defaults equal to the prior
  built-ins**, so the change is backward compatible (existing callers and the
  `weights=` kwarg are unaffected). `--weights` and `--rubric` are mutually
  exclusive; both fail closed via `WeightsConfigError`.
- **"Per-flag deductions" interpretation.** Risk flags stay free-text strings;
  `risk_penalty` deducts a flat N points from the composite per flag (clamped to
  0–100). This delivers configurable downgrading without restructuring flags into
  coded categories — a smaller, lower-risk change that's still auditable.
- **HTML-email robustness.** Replaced the regex tag-stripper with an
  `html.parser`-based extractor that drops `<script>`/`<style>`/`<head>`,
  inserts line breaks at block boundaries, and decodes entities — more reliable
  than regex on real multipart HTML emails.
- **Enrichment fallbacks.** Website enrichment now tries `<meta description>` →
  `og:description` → `<title>` for the one-liner. Third-party data sources
  (Crunchbase/Harmonic) remain deferred to 0.4.0 (need paid access/keys).

**Delivered in v0.3.0:**
- `intake/csv.py` + `parse_csv`; `triage_csv` / `triage_deal` in the pipeline
- `rubric_config.py` (`RubricConfig`); `config.load_rubric_config`; `--rubric` CLI
- `Scorecard` configurable tiers + per-flag penalty (backward compatible)
- Robust HTML→text extraction; og/title enrichment fallbacks
- CLI dispatches `.csv` vs `.eml`; `--weights`/`--rubric` mutual exclusion
- Tests extended (122 total); coverage ~95%; ruff clean; version → 0.3.0

---

### v0.4.0 — Deliberation Log (2026-06-04)

Deliberated the two remaining roadmap items (persistence vs third-party
enrichment). Decision: **ship persistence; defer enrichment.**

**Scope decisions:**

- **Persistence is the 0.4.0 headline.** It's the highest-leverage next step
  (turns one-shot triage into a workflow), has **zero external dependencies**, and
  is fully testable. Third-party enrichment was explicitly deferred to 0.5.0: with
  no API keys available, building concrete providers would be untestable
  speculation. The provider-interface work waits until a key is in hand.
- **Backend = stdlib `sqlite3`.** Queryable (status/tier filters, ranking),
  robust, transactional, and dependency-free. Chosen over a JSONL file because the
  workflow needs filtered/ranked queries and per-row status updates, which SQL
  does cleanly.
- **Dedup identity = website domain, else normalized company name.** The same deal
  forwarded by multiple syndicates collapses to one row; `times_seen` tracks
  arrivals. Domain is the more reliable key (company-name spellings vary); the
  name fallback covers stealth/website-less deals. Documented limitation: two
  emails for the same company with *different* listed domains won't merge.
- **Status preserved on re-save.** Re-triaging refreshes the scorecard but never
  resets a human-set status (`passed` stays `passed`) — the store records workflow
  state, and re-ingestion must not clobber it. `first_seen` is preserved;
  `last_seen`/`times_seen` update.
- **CLI stays backward compatible.** Added `--save` / `--queue` / `--set-status` /
  `--db` as flags (not subcommands) so every existing invocation
  (`angeltriage deal.eml …`) keeps working unchanged. `inputs` became optional;
  mode is resolved as set-status → queue → triage, with a clear "nothing to do"
  error otherwise.
- **Store location.** `~/.angeltriage/deals.db` by default, overridable via `--db`
  or `ANGELTRIAGE_DB`. Local-only; no data leaves the machine.

**Delivered in v0.4.0:**
- `store.py` — `DealStore` (SQLite), `SavedDeal`, `dedup_key`, `STATUSES`,
  `default_db_path`; context-manager + upsert/list/get/set_status API
- CLI `--save` / `--queue` (with `--status`/`--tier` filters, `--json`) /
  `--set-status` / `--db`; backward-compatible flag-based modes
- Public exports: `DealStore`, `SavedDeal`, `DealStoreError`, `STATUSES`
- Tests extended (150 total); `store.py` at 100% line coverage; ruff clean;
  version → 0.4.0

---

### v0.5.0 (in progress) — IMAP intake (2026-06-04)

First slice of 0.5.0. Triggered by a real question — "can you fetch an email from
my iPhone's Mail app / read IMAP creds from Keychain?" The honest answer (the
tool runs in a Linux process, not on the phone; iOS Keychain isn't externally
readable) pointed at IMAP polling as the durable intake path.

**Scope decisions:**

- **Credentials from the environment only.** `IMAP_HOST` / `IMAP_USER` /
  `IMAP_PASSWORD` (+ optional `IMAP_PORT` / `IMAP_FOLDER` / `IMAP_SSL`). Never
  accepted on the command line and never logged — consistent with the
  `ANTHROPIC_API_KEY` stance. Docs steer users to **app-specific passwords** and
  warn against putting mail passwords in shared/remote shells.
- **Read-only mailbox select.** Messages are not marked read, so re-polling
  re-fetches; the deal queue's dedup makes repeated polls idempotent. (A
  `mark-seen` option can come later if wanted.)
- **Testable without a network or a real mailbox.** `fetch_imap` takes a
  `connection_factory` so the whole flow is unit-tested against a `FakeIMAP`
  stand-in; `imaplib` is stdlib, so no new dependency.
- **Reuses the existing raw-bytes path.** `parse_email` already accepts RFC822
  bytes, so `triage_imap` is a thin fetch→`triage_email` loop; each message flows
  through the same deterministic-first / LLM-fallback pipeline.
- **Enrichment providers still deferred.** The rest of 0.5.0 (Crunchbase/Harmonic)
  remains blocked on having a provider key to build and test against.

**Delivered:**
- `intake/imap.py` — `fetch_imap`, `imap_config_from_env`, `ImapConfig`,
  `FetchedMessage`, `ImapError`; `pipeline.triage_imap`
- CLI `--imap` (+ `--imap-folder` / `--imap-all` / `--imap-from` / `--imap-limit`)
- Public exports for the IMAP surface
- Tests extended (174 total); ruff clean; version → 0.5.0

---

### v0.5.1 — IMAP watch mode (2026-06-04)

Follow-on to IMAP intake: a polling loop so the mailbox is checked on an interval
and new deals are auto-triaged into the queue — a hands-off inbox → queue pipeline.

**Scope decisions:**

- **In-session dedup by `Message-ID`.** Because the mailbox is selected read-only,
  an UNSEEN search returns the same messages every cycle until they're read in the
  mail client. The loop tracks handled message identities (`Message-ID`, or a
  content hash when absent) so an email is triaged **once per session**, not every
  poll — avoiding wasted work and (if enabled) repeated LLM calls. Across restarts
  the store's deal-identity dedup still prevents duplicate rows.
- **First-cycle fail-fast, later-cycle tolerance.** A misconfiguration (bad creds /
  folder) surfaces immediately on cycle 1 (`ImapError` propagates → CLI exit 2). A
  long-running watcher shouldn't die on a transient network blip, so subsequent
  cycles route errors to an `on_error` callback and keep polling.
- **Injectable clock + connection.** `watch(...)` takes a `sleeper` and the
  fetch takes a `connection_factory`, so the whole loop is unit-tested with no real
  time or network (bounded by `max_cycles`).
- **Cron-friendly.** `--max-cycles 1` makes a single pass, so a scheduled one-liner
  is a valid alternative to a long-running process.
- **Reuses everything.** The loop is `fetch_imap` → `triage_email` → `store.save`;
  no new transport, no new dependency (stdlib `email`/`hashlib`/`time`).

**Delivered:**
- `watch.py` — `watch`, `poll_once`, `message_identity`, `PollResult`
- CLI `--watch` (+ `--interval`, `--max-cycles`); shared `_resolve_config` /
  `_make_llm` / `_imap_config` helpers factored out of the triage path
- Public exports for the watch surface
- Tests extended (186 total); `watch.py` at 100% line coverage; ruff clean;
  version → 0.5.1

---

### v0.5.2 — Extraction hardening + out-of-scope detection (2026-06-05)

Driven by a real sample run (a Mana Ventures syndicate email for **Campus**, a
growth-stage edtech deal). Two weaknesses surfaced and were fixed.

**(b) Deterministic company / one-liner extraction.** The ornate subject
("Confidential + $120k+ Filled | … 8VC backed Campus ($40M ARR today) - new way
to go to college") made the subject-splitting heuristic return junk as the
company, and the one-liner grabbed the signature block.

- Company extraction now tries **high-precision body phrasings first** — "in our
  X deal", "investing in X", "X is a/an…", "X builds/operates…", "backed X" — and
  only falls back to the subject heuristic when none match. The company-name regex
  excludes internal `.` so a match stops at a sentence boundary.
- One-liner extraction now prefers the company's **own pitch sentence** ("Campus
  is a new way to go to college…") and otherwise skips greeting/signature lines.
- The Campus email is captured as `tests/fixtures/deal_growth.eml`.

**(c) Growth-stage (out-of-scope) detection.** The rubric is tuned for
pre-seed/seed; scoring a $40M-ARR / $20M venture round against it produced a
misleading "Track 56.5".

- `detect_stage_scope(deal)` flags later-stage signals: explicit Series A/B/C,
  ARR/revenue ≥ $5M (matched near ARR/revenue/MRR, not the largest dollar figure
  anywhere — so a seed deal's $10M cap doesn't false-positive), or a
  priced/venture round with a large round size.
- `Scorecard` gained `scope_note`; when set, `tier` reports **"Out of scope"** and
  CLI/memo/JSON surface the note. The composite is still computed but marked
  indicative. Defaults keep existing behavior (backward compatible).

**Delivered:**
- Reworked `_extract_company` / `_extract_one_liner` in `intake/email.py`
- `triage/rubric.detect_stage_scope` + `_max_money_near`; `Scorecard.scope_note`
- CLI + templated-memo rendering of the scope note; `deal_growth.eml` fixture
- Verified: Campus → company "Campus", real one-liner, "Out of scope"; Nimbus
  (real pre-seed) still "Strong lead 83.0", not flagged
- Tests extended (202 total); ruff clean; version → 0.5.2

### v0.6.0 — Security-hardening release (2026-06-06)

A pre-PyPI security audit of the post-pivot toolkit (now a deal-flow triage tool
ingesting untrusted email/CSV/IMAP and fetching attacker-influenced URLs) found
that several commitments in SECURITY.md/PRESIDIO-REQ.md had drifted from the code
during the pivot, plus CVE-vulnerable dependency floors. 0.6.0 closes all of them
before the first PyPI publish.

**Findings remediated:**

- **SSRF (HIGH).** `enrich_from_website` fetched the email-supplied `deal.website`
  with no address validation, and the "HTTP→HTTPS upgrade" actually helped an
  attacker reach internal HTTPS targets. Added `assert_public_host` + an
  `SSRFError`-raising guard in `HardenedSession.request`: IP literals and *every*
  resolved address must be public; non-HTTP(S) schemes refused. Unresolvable hosts
  pass through (no address to attack; connection fails naturally). *Residual:*
  DNS-rebinding by an attacker controlling authoritative DNS — documented in
  SECURITY.md with the egress-restriction guidance.
- **Log redaction not enforced at the sink (MED).** `SecretRedactor` was only
  called manually in one spot. Added `RedactingFilter` (a `logging.Filter`),
  installed on the `presidio_angellist` logger at import via `install_log_redaction`
  (idempotent), so every record is scrubbed before any handler sees it. Broadened
  the `sk-ant-*` pattern to redact the whole token.
- **LLM prompt injection (MED).** Untrusted deal text is now fenced in a
  `<untrusted_deal_content>` block (nested delimiters stripped) and both system
  prompts instruct the model to treat that content as data, never instructions.
- **Retry/backoff/429 dropped during the pivot (MED).** Re-implemented on
  `HardenedSession`: exponential backoff on connection errors/timeouts and HTTP
  429/502/503/504, honouring `Retry-After` (delta-seconds or HTTP-date).
- **Plaintext IMAP credential transport (LOW).** `IMAP_SSL=0` now refuses to connect
  (credentials would be sent in clear) unless `IMAP_ALLOW_INSECURE=1` is set, which
  also logs a loud warning.
- **Weak DH ciphers / missing dep audit (LOW).** Cipher list narrowed to ephemeral-EC
  only (matching this doc). Added `pip-audit` to `[dev]` and a CI step; pinned
  `urllib3>=2.7.0` (PYSEC-2026-141/142), `idna>=3.15` (CVE-2026-45409),
  `requests>=2.32.0`.

**Delivered:**
- `hardening.py`: `assert_public_host`/`SSRFError`, `RedactingFilter`/
  `install_log_redaction`, retry/backoff + `Retry-After` parsing, EC-only ciphers
- `llm.py`: `_wrap_untrusted` + injection-guarded system prompts
- `intake/imap.py`: plaintext refusal with explicit opt-in
- `pyproject.toml`: CVE-floored deps, `pip-audit` dev dep; `ci.yml`: `pip-audit` step
- Tests extended (231 total); coverage ~96%; ruff clean; `pip-audit` clean;
  version → 0.6.0

## SDLC

These requirements are delivered under the family-wide Presidio SDLC:
<https://github.com/presidio-v/presidio-hardened-docs/blob/main/sdlc/sdlc-report.md>.
