"""
Deterministic extraction of a :class:`Deal` from a forwarded syndicate email.

Syndicate deal emails are inconsistent, so this module extracts only what it can
match reliably with regex/heuristics. When the result is incomplete
(:func:`is_complete` returns ``False``), the caller may fall back to LLM
extraction -- see :mod:`presidio_angellist.llm`.
"""

from __future__ import annotations

import re
from email import message_from_bytes, message_from_string, policy
from email.message import EmailMessage, Message
from html.parser import HTMLParser
from pathlib import Path

from presidio_angellist.models import Deal, Founder

# A deal is "complete" enough to skip LLM fallback when we have a company name
# plus at least this many of the economically meaningful fields.
_MIN_SIGNAL_FIELDS = 2

_MONEY_RE = re.compile(
    r"\$\s*([\d][\d,]*(?:\.\d+)?)\s*([kKmMbB]|thousand|million|billion)?",
)
_URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)
_STAGE_RE = re.compile(r"\b(pre[\s-]?seed|seed|series\s+[a-d])\b", re.IGNORECASE)
_INSTRUMENT_RE = re.compile(
    r"\b(safe|convertible\s+note|priced\s+(?:round|equity)|equity\s+round)\b",
    re.IGNORECASE,
)
_MULTISPACE_RE = re.compile(r"[ \t]+")

# Tags after which a line break improves readability of the extracted text.
_HTML_BLOCK_TAGS = frozenset(
    {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}
)
_HTML_SKIP_TAGS = frozenset({"script", "style", "head", "title"})

# Hosts that are never the company's own site.
_SKIP_HOSTS = (
    "angel.co",
    "angellist.com",
    "wellfound.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
)


def read_email(source: str | bytes | Path) -> tuple[str, str]:
    """
    Return ``(subject, body_text)`` from an email source.

    ``source`` may be:
      - a path to a ``.eml`` file,
      - raw RFC822 bytes/text, or
      - plain pasted email text (no headers).
    """
    msg: Message | None = None

    if isinstance(source, Path) or (
        isinstance(source, str) and len(source) < 4096 and Path(source).is_file()
    ):
        raw = Path(source).read_bytes()
        msg = message_from_bytes(raw, policy=policy.default)
    elif isinstance(source, bytes):
        msg = message_from_bytes(source, policy=policy.default)
    elif "\n" in source and re.match(r"^[A-Za-z-]+:\s", source):
        # Looks like it has RFC822 headers.
        msg = message_from_string(source, policy=policy.default)

    if msg is None:
        # Treat as plain pasted text.
        subject = _first_line_subject(str(source))
        return subject, _normalize(str(source))

    subject = str(msg.get("Subject", "") or "")
    body = _extract_body(msg)
    return subject, _normalize(body)


def _first_line_subject(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:200]
    return ""


def _extract_body(msg: Message) -> str:
    """Prefer text/plain; fall back to stripped text/html."""
    plain: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if part.get_content_maintype() == "multipart":
                continue
            payload = _decode_part(part)
            if ctype == "text/plain":
                plain.append(payload)
            elif ctype == "text/html":
                html_parts.append(payload)
    else:
        payload = _decode_part(msg)
        if msg.get_content_type() == "text/html":
            html_parts.append(payload)
        else:
            plain.append(payload)

    if plain:
        return "\n".join(plain)
    return _strip_html("\n".join(html_parts))


def _decode_part(part: Message) -> str:
    # Under the modern email policy, get_content() returns decoded str for text.
    if isinstance(part, EmailMessage):
        try:
            content = part.get_content()
            if isinstance(content, str):
                return content
        except (LookupError, KeyError):
            pass
    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")


class _HtmlToText(HTMLParser):
    """Collect visible text from HTML, dropping script/style and head content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in _HTML_SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _HTML_BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _HTML_SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _HTML_BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def _strip_html(raw: str) -> str:
    parser = _HtmlToText()
    parser.feed(raw)
    parser.close()
    return parser.text()


def _normalize(text: str) -> str:
    lines = [_MULTISPACE_RE.sub(" ", ln).strip() for ln in text.splitlines()]
    # Collapse runs of blank lines.
    out: list[str] = []
    blank = False
    for ln in lines:
        if ln:
            out.append(ln)
            blank = False
        elif not blank:
            out.append("")
            blank = True
    return "\n".join(out).strip()


def parse_money(token: str, unit: str | None) -> float | None:
    """Convert a matched money token + unit suffix to a float in USD."""
    try:
        value = float(token.replace(",", ""))
    except ValueError:
        return None
    unit_l = (unit or "").lower()
    if unit_l in ("k", "thousand"):
        value *= 1_000
    elif unit_l in ("m", "million"):
        value *= 1_000_000
    elif unit_l in ("b", "billion"):
        value *= 1_000_000_000
    return value


def _money_near(text: str, keywords: tuple[str, ...], window: int = 40) -> float | None:
    """
    Find the dollar amount most closely associated with any of ``keywords``.

    Within ``window`` chars on either side of a keyword, pick the money mention
    *closest* to the keyword (so "$1.2M ... $10M valuation cap" yields $10M for
    "cap", not the earlier $1.2M).
    """
    low = text.lower()
    best: tuple[int, float] | None = None  # (distance, amount)
    for kw in keywords:
        for m in re.finditer(re.escape(kw), low):
            start = max(0, m.start() - window)
            end = min(len(text), m.end() + window)
            kw_pos = m.start() - start
            for mm in _MONEY_RE.finditer(text[start:end]):
                amount = parse_money(mm.group(1), mm.group(2))
                if amount is None:
                    continue
                distance = abs(mm.start() - kw_pos)
                if best is None or distance < best[0]:
                    best = (distance, amount)
    return best[1] if best else None


def parse_email(
    source: str | bytes | Path,
    *,
    source_name: str | None = None,
) -> Deal:
    """Parse an email source into a :class:`Deal` using deterministic heuristics."""
    subject, body = read_email(source)
    text = f"{subject}\n{body}".strip()

    deal = Deal(
        company=_extract_company(subject, body),
        source=source_name or (subject[:120] or None),
        raw_text=text,
    )

    deal.valuation_cap = _money_near(text, ("cap", "valuation", "post-money", "pre-money"))
    deal.round_size = _money_near(text, ("raising", "round", "target", "total round"))
    deal.allocation = _money_near(text, ("allocation", "allocated", "carve", "syndicate"))

    stage_m = _STAGE_RE.search(text)
    if stage_m:
        deal.stage = stage_m.group(1).lower().replace(" ", "-").replace("preseed", "pre-seed")

    inst_m = _INSTRUMENT_RE.search(text)
    if inst_m:
        instrument = inst_m.group(1)
        deal.instrument = "SAFE" if instrument.lower() == "safe" else instrument.lower()

    deal.lead = _extract_lead(subject, body)
    deal.deadline = _extract_deadline(text)
    deal.one_liner = _extract_one_liner(body, deal.company)
    deal.links = _extract_links(text)
    deal.website = _pick_website(deal.links)
    deal.founders = _extract_founders(text)

    return deal


def _extract_company(subject: str, body: str) -> str:
    """
    Best-effort company name.

    Tries high-precision body cues first (syndicate emails name the company in
    predictable phrasings), then falls back to the subject line, which is often
    cluttered with investor names and metrics.
    """
    from_body = _company_from_body(body)
    if from_body:
        return from_body

    subj = subject.strip()
    # Drop common forwarding/syndicate prefixes.
    subj = re.sub(r"^(re|fwd|fw)\s*:\s*", "", subj, flags=re.IGNORECASE).strip()
    subj = re.sub(
        r"^(new deal|deal|syndicate|invest in|investment opportunity)\s*[:\-]\s*",
        "",
        subj,
        flags=re.IGNORECASE,
    ).strip()
    # "Acme - AI for X" -> "Acme"
    for sep in (" - ", " — ", ": ", " | "):
        if sep in subj:
            candidate = subj.split(sep, 1)[0].strip()
            if candidate:
                return candidate
    if subj:
        return subj[:120]
    # Fall back to first non-empty body line.
    for line in body.splitlines():
        if line.strip():
            return line.strip()[:120]
    return "Unknown"


# A company name: capitalized token(s), allowing internal & and - and digits.
# Note: no internal '.', so a match stops at a sentence boundary ("Gamma. Great").
_CO = r"[A-Z][A-Za-z0-9&-]*(?:[ ][A-Z][A-Za-z0-9&-]*){0,3}"

# High-precision body phrasings that name the company, tried in order.
_COMPANY_BODY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(rf"(?i:in|into)\s+our\s+({_CO})\s+(?i:deal|round|spv)"),
    re.compile(rf"(?i:investing\s+in|invest\s+in)\s+({_CO})"),
    re.compile(rf"({_CO})\s+(?:is|are)\s+(?:a|an|the|now|building|reinventing|transforming)\b"),
    re.compile(rf"({_CO})\s+(?:builds?|makes?|operates?|provides?|offers?|develops?)\b"),
    re.compile(rf"(?i:backed)\s+({_CO})\b"),
)


def _company_from_body(body: str) -> str | None:
    for pattern in _COMPANY_BODY_PATTERNS:
        m = pattern.search(body)
        if m:
            name = m.group(1).strip(" .,-")
            if name:
                return name
    return None


# A person's name: capitalized words joined by single spaces, no trailing dot.
_NAME = r"[A-Z][a-zA-Z'’-]+(?:[ ][A-Z][a-zA-Z'’-]+){0,2}"


def _extract_lead(subject: str, body: str) -> str | None:
    m = re.search(rf"led\s+by\s+({_NAME})", body)
    if m:
        return m.group(1).strip()
    m = re.search(rf"\bsyndicate\s+lead[:\s]+({_NAME})", body)
    if m:
        return m.group(1).strip()
    return None


def _extract_deadline(text: str) -> str | None:
    m = re.search(
        r"(?:deadline|closes?|closing|commit by)[:\s]+([^\n.]{3,60})",
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    return None


_ONE_LINER_SKIP = (
    "http",
    "from:",
    "to:",
    "sent:",
    "subject:",
    "hi ",
    "hi,",
    "hello",
    "hey",
    "dear ",
    "thanks",
    "thank you",
    "best,",
    "best regards",
    "regards",
    "cheers",
    "as a reminder",
    "we have",
    "we are",
    "we're",
)
_ONE_LINER_VERBS = r"(?:is|are|builds?|makes?|operates?|provides?|offers?|develops?)"


def _extract_one_liner(body: str, company: str | None = None) -> str | None:
    # Prefer the company's own pitch sentence, e.g. "Campus is a new way to ...".
    if company and company != "Unknown":
        m = re.search(rf"{re.escape(company)}\s+{_ONE_LINER_VERBS}\b[^.\n]{{0,200}}", body)
        if m:
            return _MULTISPACE_RE.sub(" ", m.group(0)).strip()[:200]
    # Otherwise the first substantive line that isn't a greeting/signature.
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if 20 <= len(line) <= 200 and not line.lower().startswith(_ONE_LINER_SKIP):
            return line
    return None


def _extract_links(text: str) -> list[str]:
    seen: list[str] = []
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(".,);")
        if url not in seen:
            seen.append(url)
    return seen


def _pick_website(links: list[str]) -> str | None:
    for url in links:
        low = url.lower()
        if not any(host in low for host in _SKIP_HOSTS):
            return url
    return None


def _extract_founders(text: str) -> list[Founder]:
    founders: list[Founder] = []
    # Keyword is case-insensitive; the name itself must stay case-sensitive
    # (otherwise IGNORECASE lets [A-Z] match a following lowercase word).
    for m in re.finditer(
        rf"(?i:co-?founder|founder|ceo|cto)[:\s,]+({_NAME})",
        text,
    ):
        name = m.group(1).strip()
        if " " in name and name not in {f.name for f in founders}:
            founders.append(Founder(name=name))
    return founders


def is_complete(deal: Deal) -> bool:
    """
    True when deterministic extraction got enough to skip the LLM fallback.

    Requires a real company name plus at least ``_MIN_SIGNAL_FIELDS`` of the
    economically meaningful fields.
    """
    if not deal.company or deal.company == "Unknown":
        return False
    signal = [
        deal.valuation_cap is not None,
        deal.round_size is not None,
        deal.instrument is not None,
        deal.website is not None,
        bool(deal.founders),
    ]
    return sum(signal) >= _MIN_SIGNAL_FIELDS
