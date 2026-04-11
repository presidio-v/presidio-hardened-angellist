# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅ Yes    |

## Reporting a Vulnerability

If you discover a security vulnerability in `presidio-hardened-angellist`,
please report it responsibly:

1. **Do NOT open a public GitHub issue.**
2. Email **security@presidio.dev** with:
   - A description of the vulnerability
   - Steps to reproduce
   - Potential impact assessment
3. You will receive an acknowledgment within **48 hours**.
4. We aim to release a fix within **7 days** of confirmation.

## Security Features

This package provides the following hardening over a plain `requests`-based API client:

- **TLS 1.2+ enforcement** — TLS 1.0 and 1.1 are rejected. Strong cipher suites are
  enforced. Certificate verification is always enabled.
- **HTTP → HTTPS upgrade** — Insecure HTTP base URLs are automatically upgraded.
- **Secret / API key redaction** — AngelList API keys and Bearer tokens are scrubbed
  from all log output before they reach any log sink.
- **Per-host rate limiting** — Prevents accidental DoS with configurable req/s cap
  and exponential backoff on repeated failures.
- **Retry logic** — Transient 5xx errors and connection failures are retried with
  exponential backoff; 401/403 raise immediately without retry.

## Dependency Management

- Dependabot is configured to keep all dependencies up to date.
- CodeQL analysis runs on every push and pull request.
- All changes require passing CI (pytest + ruff) before merge.

## Responsible Disclosure

We follow [coordinated vulnerability disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure).
We appreciate security researchers who report issues responsibly and will
credit them in our release notes (with permission).
