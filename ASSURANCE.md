# Security Assurance Case

This document is the assurance case for `presidio-hardened-angellist`: an explicit argument
for why the project's security requirements are met. It has four parts, as
required by the OpenSSF Best Practices silver criterion `assurance_case`:

1. the threat model,
2. the trust boundaries,
3. the argument that secure design principles are applied, and
4. the argument that common implementation weaknesses are countered.

It is a summary that links to the authoritative detail in
[`SECURITY.md`](SECURITY.md) (controls, per-version threat tables, reporting) and
[`ARCHITECTURE.md`](ARCHITECTURE.md) (components, flow, boundaries) for
`presidio-v/presidio-hardened-angellist`.

## 1. Threat model

**The assets.** Two things are worth protecting here. The first is the *analyst's machine
and network position*: this tool ingests email sent by strangers and, on request, fetches
URLs those strangers chose, so it is a path from an untrusted sender to an inside-the-
perimeter process. The second is *the analyst's credentials and deal data*: an LLM API key,
a mail password, an SMTP password, and a local queue of deal information that is commercially
sensitive and may contain personal data about founders.

**Adversaries and threats, each mapped to its control.**

| Threat | Control |
|---|---|
| A sender crafts a deal email whose company URL points at an internal service or a cloud metadata endpoint, using the analyst's `--enrich` run as an SSRF proxy | `assert_public_host` resolves the target and refuses loopback, private, link-local (incl. `169.254.169.254`), reserved, multicast, and unspecified addresses, for IP literals and every resolved address; enrichment is off by default |
| A sender points at a *public* site under their control which redirects to an internal address, so the first-hop check passes and the fetch lands inside the perimeter | The guard runs in `HardenedSession.send`, which every redirect hop passes through, so each `Location` is validated before it is followed; redirect depth is capped at 5. This was audit finding F-01, exploitable through 0.7.2 and fixed in 0.7.3 |
| A sender writes the internal address in an alternative notation (`0177.0.0.1`, `0x7f.0.0.1`, `2130706433`) so it parses as a hostname and reaches the resolver, whose interpretation is platform-dependent | A host whose labels are all numeric but which does not parse strictly as an IP literal is refused outright; zone ids and brackets are stripped before the check (audit F-08) |
| A hostile site answers a multi-gigabyte body to exhaust the analyst's memory during enrichment | The response is streamed and truncated at 512 KiB, and only textual content types are scanned (audit F-02) |
| Deal data at rest is read by another user on a shared host | The deal store is created mode `0o600` in a directory created `0o700`; pre-existing files are left to the operator, which SECURITY.md states (audit F-03) |
| A sender downgrades an enrichment fetch to plaintext, or to a non-HTTP scheme, to intercept or redirect it | `HardenedSession` upgrades `http://` to `https://` and refuses any other scheme outright, on every hop; TLS 1.2+ with mandatory certificate verification and hostname checking |
| A sender embeds instructions in the deal text to steer the LLM extraction or memo (prompt injection) | The deal text is wrapped in a `<untrusted_deal_content>` block with nested delimiters stripped, and both system prompts declare that block to be data and never instructions. Residual risk is real and is stated below |
| A sender's content reaches a shell, SQL statement, or the filesystem as code | Parsed content only ever populates dataclass fields. All SQL in `store.py` is parameterized; no `subprocess`, `eval`, `exec`, or `pickle` is used on deal content |
| Malicious HTML or a hostile email structure crashes or hangs the parser | Parsing uses the stdlib `email` and `csv` modules and an `html.parser` subclass; `<script>`/`<style>`/`<head>` are dropped rather than interpreted. Exercised by an Atheris fuzz harness (`fuzz/fuzz_intake.py`) over the full intake path |
| An API key, mail password, or bearer token leaks through logs, a crash trace, or a debug dump | A `RedactingFilter` is installed on the `presidio_angellist` logger at import, scrubbing every record at the sink; secrets are read from environment variables only, never from command-line arguments (which are visible in `ps` and shell history) |
| A mail password is sent in clear over a plaintext IMAP connection | IMAP-over-TLS is the default and plaintext is refused unless the operator sets `IMAP_ALLOW_INSECURE=1`, which also logs a warning |
| A hostile or malformed rubric/weights file silently degrades scoring so a bad deal reads as a good one | `config.load_weights` / `load_rubric_config` validate strictly and raise `WeightsConfigError` on unknown dimensions, non-numeric, negative, boolean, non-object, or all-zero input — no silent fallback |
| A known-vulnerable dependency ships in a release | `pip-audit` on every push and pull request, Dependabot on pip and GitHub Actions, runtime floors pinned above known CVEs (`requests>=2.32.0`, `urllib3>=2.7.0`, `idna>=3.15`) |
| A tampered build or a typosquatted release is published under this project's name | Publishing is by PyPI Trusted Publishing (OIDC, no stored token) from a tag-triggered workflow, with build provenance attestations and an SBOM attached to the release; all GitHub Actions are pinned to commit SHAs |
| An unreviewed change lands the above controls in a weakened state | `main` is protected: required status checks, required code-owner review by someone other than the author, and admin enforcement |

**Explicitly out of scope.**

- **Prompt injection is mitigated, not solved.** An LLM can still be steered by sufficiently
  clever content. Generated memos are advisory; the deterministic scorecard, which no model
  touches, is the authoritative output.
- **DNS rebinding.** `assert_public_host` resolves and checks before the connection, so an
  attacker who controls authoritative DNS can in principle race the resolve/connect window.
  Operators handling low-trust senders should run `--enrich`/`--watch` from an
  egress-restricted network.
- **Endpoint and account security.** Protection of the analyst's machine, their mail account,
  and the confidentiality of `~/.angeltriage/deals.db` at rest is left to the operating
  system and the operator; the project ships no encryption-at-rest layer.
- **The operator-configured LLM endpoint.** A base URL the operator sets is trusted by
  configuration. If they point it at a hostile server, this project's controls do not help.
- **Correctness of the investment judgement.** The rubric is a triage heuristic, not
  diligence, and is out of scope as a security property.

## 2. Trust boundaries

The names below match [`ARCHITECTURE.md#trust-boundaries`](ARCHITECTURE.md#trust-boundaries),
which carries the full table.

- **Forwarded email / CSV → intake** — *input validation boundary*, and the primary one.
  Stdlib parsers only; HTML stripped with active elements dropped; content becomes typed
  dataclass fields and nothing else.
- **Deal-derived URL → public internet** — *egress boundary*. `HardenedSession`: HTTPS-only,
  TLS 1.2+ with certificate verification, SSRF guard on literals and resolved addresses,
  per-host rate limiting. Enforced in `send()`, so the boundary holds across redirect hops
  and not merely on the first request; depth capped at 5. Response bodies are truncated at
  512 KiB. Opt-in.
- **Deal text → LLM provider** — *egress and injection boundary*. Untrusted-content wrapping
  plus an explicit data-not-instructions system prompt; key from the environment.
- **Operator-configured LLM endpoint → local model server** — *documented exception*. Plain
  `requests` without the SSRF guard, because the address is operator-supplied (typically
  loopback) and never derived from deal content.
- **Mail server → IMAP intake** — *credential and input boundary*. Environment-only
  credentials, read-only mailbox, TLS by default, plaintext refused without an explicit
  override.
- **Triage result → SMTP recipients** — *egress boundary*. Environment-only credentials,
  implicit TLS or STARTTLS; the recipient list is trusted by configuration.
- **Process → local deal store** — *persistence boundary*. Parameterized SQL, no secrets at
  rest, local file only.
- **Process → log sinks** — *egress boundary*. Sink-level redaction via `RedactingFilter`.

Custody of every credential the project uses — LLM key, IMAP password, SMTP password — sits
outside the project by contract: it reads them from the environment and never persists,
transmits, or logs them.

## 3. Secure design principles applied

**Fail-safe defaults / secure by default.** Every network-touching capability is off until
the operator turns it on: enrichment needs `--enrich`, LLM steps need a configured backend
and key, IMAP and SMTP need environment credentials. When a security control does engage, it
fails closed — a non-public host, a non-HTTPS scheme, an invalid weights file, or plaintext
IMAP raises rather than degrading. The one deliberate exception, the operator-configured
local LLM endpoint, is documented here and in `SECURITY.md` rather than left implicit. New
controls are added opt-in; weakening an existing default requires an explicit rationale in
review ([CONTRIBUTING.md](CONTRIBUTING.md#security-sensitive-changes)).

**Complete mediation.** The scheme check, HTTPS upgrade, SSRF guard, and rate limiter live
inside `HardenedSession.send` — deliberately `send`, not `request`. `requests` resolves
redirects inside `Session.send` → `resolve_redirects`, which calls `self.send()` for each hop
and **never re-enters** `Session.request()`. Guarding in `send` is therefore what makes
mediation complete: every dispatch, first hop and attacker-chosen `Location` alike, is
validated before it goes out, and redirect depth is capped at 5 rather than the `requests`
default of 30. Log redaction is likewise enforced at the sink by a filter on the package
logger, not at individual call sites, so a new `_log.info(...)` anywhere in the package is
covered the moment it is written. Both placements are chosen specifically so that mediation
does not depend on future authors remembering it.

*Correction, recorded rather than quietly fixed.* Until 0.7.3 these controls lived in
`request()`, and this document claimed on that basis that there was "no bypass path short of
not using the session." That was wrong: the independent audit of 2026-07-29 (finding F-01)
demonstrated end-to-end that a public site answering `302 Location:
https://169.254.169.254/latest/meta-data/` was followed and its body stored in
`deal.one_liner`. The placement above is the fix, `tests/test_hardening.py`
(`TestRedirectSSRFGuard`) and `tests/test_enrich.py` are its regression coverage, and this
paragraph stays because an assurance case that silently rewrites a falsified claim is worth
less than one that shows where it was wrong.

**Least privilege.** The project holds no long-lived secret of its own: there is no service
account, no stored token, and no credential file. It reads what it needs from the
environment at the moment of use. The IMAP mailbox is opened **read-only**. Publishing uses
short-lived OIDC credentials via Trusted Publishing rather than a stored PyPI token, and
every CI workflow declares a read-only top-level `permissions:` block, elevating only the
single job that needs `security-events: write` or `id-token: write`.

**Defense in depth.** The controls are independent and cover distinct threats rather than
restating one another: transport hardening (TLS floor, ciphers, cert verification) is
separate from destination validation (SSRF guard), which is separate from output hygiene
(log redaction), which is separate from input hygiene (stdlib parsing, no dynamic
execution), which is separate from supply-chain controls (SHA-pinned actions, `pip-audit`,
Dependabot, provenance attestation). The deterministic rubric is itself a defensive layer:
because scoring never depends on the LLM, a successful prompt injection cannot change the
score, only the advisory prose.

**Economy of mechanism.** The project implements no cryptography. TLS comes from the
standard library's `ssl` module through `requests`/`urllib3`; the only crypto-adjacent code
is `ssl.create_default_context()` with a raised minimum version and a restricted cipher
list. There is no bespoke parser where a stdlib one exists, no custom serialization format,
and no dependency added where the standard library suffices — the runtime dependency set is
three packages.

## 4. Common implementation weaknesses countered

SAST and posture tooling actually run by this repository: **CodeQL**
(`security-extended` queries, on every push and pull request, results in the Security tab),
**Bandit** (medium severity / medium confidence over `src/`), **ruff** with the `S`
(flake8-bandit) rule set enabled in `pyproject.toml`, **pip-audit**, and **OpenSSF
Scorecard** weekly and on push.

| Weakness class | How it is countered |
|---|---|
| Improper input validation / injection (CWE-20, CWE-74) | Untrusted email, HTML, and CSV are parsed with stdlib parsers into typed fields; no `eval`/`exec`/`subprocess` and no shell interpolation touches deal content. Prompt injection (the LLM-specific case of CWE-74) is bounded by untrusted-content delimiting plus a data-not-instructions system prompt, with the authoritative score computed without the model. Checked by CodeQL, Bandit, ruff `S`, and the Atheris harness over the intake path |
| SQL injection (CWE-89) | Every statement in `store.py` uses bound parameters; no query is built by string concatenation. Checked by CodeQL and Bandit |
| Memory safety (CWE-119 family) | Not applicable at the source level: Python is memory-safe and the project contains no native extension and no `ctypes`. The residual exposure is in CPython and the C code inside `requests`/`urllib3`, which is covered by dependency floors and `pip-audit` |
| Cryptographic misuse (CWE-327, CWE-916) | No cryptography is implemented. TLS is configured through `ssl.create_default_context()` with `minimum_version = TLSv1_2`, `check_hostname = True`, `verify_mode = CERT_REQUIRED`, and an EC-ephemeral-only cipher list. No password is stored or hashed by this project. Checked by CodeQL and Bandit (`B501`-class checks) |
| Hard-coded or exposed secrets (CWE-798, CWE-532) | No secret is committed or defaulted in source; all credentials come from environment variables and are never accepted as CLI arguments. A `RedactingFilter` scrubs bearer tokens, `access_token=`/`api_key=` parameters, `Authorization` headers, and `sk_live_*`/`sk-ant-*` keys from every log record at the sink. Checked by CodeQL, Bandit, GitHub secret scanning, and unit tests over the redaction rules |
| Insecure network communication / SSRF (CWE-319, CWE-295, CWE-918) | HTTP is upgraded to HTTPS and other schemes refused; TLS 1.2+ with mandatory certificate and hostname verification; `assert_public_host` blocks non-public destinations for both IP literals and resolved names, including IPv4-mapped IPv6, ambiguous numeric notations, and zone-id forms. Enforced in `HardenedSession.send`, so **redirect hops are validated too** — the gap that audit F-01 exploited through 0.7.2 — with depth capped at 5. Checked by CodeQL, Bandit, and dedicated SSRF unit tests including the redirect cases |
| Unsafe deserialization (CWE-502) | No `pickle`, `marshal`, `shelve`, or `yaml.load` anywhere in the package. Untrusted structured input is JSON parsed with `json.loads` into plain dicts, then validated field by field; the LLM's JSON response is likewise parsed and validated rather than trusted. Checked by CodeQL and Bandit |
| Uncontrolled resource consumption (CWE-400) | Bounded retries with exponential backoff, per-host rate limiting, and explicit timeouts on the enrichment fetch (10 s), the OpenAI-compatible LLM call (120 s, tunable), and SMTP delivery (30 s). The Anthropic SDK path relies on the SDK's own default timeout rather than passing the configured value. Enrichment failures are non-fatal, so a slow host degrades rather than blocks |
| Vulnerable dependencies (CWE-1104) | Three runtime dependencies, each floored above its known CVEs; `pip-audit` fails CI on any known-vulnerable package; Dependabot tracks pip and GitHub Actions weekly; a CycloneDX SBOM is generated in CI and attached to each release |
| Compromised build or dependency confusion (CWE-1357) | All GitHub Actions are pinned to commit SHAs; workflows use least-privilege tokens; releases are published via OIDC Trusted Publishing with build-provenance attestations rather than a stored API token |

These classes are checked continuously: CodeQL and Bandit run on every push and pull
request, `pip-audit` gates every build, and OpenSSF Scorecard runs weekly and on push to
`main`, with results published to the public OpenSSF store.

**Independent review.** An independent third-party security review was performed on
**2026-07-29** against commit `e9e8b60`, covering source, tests, CI/CD, supply chain,
dependency advisories, governance documentation versus implementation, and the residual
threat model, with dynamic probes of the SSRF guard, redirect handling, header injection,
secret redaction, and store permissions. It returned 0 critical, 1 high, 4 medium, and 5
low findings. The high finding (F-01, redirect SSRF) and every medium and low finding with
a code remedy were fixed in **0.7.3**; see the CHANGELOG entry for that release. Two
findings are process rather than code and are tracked as such: the OpenSSF Code-Review
score reflects historical merges predating the two-person gate, and secret-scanning push
protection. The full report is retained privately under `third-party-audits/` and is
available to downstream integrators on request. Ongoing review is (a) required code-owner
review on every change to `main` by someone other than the author, and (b) the automated
analysis listed above.

## Conclusion

The threats above are each matched to a control; the controls sit at explicit
trust boundaries; the design follows fail-safe, least-privilege, complete-
mediation, defense-in-depth, and economy-of-mechanism principles; and the common
implementation weakness classes are countered by design and checked by automated
analysis. The project's stated security requirements are therefore met, subject
to the documented out-of-scope assumptions.
