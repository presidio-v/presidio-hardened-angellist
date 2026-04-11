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
- **HTTP → HTTPS auto-upgrade** — Insecure `http://` base URLs silently upgraded to HTTPS
- **API key / secret redaction** — Bearer tokens, `sk_live_*` keys, `access_token=`,
  `api_key=`, and `Authorization:` headers are scrubbed from all log output before
  reaching any log sink
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

| Version | Planned features |
|---|---|
| **0.1.0** | Initial scaffold — see above |
| **0.2.0** | Test coverage to 90%+, `NotFoundError`, configurable timeout, `AsyncAngelListClient` (httpx), certificate pinning, PyPI publish workflow |
| **0.3.0** | Pydantic response models (opt-in via `validate=True`), pagination generators (`iter_startups`, `iter_users`), CLI entrypoint (JSON default + `--format table`), optional `truststore` integration |

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
