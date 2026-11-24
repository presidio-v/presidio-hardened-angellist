# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.8.x   | ✅ Yes (latest) |
| 0.7.3   | ✅ Yes |
| 0.7.0 – 0.7.2 | ⚠️ Upgrade to 0.7.3 — affected by the redirect-SSRF defect fixed in 0.7.3 (see below) |
| 0.6.x   | ⚠️ Upgrade to 0.7.3 — same redirect-SSRF defect |
| 0.5.x   | ⚠️ Superseded — upgrade to 0.7.x (SSRF + CVE fixes) |
| 0.4.x   | ⚠️ Superseded — upgrade to 0.7.x |
| 0.3.x   | ⚠️ Superseded — upgrade to 0.7.x |
| 0.2.x   | ⚠️ Superseded — upgrade to 0.7.x |
| 0.1.x   | ❌ No (wrapped the now-defunct AngelList API) |

## Reporting a Vulnerability

Please report security vulnerabilities **privately**. Do not open a public issue for a
suspected vulnerability.

- Preferred: open a private
  [GitHub Security Advisory](https://github.com/presidio-v/presidio-hardened-angellist/security/advisories/new)
  (repository "Security" tab → "Report a vulnerability").
- Alternatively, email security@presidio-group.eu.

Include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You will receive an acknowledgement within 5 business days. We aim to release a patch
within 30 days of a confirmed vulnerability, and will keep you updated on progress until
the issue is resolved or dismissed with a rationale.

**Credit.** We credit reporters of valid vulnerabilities by name in the published GitHub
Security Advisory and in the `CHANGELOG.md` entry for the fix, unless the reporter asks to
remain anonymous.

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
  unspecified addresses are refused with an `SSRFError`. Hosts written in an
  alternative numeric notation that does not parse strictly as an IP (`0177.0.0.1`,
  `0x7f.0.0.1`, `2130706433`) are refused too, since the resolver's reading of them is
  platform-dependent, and IPv6 zone ids and brackets are stripped before the check.
  **The check runs on every hop, including redirects** — it is enforced in
  `HardenedSession.send`, which `requests` calls for each redirect it resolves, and
  redirect depth is capped at 5. Enforcing it only on the first request was the
  redirect-SSRF defect present through 0.7.2 and fixed in 0.7.3; see the CHANGELOG.
  *Residual:* a DNS-rebinding attacker who controls authoritative DNS can still race
  the resolve/connect window; run `--enrich`/`--watch` from an egress-restricted
  network when handling low-trust senders.
- **Bounded enrichment reads** — An enrichment response is streamed and truncated at
  512 KiB, and only textual content types are scanned, so a hostile site cannot
  exhaust memory with a huge body.
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
- **LLM calls are opt-in, key-gated, and injection-hardened.** The
  extraction/memo steps run only when an LLM backend is configured. With Anthropic,
  `ANTHROPIC_API_KEY` is read from the environment — **never passed on the command
  line** — and covered by the `sk-ant-*` redaction rule. Because deal text is
  untrusted, it is wrapped in a delimited `<untrusted_deal_content>` block (with any
  nested delimiter stripped) and the system prompt instructs the model to treat that
  content strictly as data, never as instructions. Residual prompt-injection risk is
  inherent to LLMs; treat generated memos as advisory, not authoritative.
- **Local/self-hosted LLM endpoints bypass the SSRF guard by design.** Setting
  `ANGELTRIAGE_LLM_BASE_URL` selects an OpenAI-compatible backend that talks plain
  `/v1/chat/completions`. These endpoints are typically loopback (`127.0.0.1`),
  which the enrichment SSRF guard correctly refuses — so the LLM client uses a
  direct `requests` call instead of `HardenedSession`. This is safe because the
  endpoint is an **explicitly operator-configured, trusted address**, not a value
  derived from untrusted deal content. Point it only at a model server you control.
- **SMTP notification credentials are environment-only.** `--notify` reads
  `ANGELTRIAGE_SMTP_*` (host/port/user/password/from) and `ANGELTRIAGE_NOTIFY_TO`
  from the environment — never the command line — and connects over implicit TLS
  (port 465) or STARTTLS. Deal data (which may include attacker-influenced text) is
  emailed to the configured recipients only; keep that list trusted.
- **The deal queue is a local store.** `--save` writes triaged deals to a local
  SQLite file (`~/.angeltriage/deals.db` by default, parameterized via `--db` /
  `ANGELTRIAGE_DB`). It contains deal data at rest, holds **no secrets/API keys**,
  and never leaves the machine; queries are fully parameterized (no SQL injection).
  A database this tool creates is given mode `0o600`, and a directory it creates
  `0o700`, so deal JSON, memos, founder names, and commercial terms are not
  world-readable on a shared host. **A pre-existing file is left exactly as you set
  it** — if your store was created by 0.7.2 or earlier, tighten it once by hand:
  `chmod 600 ~/.angeltriage/deals.db`. There is no encryption at rest.
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

### Portfolio digest

`angeltriage digest` (0.8.0+) handles the investor's own portfolio, which is more
sensitive than inbound deal mail. Its controls:

- **LaTeX injection.** Company names and leads (from the CSV), editorial text (from
  content JSON, possibly LLM-drafted), gate labels and brand text are all untrusted.
  Each is escaped before it reaches the document: `\ { } $ & # ^ _ ~ % [ ] < > | "`
  are replaced by their text equivalents and control/format characters are dropped.
  Link targets must be `http`/`https`, are percent-encoded, and keep only `\%`, `\#`,
  `\&` as escapes, so `javascript:`, `file:` and `run:` links never appear. Brand fonts
  must match `[A-Za-z0-9 .-]` and colours must be 6-digit hex.
- **Fail-closed pre-flight.** Before TeX runs, the document body is scanned for
  primitives the templates never emit (`\input`, `\include`, `\write`, `\openin`,
  `\openout`, `\immediate`, `\catcode`, `\csname`, `\def`, `\let`, `\directlua`,
  `^^`, …). A hit aborts the build: if one appears, escaping was bypassed.
- **No shell escape.** `xelatex` runs with `-no-shell-escape` (and `shell_escape=f`), so
  `\write18` can never execute a command regardless of the local `texmf.cnf`.
  `openout_any=p` stops TeX writing outside its job directory; `openin_any=p` refuses
  dot-files. Note: on current TeX Live, `openin_any=p` does **not** stop reading an
  absolute path, which is why the escaping and the pre-flight scan are the primary
  controls. The job runs in a fresh temporary directory with a minimal environment,
  fixed arguments (no shell), and a timeout.
- **Payload minimisation (refresh).** The optional advisor refresh sends the model only
  the company name, its sector/market and stage labels, and prior editorial text after
  removing every money amount, multiple, lead, fund vehicle, investing entity and any
  operator-listed term (`--redact`, `refresh_options.redact_terms`, the brand name). The
  serialized request is then re-checked against every amount and name in the whole
  export; a match skips that company (`PayloadLeakError`). Tickets, caps, valuations,
  marks, leads and the investor's identity never leave the machine. Web content returned
  by the model is treated as untrusted text: it is coerced to the content schema,
  URLs are limited to `http(s)`, and it is escaped like everything else. Drafts go to
  `<content>.draft.json`; the approved content file is never written.
- **Confidential output stays local.** PDFs, `.tex` sources and drafts are written with
  mode `0600`. They hold tickets, caps and leads and are marked with the configured
  classification (default `TLP:AMBER`). The scheduled run's email notice lists file
  names only; attaching PDFs requires `attach_pdf = true`. Keep `out_dir` off shared
  and synced folders you do not control.
- **Locked estimates and portfolio content** are private runtime inputs. Their text
  (events, method, segment verdicts, source labels) is escaped like all other content,
  source links are limited to `http(s)`, and the estimates file is validated strictly.
  Estimates are never sent to a model; the advisor refresh payload is unchanged.
- **No private data in the repository.** Brand, gate parameters, editorial content and
  the export are runtime inputs; the repository ships only neutral examples
  (`contrib/digest/`) and synthetic fixtures.

For the consolidated assurance case — the threat model, the trust boundaries, the argument
that secure design principles are applied, and how common implementation weaknesses are
countered — see [ASSURANCE.md](ASSURANCE.md). For components and the processing flow, see
[ARCHITECTURE.md](ARCHITECTURE.md).

## Verifying Releases and Obtaining Public Signing Keys

Release artefacts and git tags are signed. There is no key to fetch by hand for artefact
verification; the trusted identities are described below.

- **Release artefacts** are verified with Sigstore-backed build provenance. The trusted
  identity is the repository's OIDC signer:

  ```bash
  gh attestation verify <artefact> --repo presidio-v/presidio-hardened-angellist
  ```

- **Git release tags** are SSH-signed with the organisation's release signing key, which is
  registered as a signing key on the maintainer's GitHub account, so each release tag shows
  as **Verified** on the Releases page and via the API:

  ```bash
  gh api repos/presidio-v/presidio-hardened-angellist/git/tags/<sha> --jq .verification.verified
  ```

  The public half of that key is published in this repository's
  [`allowed_signers`](allowed_signers) file. To verify a tag locally:

  ```bash
  git -c gpg.ssh.allowedSignersFile=allowed_signers verify-tag <tag>
  ```

  Note: tag signing was adopted after `v0.7.1`, so tags up to and including `v0.7.1` are
  unsigned — a published tag cannot be re-signed. Every tag from `v0.7.2` onward is
  signed and shows as Verified on GitHub.

- **PyPI releases** carry PEP 740 attestations published via Trusted Publishing (OIDC, no
  stored API token). `pip` and the PyPI UI surface these automatically; the raw bundle is
  also retrievable from PyPI's integrity API:

  ```bash
  curl -s https://pypi.org/integrity/presidio-hardened-angellist/<version>/<filename>/provenance
  ```

## Dependency Management

- Dependabot is configured to keep all dependencies up to date, for both pip and GitHub
  Actions.
- CodeQL (`security-extended`) and Bandit both run on every push and pull request.
- `pip-audit` runs in CI on every push and pull request and fails the build on any
  known-vulnerable dependency.
- A CycloneDX SBOM is generated in CI and attached to every release.
- Every GitHub Action is pinned to a commit SHA, and every workflow declares a read-only
  top-level token, elevating only the single job that needs more.
- OpenSSF Scorecard runs weekly and on push to `main`; results are published to the public
  OpenSSF store.
- Runtime dependency floors are pinned above known CVEs (`urllib3>=2.7.0`,
  `idna>=3.15`, `requests>=2.32.0`).
- All changes require passing CI (pytest + ruff + pip-audit) before merge.

## Responsible Disclosure

We follow [coordinated vulnerability disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure).
We appreciate security researchers who report issues responsibly and will
credit them in our release notes (with permission).

## Independent Security Review

An independent third-party security review was performed on **2026-07-29** against commit
`e9e8b60`, covering source, tests, CI/CD, supply chain, dependency advisories, governance
documentation versus implementation, and the residual threat model, with dynamic probes of the
SSRF guard, redirect handling, SMTP header injection, secret redaction, and store permissions.

It returned 0 critical, 1 high, 4 medium, and 5 low findings. The high finding — a
redirect-based SSRF bypass (CWE-918) — and every medium and low finding with a code remedy
were fixed in **0.7.3**; the [CHANGELOG](CHANGELOG.md) entry for that release lists each one.
Two findings are process rather than code and are tracked openly: the OpenSSF Code-Review
score reflects historical merges that predate the current two-person review gate, and
secret-scanning push protection.

The full report is retained privately under `third-party-audits/` and is available to
downstream integrators on request. The assurance argument it tested, and the correction it
forced, are in [ASSURANCE.md](ASSURANCE.md).

## Software Development Lifecycle

This repository is developed under the Presidio hardened-family SDLC. The public report
— scope, standards mapping, threat-model gates, and supply-chain controls — is at
<https://github.com/presidio-v/presidio-hardened-docs/blob/main/sdlc/sdlc-report.md>.
