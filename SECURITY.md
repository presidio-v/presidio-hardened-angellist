# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.5.x   | ✅ Yes    |
| 0.4.x   | ✅ Yes    |
| 0.3.x   | ✅ Yes    |
| 0.2.x   | ✅ Yes    |
| 0.1.x   | ❌ No (wrapped the now-defunct AngelList API) |

## Reporting a Vulnerability

Please report security vulnerabilities by opening a private GitHub Security Advisory
(via the "Security" tab → "Report a vulnerability") rather than a public issue.

Include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You will receive an acknowledgement within 5 business days. We aim to release a patch
within 30 days of a confirmed vulnerability.

## Security Features

The Presidio hardening layer (`HardenedSession`) is applied to **every outbound
enrichment request** the toolkit makes:

- **TLS 1.2+ enforcement** — TLS 1.0 and 1.1 are rejected. Strong cipher suites are
  enforced. Certificate verification is always enabled.
- **HTTP → HTTPS upgrade** — Insecure HTTP URLs are automatically upgraded.
- **Secret / API key redaction** — Bearer tokens and `sk_live_*` / `sk-ant-*` keys
  are scrubbed from all log output before they reach any log sink.
- **Per-host rate limiting** — Prevents accidental DoS of enrichment hosts with a
  configurable req/s cap.
- **Structured security-event logging** — Every hardening action (HTTPS upgrade,
  TLS error, rate-limit wait) emits a structured log entry via the
  `presidio_angellist` logger.

## Data Handling & Trust Boundaries

This is a deal-flow triage tool, so it processes untrusted input. The relevant
boundaries:

- **Forwarded emails and CSVs are untrusted.** Deal emails are parsed with the
  standard library `email` module (and an `html.parser`-based extractor that drops
  `<script>`/`<style>`); CSVs are parsed with the standard `csv` module. Their
  content is **never executed, rendered, or used to construct shell/SQL/file-system
  operations** — it only populates `Deal` dataclasses.
- **Network enrichment is opt-in and bounded.** `--enrich` fetches the **company
  website URL extracted from the email** through `HardenedSession`. Because that
  URL originates from untrusted input, enrichment is off by default; when enabled,
  TLS verification and HTTPS upgrade still apply. Operators handling emails from
  low-trust senders should leave `--enrich` off or run it from an egress-restricted
  network, as the fetched URL is attacker-influenced (SSRF surface).
- **The `--weights` config fails closed.** The rubric-weights JSON file is strictly
  validated (`config.load_weights`): unknown dimensions, negative / non-numeric /
  boolean values, non-object JSON, and an all-zero set are rejected with a clear
  error rather than silently degrading scoring.
- **LLM calls are opt-in and key-gated.** The Claude extraction/memo steps run only
  when `ANTHROPIC_API_KEY` is set and the optional `[llm]` extra is installed. The
  key is read from the environment — **never passed on the command line** — and is
  covered by the `sk-ant-*` redaction rule. Deal content is sent to the Anthropic
  API only when these steps are explicitly invoked.
- **The deal queue is a local store.** `--save` writes triaged deals to a local
  SQLite file (`~/.angeltriage/deals.db` by default, parameterized via `--db` /
  `ANGELTRIAGE_DB`). It contains deal data at rest, holds **no secrets/API keys**,
  and never leaves the machine. Protect it with normal filesystem permissions if
  the deal data is sensitive; queries are fully parameterized (no SQL injection).
- **IMAP credentials come from the environment only.** `--imap` reads
  `IMAP_HOST` / `IMAP_USER` / `IMAP_PASSWORD` (and optional `IMAP_PORT` /
  `IMAP_FOLDER` / `IMAP_SSL`) from the environment — **never** from the command
  line, and they are never logged. Use an **app-specific password**, keep it in a
  local `.env` / shell profile, and don't run `--imap` in a shared or remote shell
  where the mail password would be exposed. The mailbox is opened read-only.

## Dependency Management

- Dependabot is configured to keep all dependencies up to date.
- CodeQL analysis runs on every push and pull request.
- All changes require passing CI (pytest + ruff) before merge.

## Responsible Disclosure

We follow [coordinated vulnerability disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure).
We appreciate security researchers who report issues responsibly and will
credit them in our release notes (with permission).

## Software Development Lifecycle

This repository is developed under the Presidio hardened-family SDLC. The public report
— scope, standards mapping, threat-model gates, and supply-chain controls — is at
<https://github.com/presidio-v/presidio-hardened-docs/blob/main/sdlc/sdlc-report.md>.
