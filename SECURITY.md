# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.6.x   | ✅ Yes (latest 0.6.0) |
| 0.5.x   | ⚠️ Superseded — upgrade to 0.6.x (SSRF + CVE fixes) |
| 0.4.x   | ⚠️ Superseded — upgrade to 0.6.x |
| 0.3.x   | ⚠️ Superseded — upgrade to 0.6.x |
| 0.2.x   | ⚠️ Superseded — upgrade to 0.6.x |
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

- **TLS 1.2+ enforcement** — TLS 1.0 and 1.1 are rejected. Only ephemeral-EC cipher
  suites (`ECDH+AESGCM` / `ECDH+CHACHA20`) are offered; non-EC finite-field DH is
  excluded. Certificate verification is always enabled.
- **HTTP → HTTPS upgrade** — Insecure HTTP URLs are automatically upgraded; non-HTTP(S)
  schemes are refused outright.
- **SSRF guard** — Before any outbound request, the target host is checked (and
  resolved, if a name): requests to loopback, private (RFC 1918), link-local
  (incl. the `169.254.169.254` cloud-metadata endpoint), reserved, multicast, and
  unspecified addresses are refused with an `SSRFError`. This bounds the
  attacker-influenced enrichment URL. *Residual:* a DNS-rebinding attacker who
  controls authoritative DNS can still race the resolve/connect window; run
  `--enrich`/`--watch` from an egress-restricted network when handling low-trust
  senders.
- **Secret / API key redaction** — A `RedactingFilter` is installed on the
  `presidio_angellist` logger at import, so Bearer tokens, `access_token=` /
  `api_key=` query params, and `sk_live_*` / `sk-ant-*` keys are scrubbed from
  **every** log record at the sink — not just the call sites that redact manually.
- **Retry with exponential backoff** — Transient failures (connection errors,
  timeouts, HTTP 429/502/503/504) are retried with exponential backoff, honouring a
  `Retry-After` header (delta-seconds or HTTP-date) when present.
- **Per-host rate limiting** — Prevents accidental DoS of enrichment hosts with a
  configurable req/s cap.
- **Structured security-event logging** — Every hardening action (HTTPS upgrade,
  SSRF refusal, TLS error, retry, rate-limit wait) emits a structured log entry via
  the `presidio_angellist` logger.

## Data Handling & Trust Boundaries

This is a deal-flow triage tool, so it processes untrusted input. The relevant
boundaries:

- **Forwarded emails and CSVs are untrusted.** Deal emails are parsed with the
  standard library `email` module (and an `html.parser`-based extractor that drops
  `<script>`/`<style>`); CSVs are parsed with the standard `csv` module. Their
  content is **never executed, rendered, or used to construct shell/SQL/file-system
  operations** — it only populates `Deal` dataclasses.
- **Network enrichment is opt-in and SSRF-guarded.** `--enrich` fetches the
  **company website URL extracted from the email** through `HardenedSession`.
  Because that URL is attacker-influenced, enrichment is off by default and, when
  enabled, the SSRF guard (above) refuses any target resolving to a non-public
  address — so a crafted `http://169.254.169.254/…` or `http://10.0.0.5/…` URL is
  blocked, not fetched. The residual DNS-rebinding risk means operators handling
  low-trust senders should still prefer an egress-restricted network.
- **The `--weights` config fails closed.** The rubric-weights JSON file is strictly
  validated (`config.load_weights`): unknown dimensions, negative / non-numeric /
  boolean values, non-object JSON, and an all-zero set are rejected with a clear
  error rather than silently degrading scoring.
- **LLM calls are opt-in, key-gated, and injection-hardened.** The Claude
  extraction/memo steps run only when `ANTHROPIC_API_KEY` is set and the optional
  `[llm]` extra is installed. The key is read from the environment — **never passed
  on the command line** — and is covered by the `sk-ant-*` redaction rule. Because
  deal text is untrusted, it is wrapped in a delimited `<untrusted_deal_content>`
  block (with any nested delimiter stripped) and the system prompt instructs the
  model to treat that content strictly as data, never as instructions — a
  prompt-injection defense. Residual prompt-injection risk is inherent to LLMs;
  treat generated memos as advisory, not authoritative.
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
  Connections use IMAP-over-TLS by default; **plaintext IMAP is refused** (it would
  send the password in clear) unless the operator explicitly sets
  `IMAP_ALLOW_INSECURE=1`, which also emits a loud warning. `--watch` (continuous
  polling) keeps those env-sourced credentials in the long-running process's memory
  for its lifetime — run it on a host you control.

## Dependency Management

- Dependabot is configured to keep all dependencies up to date.
- CodeQL analysis runs on every push and pull request.
- `pip-audit` runs in CI on every push and pull request and fails the build on any
  known-vulnerable dependency.
- Runtime dependency floors are pinned above known CVEs (`urllib3>=2.7.0`,
  `idna>=3.15`, `requests>=2.32.0`).
- All changes require passing CI (pytest + ruff + pip-audit) before merge.

## Responsible Disclosure

We follow [coordinated vulnerability disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure).
We appreciate security researchers who report issues responsibly and will
credit them in our release notes (with permission).

## Software Development Lifecycle

This repository is developed under the Presidio hardened-family SDLC. The public report
— scope, standards mapping, threat-model gates, and supply-chain controls — is at
<https://github.com/presidio-v/presidio-hardened-docs/blob/main/sdlc/sdlc-report.md>.
