# Stability & semver guarantees — presidio-hardened-angellist

For downstream integrators depending on this project.

## What is the public API

The public API is:

1. **Every name exported in `presidio_angellist.__all__`**, together with the documented
   signatures of those names. At 0.7.x that is the pipeline entry points (`triage_email`,
   `triage_csv`, `triage_deal`, `triage_imap`), intake (`parse_email`, `read_email`,
   `parse_csv`, `fetch_imap`, `imap_config_from_env`, `ImapConfig`, `ImapError`,
   `FetchedMessage`, `is_complete`), watch (`watch`, `poll_once`, `message_identity`,
   `PollResult`), triage (`score_deal`, `detect_stage_scope`, `write_memo`,
   `DEFAULT_WEIGHTS`, `DEFAULT_CAP_CEILINGS`, `DEFAULT_TIERS`, `RubricConfig`), config
   (`load_weights`, `load_rubric_config`, `WeightsConfigError`), persistence (`DealStore`,
   `SavedDeal`, `DealStoreError`, `STATUSES`), enrichment (`enrich_from_website`),
   notification (`notify_config_from_env`, `send_notifications`, `NotifyConfig`,
   `NotifyError`), models (`Deal`, `Founder`, `Scorecard`, `DimensionScore`,
   `TriageResult`), LLM (`LLMClient`, `LLMUnavailableError`), and the hardening primitives
   (`HardenedSession`, `SecretRedactor`, `RateLimiter`).
2. **The public fields of the exported dataclasses** — `Deal`, `Founder`, `Scorecard`,
   `DimensionScore`, `TriageResult`, `SavedDeal`, `ImapConfig`, `NotifyConfig`,
   `PollResult`, `RubricConfig` — and the values of `STATUSES`.
3. **The exception hierarchy**: `SSRFError` (a `requests.exceptions.RequestException`
   subclass, so callers may catch it either way), `WeightsConfigError`, `DealStoreError`,
   `ImapError`, `NotifyError`, `LLMUnavailableError`. Which exception type a documented
   failure raises is part of the contract.
4. **The `angeltriage` console entry point**: its documented flags, its `--json` output
   shape, and its exit codes.
5. **The environment-variable contract**: `ANGELTRIAGE_DB`, `ANGELTRIAGE_LLM_*`,
   `ANTHROPIC_API_KEY`, `IMAP_*`, and `ANGELTRIAGE_SMTP_*` / `ANGELTRIAGE_NOTIFY_TO`.

`SSRFError` is not currently listed in `__all__` but is public by the definition above —
callers are expected to catch it, and it is importable from `presidio_angellist.hardening`.
It will be added to `__all__` in a future minor; that addition is additive, not breaking.

Everything else is internal: any module member with a leading underscore (including
`_TLSHardenedAdapter`, `_is_blocked_ip`, and every `_*_RE` pattern), the submodule layout
itself, the SQLite schema (see *Schema/wire stability*), and the exact prompt text in
`llm.py`. Internals may change in any release without notice.

## Versioning rules (semver, pre-1.0 profile)

- **Patch (0.x.Y):** bug fixes, security fixes, dependency floor bumps. No API
  change, no behaviour change except the fixed defect. Safe to auto-upgrade; this
  is the channel security releases ship on.
- **Minor (0.X.0):** additive API (new exports, new optional parameters with
  defaults, new optional extras). Existing code keeps working, including the
  documented public behaviour. Deprecations are announced here (docstring +
  CHANGELOG) at least one minor before any change.
- **Major (1.0.0+):** the only place deprecated surface may be removed.

**Pin guidance for integrators:** pin `presidio_angellist` to the current minor
in production and run the verification step (below) in your CI on every upgrade.

## Behavioural guarantees (stronger than API stability)

These are security invariants, not just interfaces; weakening any of them is
treated as a breaking change regardless of which version component moves.

1. **No outbound request escapes the hardening layer — including redirect hops.** Every
   dispatch through `HardenedSession` is upgraded to HTTPS or refused, checked against the
   SSRF guard, and rate-limited *before* it goes out. The checks live in
   `HardenedSession.send`, not `request`, because `requests` resolves redirects via
   `Session.send` → `resolve_redirects`, which never re-enters `request()`; moving them back
   would silently reopen the redirect bypass that audit finding F-01 exploited through 0.7.2
   (fixed in 0.7.3). Adding a code path that reaches the network without these checks is
   breaking, even if no signature changes. The one exception is the operator-configured LLM
   endpoint (`ANGELTRIAGE_LLM_BASE_URL`), which is documented in [SECURITY.md](SECURITY.md)
   and [ASSURANCE.md](ASSURANCE.md).

   *This guarantee was overstated before 0.7.3:* the text claimed complete mediation while
   redirects bypassed it. The wording is corrected rather than removed so integrators who
   relied on the old claim can see exactly what changed and when.
2. **TLS floor.** Enrichment connections negotiate TLS 1.2 or better, with certificate and
   hostname verification always on and an EC-ephemeral cipher list. Lowering the floor,
   widening the cipher list, or making verification optional is breaking.
3. **Non-public destinations stay refused.** `assert_public_host` rejects loopback, private,
   link-local (including `169.254.169.254`), reserved, multicast, and unspecified addresses,
   for IP literals and for every address a hostname resolves to. It also refuses hosts written
   in an alternative numeric notation that does not parse strictly as an IP (`0177.0.0.1`,
   `0x7f.0.0.1`, `2130706433`), because the resolver's reading of those is platform-dependent,
   and strips IPv6 zone ids and brackets before checking. Narrowing that set is breaking.
4. **Secrets never reach a log sink.** The `RedactingFilter` on the `presidio_angellist`
   logger scrubs bearer tokens, `access_token=` / `api_key=` parameters, `Authorization`
   headers, `sk_live_*` / `sk-ant-*` keys, `password=` / `passwd:` / `pwd` assignments, and
   credential-shaped environment names such as `IMAP_PASSWORD=` from every record.
   `ImapConfig.password` and `NotifyConfig.password` are excluded from `repr()` so a
   stringified config cannot print them. Removing a redaction pattern, restoring a password
   field to a repr, or emitting a credential outside that logger, is breaking.
5. **Credentials are environment-only.** No credential — LLM key, IMAP password, SMTP
   password — is accepted as a command-line argument, written to disk, or persisted in the
   deal store. Accepting one on the command line is breaking.
6. **IMAP is TLS by default and the mailbox is opened read-only.** Plaintext requires the
   explicit `IMAP_ALLOW_INSECURE=1` override and warns. Changing either default is breaking.
7. **Operator config fails closed.** An unknown dimension, a negative, non-numeric, or
   boolean weight, a non-object document, or an all-zero weight set raises
   `WeightsConfigError`. Substituting a silent default for any of these is breaking.
8. **Untrusted content stays delimited.** Deal text sent to a model is wrapped in the
   untrusted-content block with nested delimiters stripped, under a system prompt that
   declares it data. Removing the wrapping is breaking.
9. **Scoring is deterministic and model-independent.** `score_deal` is pure: the same
   `Deal` and weights always produce the same composite and tier, and no LLM participates.
   Making the score depend on a model — or changing the composite for unchanged input
   outside a documented rubric change — is breaking.
10. **Enrichment reads a bounded prefix.** An enrichment response is streamed and truncated
    at 512 KiB (`enrich.web.MAX_BODY_BYTES`), and only textual content types are scanned, so
    a hostile site cannot exhaust memory. Removing the cap is breaking.
11. **The deal store is created owner-only.** A database this tool creates is mode `0o600`,
    in a directory it creates at `0o700`. Pre-existing paths are left as the operator set
    them. Loosening the mode on creation is breaking.
12. **Optional enrichment never fails triage, and the deterministic path is the fallback.**
    Website enrichment is strictly additive — it fills `one_liner` only when that field is
    empty. LLM extraction is different and worth stating precisely: when the deterministic
    parse is judged incomplete, the LLM's structured result *replaces* the parsed `Deal`
    wholesale; if the call fails for any reason, the deterministic result is kept and
    scoring proceeds. Making an enrichment failure fatal, or letting the LLM run when the
    deterministic parse was already complete, is breaking.

## Verifying an installation

The project ships no single self-check command. The guarantees above are covered by the
test suite, so the supported verification is to run it against the installed package:

```bash
pip install 'presidio-hardened-angellist[dev]'
git clone --depth 1 --branch v$(python -c 'import presidio_angellist as p; print(p.__version__)') \
  https://github.com/presidio-v/presidio-hardened-angellist.git
cd presidio-hardened-angellist && python -m pytest tests/ -q
```

A passing result is exit code 0 with no failures. The tests that exercise the invariants
above directly are `tests/test_hardening.py` (TLS floor, HTTPS upgrade, SSRF refusals, log
redaction), `tests/test_config.py` (fail-closed weight validation), `tests/test_imap.py`
(TLS default and plaintext refusal), `tests/test_llm.py` (untrusted-content wrapping), and
`tests/test_rubric.py` (deterministic scoring).

For a quick smoke test of the deterministic path only, with no network and no API key:

```bash
printf 'Subject: Deal\n\nAcme raising $2M SAFE at a $10M cap, pre-seed.\n' | angeltriage -
```

Verifying the artefact you installed is a separate step — see
[SECURITY.md](SECURITY.md#verifying-releases-and-obtaining-public-signing-keys).

## Schema/wire stability

This project consumes no wire protocol of its own and tracks no external specification. It
emits and reads three schemas:

- **The `--json` CLI output.** Stable within a minor line and **additive-only**: new keys
  may appear in a minor release, but an existing key will not be removed, renamed, or have
  its type changed outside a major. Consumers should ignore unknown keys.
- **The SQLite deal store** (`~/.angeltriage/deals.db`). Tables are created with `CREATE
  TABLE IF NOT EXISTS`, so an existing queue is opened, never rewritten or dropped, by an
  upgrade. Note plainly: **the store ships no migration mechanism today** — the schema has
  not changed since it was introduced, and a future column would require adding one. Any
  such change will be called out in `CHANGELOG.md` with its upgrade path. The *SQL schema
  itself is internal*: read the queue through `DealStore`, not by querying the tables
  directly. There is no downgrade guarantee.
- **The rubric and weights JSON files** (`--rubric`, `--weights`). Accepted keys are the
  five rubric dimensions plus the documented rubric-config fields. New optional fields may
  be added in a minor release, and a file that was valid at 0.X stays valid at 0.X+1;
  removing or repurposing a field is a breaking change. Unknown keys are rejected rather
  than ignored, by design — a typo in a weights file must not silently change scoring.

## Security response

See [SECURITY.md](SECURITY.md). Security fixes ship as patch releases on the
latest minor; any minimum-safe dependency floors are bumped in the same release.
