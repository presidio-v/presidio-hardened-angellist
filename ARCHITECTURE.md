# Architecture

This document describes the high-level design of `presidio-hardened-angellist`: its
components, how data flows through them, and the trust boundaries the project is
built to enforce. For the security requirements and threat model that motivate
this design, see [SECURITY.md](SECURITY.md) and the assurance case in
[ASSURANCE.md](ASSURANCE.md).

## Overview

`presidio-hardened-angellist` is a Python library and CLI (`angeltriage`) that turns
forwarded AngelList/syndicate deal emails into a structured `Deal`, scores it against a
deterministic pre-seed/seed rubric, and optionally writes an investment memo. It runs on
the analyst's own machine; there is no server component and no hosted service. The core
triage path is pure computation over in-memory dataclasses — it makes no network calls and
needs no API key. Every network-touching capability (website enrichment, LLM extraction and
memo, IMAP intake, SMTP notification) is opt-in and separately gated. State is optional: the
`--save` deal queue is a local SQLite file that never leaves the machine. The design stance
is that **everything arriving from a deal email is data, never instructions** — it is parsed
into typed fields and is never executed, rendered, interpolated into a shell or SQL string,
or allowed to steer an LLM.

## Components

Listed in dependency order — primitives first, orchestration last.

| Component | Responsibility |
|---|---|
| `hardening.py` | The security primitives: `HardenedSession` (TLS 1.2+, EC-ephemeral ciphers, cert verification, HTTP→HTTPS upgrade, retry with backoff honouring `Retry-After`), `assert_public_host` (SSRF guard), `SecretRedactor` / `RedactingFilter` (secret scrubbing installed on the package logger at import), `RateLimiter` (per-host). |
| `models.py` | Pure data: `Deal`, `Founder`, `Scorecard`, `DimensionScore`, `TriageResult`. No I/O, no behaviour beyond field derivation. |
| `intake/email.py` | Deterministic extraction of a `Deal` from RFC822 bytes, an `.eml` path, or pasted text. Prefers `text/plain`; falls back to an `html.parser` extractor that drops `<script>`/`<style>`/`<head>`. |
| `intake/csv.py` | One `Deal` per row of an operator-supplied CSV, via the stdlib `csv` module. |
| `intake/imap.py` | Read-only IMAP fetch of deal messages. Credentials come from `IMAP_*` environment variables only; TLS is the default and plaintext is refused unless explicitly overridden. |
| `enrich/web.py` | Opt-in (`--enrich`) fetch of the company website through `HardenedSession` to backfill a one-liner. Failures are non-fatal. |
| `llm.py` | Optional LLM extraction and memo generation, against either the Anthropic SDK or an operator-configured OpenAI-compatible endpoint. Wraps untrusted deal text in a delimited block and instructs the model to treat it as data. |
| `triage/rubric.py` | The deterministic scorecard: five weighted dimensions (team, market, traction, terms, syndicate) → composite and tier. No network, no model. |
| `triage/memo.py` | The templated memo used when no LLM backend is configured, so `--memo` always works. |
| `config.py`, `rubric_config.py` | Strict validation of operator-supplied `--weights` / `--rubric` JSON. Rejects unknown dimensions, non-numeric, negative, boolean, and all-zero weight sets. |
| `store.py` | The SQLite deal queue: dedup by website domain or normalised company name, workflow status, ranking. All SQL is parameterized. |
| `notify.py` | Optional SMTP notification of new triage results over implicit TLS or STARTTLS, with credentials from the environment only. |
| `pipeline.py` | Composes intake → (LLM fallback) → enrichment → scoring → memo into `triage_email` / `triage_csv` / `triage_deal` / `triage_imap`. |
| `watch.py` | The `--watch` polling loop over IMAP, with per-message dedup against the store. |
| `cli.py` | Argument parsing, output rendering (human and `--json`), and exit codes. |

## Data / processing flow

A single deal moves through the pipeline in this order:

1. **Intake** — a `.eml` file, raw RFC822 bytes, pasted text, a CSV row, or an IMAP message
   is parsed into a `Deal` by the deterministic extractor.
2. **Completeness check** — `is_complete()` decides whether the deterministic parse
   recovered a company name plus enough economically meaningful fields.
3. **LLM fallback** *(opt-in, only when incomplete)* — if a backend is configured, the deal
   text is wrapped as untrusted content and sent for structured extraction. With no key or
   no backend, this step is skipped and the deterministic result stands.
4. **Enrichment** *(opt-in)* — the extracted company URL is fetched through
   `HardenedSession` to backfill a one-liner.
5. **Scoring** — the deterministic rubric produces per-dimension scores, a composite, and a
   tier. This step is always reached.
6. **Memo** *(opt-in)* — LLM-written if a backend is available, templated otherwise.
7. **Persistence and notification** *(opt-in)* — `--save` writes to the SQLite queue;
   `--notify` emails the result.

**Failure posture.** The two postures are deliberately different and the distinction is part
of the contract:

- **Security controls fail closed.** A non-HTTPS scheme, a host that resolves to a
  non-public address, an invalid weights/rubric file, or a plaintext IMAP connection without
  an explicit override raises and stops that operation. There is no silent downgrade path.
- **Optional enrichment fails open, additively.** A failed website fetch, an unavailable LLM
  backend, or a failed notification is logged and skipped; triage still produces a
  deterministic score. Enrichment only ever *adds* to a `Deal`.

**Load-bearing ordering, and where it lives.** The SSRF guard and the HTTPS upgrade run
inside `HardenedSession.send` *before* each dispatch, so no code path can reach the network
with an unchecked host. `send` is the correct seam and `request` is not: `requests` resolves
redirects in `Session.send` → `resolve_redirects`, which calls `send()` per hop and never
re-enters `request()`, so a guard in `request` would validate the first hop and follow every
attacker-chosen `Location` unchecked. That was the defect through 0.7.2. The untrusted-content wrapping in `llm.py` is applied to the
deal text before it becomes a user turn, not afterwards. Both orderings are part of the
contract, not an implementation detail.

## Trust boundaries

| Boundary | Kind | Control |
|---|---|---|
| **Forwarded email / CSV → intake** | Input validation | Parsed with the stdlib `email` and `csv` modules; HTML is stripped by an `html.parser` subclass that drops `<script>`, `<style>`, `<head>`, `<title>`. Content only populates dataclass fields — it is never executed, rendered, or used to build shell, SQL, or filesystem operations. |
| **Deal-derived URL → public internet** | Egress | `HardenedSession`: HTTP is upgraded to HTTPS and any other scheme is refused; TLS 1.2+ with EC-ephemeral ciphers and mandatory certificate verification; `assert_public_host` refuses literals and resolved addresses that are loopback, private, link-local (including `169.254.169.254`), reserved, multicast, or unspecified, plus ambiguous numeric notations; per-host rate limiting; responses truncated at 512 KiB. Enforced in `send()` so **every redirect hop is validated**, with depth capped at 5. Off by default (`--enrich`). |
| **Deal text → LLM provider** | Egress + injection | The deal text is wrapped in a `<untrusted_deal_content>` block with nested delimiters stripped, and the system prompt states that the block is data and never instructions. Off unless a backend is configured; the API key is read from the environment, never a CLI argument, and is covered by the `sk-ant-*` redaction rule. |
| **Operator-configured LLM endpoint → local model server** | Egress (documented exception) | `ANGELTRIAGE_LLM_BASE_URL` selects an OpenAI-compatible backend reached with plain `requests`, **not** `HardenedSession`, because such endpoints are typically loopback and the SSRF guard would correctly refuse them. This address is operator-supplied and trusted by configuration; it is never derived from deal content. |
| **Mail server → IMAP intake** | Credential + input | `IMAP_HOST` / `IMAP_USER` / `IMAP_PASSWORD` are read from the environment only, never the command line, and are never logged. The mailbox is opened read-only. IMAP-over-TLS is the default; plaintext is refused unless `IMAP_ALLOW_INSECURE=1` is set explicitly, which also warns. |
| **Triage result → SMTP recipients** | Egress | `ANGELTRIAGE_SMTP_*` credentials come from the environment only; the connection uses implicit TLS (465) or STARTTLS. Deal text — which is attacker-influenced — is delivered to the configured recipients, so that list must be trusted. |
| **Process → local deal store** | Persistence | SQLite at `~/.angeltriage/deals.db` (overridable via `--db` / `ANGELTRIAGE_DB`). All statements are parameterized. The store holds deal data at rest and no secrets or API keys, and never leaves the machine; protect it with filesystem permissions if the deal data is sensitive. |
| **Process → log sinks** | Egress | A `RedactingFilter` is attached to the `presidio_angellist` logger at import time, so bearer tokens, `access_token=` / `api_key=` parameters, `Authorization:` headers, and `sk_live_*` / `sk-ant-*` keys are scrubbed at the sink for every record — not only at call sites that redact by hand. |
