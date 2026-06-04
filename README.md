# presidio-hardened-angellist

[![CI](https://github.com/presidio-v/presidio-hardened-angellist/actions/workflows/ci.yml/badge.svg)](https://github.com/presidio-v/presidio-hardened-angellist/actions/workflows/ci.yml)
[![CodeQL](https://github.com/presidio-v/presidio-hardened-angellist/actions/workflows/codeql.yml/badge.svg)](https://github.com/presidio-v/presidio-hardened-angellist/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

Presidio security-hardened **deal-flow triage & due-diligence toolkit** for
early-stage (pre-seed / seed) startups sourced via **AngelList syndicates**.

> **Why not an API client?** The legacy AngelList Startup/Funding Data API
> (`api.angel.co`) has been shut down — AngelList today is fund/SPV
> infrastructure, not an open data API. So this toolkit triages the deal flow you
> *actually receive* — forwarded syndicate deal emails — instead of calling a
> dead endpoint. The original Presidio hardening layer is retained and reused for
> every outbound enrichment call.

---

## How it works

```
forwarded .eml ─▶ intake ─▶ extraction ─▶ enrichment ─▶ triage rubric ─▶ memo
                  (parse)   (regex first,  (hardened     (deterministic   (Claude or
                            LLM fallback)   HTTP fetch)    scorecard)       template)
```

1. **Intake** — parse a forwarded `.eml` (or pasted text) into a structured `Deal`.
2. **Extraction** — deterministic regex/heuristics first; **Claude fallback** only
   when the parse is too thin (`is_complete()` is `False`).
3. **Enrichment** *(opt-in)* — fetch the company website through the hardened
   session to backfill a one-liner.
4. **Triage** — score against a deterministic pre-seed/seed rubric → composite +
   tier (`Pass` / `Track` / `Dig deeper` / `Strong lead`).
5. **Memo** *(opt-in)* — Claude-assisted investment memo, with a templated
   fallback so `--memo` still works with no API key.

The deterministic path needs **no API key**. The LLM steps activate only when
`ANTHROPIC_API_KEY` is set and the `[llm]` extra is installed.

---

## Installation

```bash
pip install presidio-hardened-angellist            # deterministic core
pip install 'presidio-hardened-angellist[llm]'     # + Claude extraction/memo
```

For development:

```bash
git clone https://github.com/presidio-v/presidio-hardened-angellist.git
cd presidio-hardened-angellist
uv venv && source .venv/bin/activate
uv pip install -e ".[dev,llm]"
```

---

## CLI usage

```bash
angeltriage deal.eml                 # scorecard for one deal
angeltriage deal.eml --memo          # + investment memo
angeltriage deal.eml --enrich        # fetch the company site for more signal
angeltriage deal.eml --json          # machine-readable output (pipe-friendly)
cat deal.txt | angeltriage -         # read a pasted email from stdin
angeltriage *.eml                    # batch, ranked by composite score
angeltriage deals.csv                # batch-triage a CSV of deals (one row each)
angeltriage --imap                   # pull deal emails over IMAP (see below)
angeltriage --watch --interval 300   # poll IMAP every 5 min, auto-triage new deals
angeltriage deal.eml --no-llm        # force the deterministic-only path
angeltriage deal.eml --weights w.json  # tune dimension weights (see below)
angeltriage deal.eml --rubric r.json   # full rubric config (see below)
angeltriage deal.eml --save          # persist to the deal queue (see below)
angeltriage --queue                  # show the ranked, saved deal queue
angeltriage --set-status 4 passed    # update a saved deal's workflow status
```

`.eml`/text inputs are parsed as emails; `.csv` inputs are triaged a row at a
time. You can mix files in one batch — everything is ranked together by score.

Example output:

```
Nimbus Robotics  [Strong lead · 83.0/100]
  pre-seed · SAFE · $10,000,000 cap · lead: Jane Okafor
  Warehouse-automation robots for SMB 3PLs.

  Scorecard:
    Team       4.5/5   2 founders; credential signals: ex-, former, mit
    Market     3.5/5   clear one-liner present
    Traction   4.5/5   signals: customers, month-over-month, mrr, paying
    Terms      4.0/5   cap $10,000,000; SAFE
    Syndicate  4.0/5   lead: Jane Okafor; allocation $250,000
```

## Library usage

```python
from presidio_angellist import triage_email

result = triage_email("deal.eml", memo=True)
print(result.scorecard.tier, result.scorecard.composite)   # Strong lead 83.0
print(result.deal.valuation_cap)                            # 10000000.0
print(result.memo)
```

Tune the rubric weights:

```python
from presidio_angellist import score_deal, parse_email

deal = parse_email("deal.eml")
sc = score_deal(deal, weights={"team": 0.4, "market": 0.2, "traction": 0.2,
                               "terms": 0.1, "syndicate": 0.1})
```

---

## Triage rubric (pre-seed / seed)

| Dimension | What it weighs |
|---|---|
| **Team** | Founder count, technical co-founder, credential signals (ex-FAANG, YC, etc.) |
| **Market** | Crispness of the one-liner / sector framing |
| **Traction** | Revenue, users, LOIs, growth — any early signal |
| **Terms** | Valuation cap sanity for the stage, instrument (SAFE/priced) |
| **Syndicate** | Named lead, allocation, social proof |

Risk flags (solo founder, missing cap, cap too high for stage, no traction, no
website) are surfaced separately.

### Tuning the weights

Weights live in `DEFAULT_WEIGHTS` and are overridable per call, or from a JSON
config file via `--weights`:

```json
{
  "team": 0.5,
  "traction": 0.3
}
```

```bash
angeltriage deal.eml --weights weights.json
```

Dimensions you omit keep their default weight (so partial overrides are fine),
weights need not sum to one (the composite normalizes by total weight), and at
least one must be positive. Valid dimensions: `team`, `market`, `traction`,
`terms`, `syndicate`. From the library:

```python
from presidio_angellist import load_weights, triage_email

result = triage_email("deal.eml", weights=load_weights("weights.json"))
```

### Full rubric config (`--rubric`)

For more than weights, pass a `--rubric` file. All sections are optional and
merge over the defaults:

```json
{
  "weights": { "team": 0.4, "traction": 0.25 },
  "tier_thresholds": { "Strong lead": 90, "Dig deeper": 75 },
  "cap_ceilings": { "pre-seed": 8000000, "seed": 25000000 },
  "risk_penalty": 5.0
}
```

- **`tier_thresholds`** — minimum composite (0–100) for each tier label. The
  `Pass` floor at 0 is always retained.
- **`cap_ceilings`** — per-stage valuation-cap ceiling (USD); caps above it raise
  a risk flag and dock the Terms score.
- **`risk_penalty`** — composite points deducted **per risk flag** (default 0).

```bash
angeltriage deal.eml --rubric rubric.json   # mutually exclusive with --weights
```

```python
from presidio_angellist import load_rubric_config, triage_email

result = triage_email("deal.eml", config=load_rubric_config("rubric.json"))
```

Validation fails closed — unknown keys/dimensions, out-of-range thresholds,
negative penalties, or malformed JSON raise `WeightsConfigError`.

### CSV batch import

`angeltriage deals.csv` triages one `Deal` per row. Headers are matched
case-insensitively against common aliases:

| Field | Accepted headers (any of) |
|---|---|
| company | `company`, `name`, `startup` |
| valuation_cap | `valuation_cap`, `cap`, `valuation` |
| round_size | `round_size`, `raising`, `round`, `target` |
| website | `website`, `url`, `site` |
| founders | `founders`, `founder`, `team` (split on `;` / `,`) |
| … | `one_liner`, `sector`, `stage`, `instrument`, `allocation`, `lead`, `deadline`, `location`, `traction`, `links` |

Money cells accept `$1.2M`, `1,200,000`, or `500k`. Rows without a company are
skipped.

```python
from presidio_angellist import triage_csv

for result in triage_csv("deals.csv"):
    print(result.deal.company, result.scorecard.tier)
```

---

## IMAP intake

`--imap` pulls deal emails straight from a mailbox (file syndicate emails into a
folder, then poll it). It runs **wherever you run it** — your laptop or a server,
not a phone. Credentials come from the environment **only** (never the command
line) — use an **app-specific password** (iCloud, Gmail with 2FA):

```bash
export IMAP_HOST=imap.mail.me.com      # iCloud; Gmail: imap.gmail.com
export IMAP_USER=you@icloud.com
export IMAP_PASSWORD=abcd-efgh-ijkl-mnop   # app-specific password
export IMAP_FOLDER=Deals               # optional; defaults to INBOX

angeltriage --imap --save              # fetch UNSEEN, triage, save to the queue
angeltriage --imap --imap-all --imap-limit 20    # most recent 20, read or not
angeltriage --imap --imap-from deals@syndicate.com
```

| Env var | Purpose |
|---|---|
| `IMAP_HOST` / `IMAP_USER` / `IMAP_PASSWORD` | Required connection + app-specific password |
| `IMAP_PORT` | Optional, default `993` |
| `IMAP_FOLDER` | Optional, default `INBOX` (or use `--imap-folder`) |
| `IMAP_SSL` | Optional, default on (`0`/`false` to disable) |

Flags: `--imap-folder`, `--imap-all` (not just `UNSEEN`), `--imap-from ADDR`,
`--imap-limit N`. The mailbox is opened **read-only**, so messages aren't marked
read — re-polling re-fetches them and the deal queue dedups by deal identity.

```python
from presidio_angellist import imap_config_from_env, triage_imap

cfg = imap_config_from_env(folder="Deals", limit=20)   # reads IMAP_* env vars
for result in triage_imap(cfg):
    print(result.deal.company, result.scorecard.tier)
```

### Watch mode (continuous polling)

`--watch` polls the mailbox on an interval and auto-triages new deals into the
queue — a hands-off inbox-to-queue pipeline:

```bash
angeltriage --watch --interval 300        # poll every 5 min until Ctrl-C, saving new deals
angeltriage --watch --max-cycles 12       # poll 12 times then stop
```

Within a session, messages are deduped by `Message-ID` so the same unread email
isn't re-triaged every poll; across restarts the deal queue dedups by deal
identity. The first poll fails fast on a bad config/credentials; later polls
tolerate transient network errors and keep going. Each poll prints a one-line
summary plus any newly-saved deals. For a cron-style setup, use `--max-cycles 1`
on a schedule instead of a long-running process.

```python
from presidio_angellist import DealStore, imap_config_from_env, watch

with DealStore() as store:
    watch(imap_config_from_env(folder="Deals"), store, interval=300)
```

> ⚠️ Don't put your mail password in a shared/remote shell. Keep it in a local
> `.env` / your shell profile, scoped to where you run the tool.

---

## Deal queue (persistence)

`--save` persists triaged deals to a local SQLite store so triage becomes a
workflow you work over time, instead of one-shot:

```bash
angeltriage inbox/*.eml --save           # triage + save the batch
angeltriage --queue                      # ranked list of everything saved
angeltriage --queue --status new         # filter by workflow status
angeltriage --set-status 4 tracking      # new -> tracking -> passed -> committed
```

```
  #  tier         score  status     seen  company
  1  Strong lead   83.0  tracking      2  Nimbus Robotics
  3  Track         49.5  new           1  Solo Stealth
```

- **Dedup across runs** — deals are keyed by website domain (or normalized
  company name when there's no site), so the same deal forwarded by two
  syndicates collapses to one row. `seen` counts how many times it arrived.
- **Status is preserved on re-save** — re-triaging a `passed` deal won't reset it
  to `new`; only the scorecard/score refresh.
- **Store location** — `~/.angeltriage/deals.db` by default; override with `--db
  FILE` or the `ANGELTRIAGE_DB` env var. The DB is local; nothing leaves your
  machine.

```python
from presidio_angellist import DealStore, triage_email

with DealStore() as store:                       # default path, or DealStore("deals.db")
    saved, is_new = store.save(triage_email("deal.eml"))
    for row in store.list(status="new"):
        print(row.id, row.company, row.tier, row.composite)
    store.set_status(saved.id, "tracking")
```

---

## Security hardening (retained, reused for enrichment)

| Feature | What it does |
|---|---|
| **Strict TLS 1.2+ enforcement** | Rejects TLS 1.0/1.1; strong ciphers; `verify=True` always |
| **HTTP → HTTPS auto-upgrade** | Insecure `http://` URLs are silently upgraded |
| **API key / secret redaction** | Bearer tokens, `sk_live_*`, `sk-ant-*` keys scrubbed from logs |
| **Per-host rate limiting** | Token-bucket limiter; prevents accidental DoS of enrichment hosts |
| **Security event logging** | Structured logs for every hardening action (`presidio_angellist` logger) |

Every outbound enrichment request goes through `HardenedSession`.

---

## Roadmap

| Version | Highlights |
|---|---|
| **0.2.0** | Pivot to deal-flow triage: email intake, deterministic rubric, `--weights` config, LLM extraction fallback + memo, `angeltriage` CLI |
| **0.3.0** | CSV/batch import, full rubric config (`--rubric`: tiers, cap ceilings, per-flag penalty), HTML-email robustness, og/title enrichment fallbacks |
| **0.4.0** | SQLite deal queue: `--save` / `--queue` / `--set-status`, dedup across runs, workflow statuses |
| **0.5.0** | IMAP intake (`--imap`, key-gated) |
| **0.5.1** | IMAP watch mode (`--watch`: interval polling, in-session dedup, auto-save) |
| **0.6.0** _(planned)_ | Pluggable enrichment providers (Crunchbase/Harmonic), queue export/digest |

---

## Running tests

```bash
pytest -v --cov=presidio_angellist --cov-report=term-missing
```

---

## Project structure

```
presidio-hardened-angellist/
├── src/presidio_angellist/
│   ├── __init__.py          # public API
│   ├── hardening.py         # TLS / redaction / rate-limit primitives
│   ├── models.py            # Deal, Scorecard, TriageResult
│   ├── intake/email.py      # forwarded .eml / text -> Deal (deterministic)
│   ├── intake/csv.py        # CSV of deals -> list[Deal]
│   ├── intake/imap.py       # pull deal emails over IMAP (key-gated)
│   ├── watch.py             # --watch: poll IMAP on an interval, auto-triage
│   ├── enrich/web.py        # hardened website enrichment
│   ├── rubric_config.py     # RubricConfig + defaults (weights/tiers/ceilings)
│   ├── triage/rubric.py     # deterministic pre-seed/seed scorecard
│   ├── triage/memo.py       # LLM memo + templated fallback
│   ├── store.py             # SQLite-backed persistent deal queue
│   ├── config.py            # --weights / --rubric config loaders
│   ├── llm.py               # optional Claude extraction/memo (key-gated)
│   ├── pipeline.py          # end-to-end triage_email()
│   └── cli.py               # angeltriage entrypoint
├── tests/
├── pyproject.toml
├── LICENSE                  # MIT
├── README.md
└── SECURITY.md
```

---

## License

MIT — see [LICENSE](./LICENSE).

## Security

See [SECURITY.md](./SECURITY.md) for our vulnerability disclosure policy.

---

## SDLC

This repository is developed under the Presidio hardened-family SDLC:
<https://github.com/presidio-v/presidio-hardened-docs/blob/main/sdlc/sdlc-report.md>.
