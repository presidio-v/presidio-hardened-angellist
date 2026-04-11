# presidio-hardened-angellist

[![CI](https://github.com/presidio-v/presidio-hardened-angellist/actions/workflows/ci.yml/badge.svg)](https://github.com/presidio-v/presidio-hardened-angellist/actions/workflows/ci.yml)
[![CodeQL](https://github.com/presidio-v/presidio-hardened-angellist/actions/workflows/codeql.yml/badge.svg)](https://github.com/presidio-v/presidio-hardened-angellist/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

Presidio security-hardened Python toolkit for the **AngelList Startup/Funding Data API**.

---

## Security Features

| Feature | What it does |
|---|---|
| **Strict TLS 1.2+ enforcement** | Rejects TLS 1.0/1.1; enforces strong ciphers; `verify=True` always |
| **HTTP → HTTPS auto-upgrade** | Insecure `http://` base URLs are silently upgraded |
| **API key / secret redaction** | Keys and Bearer tokens are scrubbed from all log output |
| **Per-host rate limiting** | Token-bucket limiter with exponential backoff |
| **Retry with backoff** | Retries on 5xx and connection errors; immediate raise on 401/403 |
| **Security event logging** | Structured logs for every hardening action (`presidio_angellist` logger) |

---

## Installation

```bash
pip install presidio-hardened-angellist
```

For development:

```bash
git clone https://github.com/presidio-v/presidio-hardened-angellist.git
cd presidio-hardened-angellist
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Usage

```python
from presidio_angellist import AngelListClient

client = AngelListClient(api_key="sk_live_...")  # key never appears in logs

# Get a startup by ID
startup = client.get_startup(startup_id=12345)

# Search startups
results = client.search_startups(query="AI infrastructure", market="Machine Learning")

# Get funding rounds
funding = client.get_funding_rounds(startup_id=12345)

# Get a single funding round
round_ = client.get_funding_round(funding_id=99)

# Search users / investors
investors = client.search_users(query="Naval Ravikant", role="investor")

# Fetch market tags
markets = client.get_tags(tag_type="MarketTag")
```

### Custom configuration

```python
from presidio_angellist import AngelListClient, RateLimiter, SecretRedactor

client = AngelListClient(
    api_key="sk_live_...",
    rate_limiter=RateLimiter(max_requests_per_second=2.0),
    redactor=SecretRedactor(placeholder="[SCRUBBED]"),
    max_retries=5,
    retry_backoff=2.0,
)
```

---

## Running Tests

```bash
pytest -v --cov=presidio_angellist --cov-report=term-missing
```

---

## Project Structure

```
presidio-hardened-angellist/
├── src/presidio_angellist/
│   └── __init__.py              # Hardened client + security primitives
├── tests/
│   └── test_client.py           # Full test suite (mocked HTTP)
├── .github/
│   ├── dependabot.yml
│   └── workflows/
│       ├── ci.yml               # pytest + ruff on every push/PR
│       └── codeql.yml           # GitHub CodeQL security scanning
├── pyproject.toml
├── LICENSE                      # MIT
├── README.md
└── SECURITY.md
```

---

## License

MIT — see [LICENSE](./LICENSE).

## Security

See [SECURITY.md](./SECURITY.md) for our vulnerability disclosure policy.
