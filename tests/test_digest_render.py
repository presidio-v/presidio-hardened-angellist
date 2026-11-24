"""LaTeX escaping, injection resistance, document assembly and the xelatex wrapper."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from digest_helpers import (
    AGG_CONTENT,
    BRAND,
    CSV,
    GATE,
    VINTAGE_CONTENT,
    csv_text,
    fake_xelatex,
)

from presidio_angellist.digest.build import (
    DigestBuildError,
    check_tex_source,
    compile_pdf,
    find_xelatex,
    xelatex_command,
)
from presidio_angellist.digest.config import (
    Brand,
    DigestConfigError,
    load_brand,
    load_content,
    normalise_content,
    parse_brand,
)
from presidio_angellist.digest.csvload import in_years, load_positions, parse_positions
from presidio_angellist.digest.gate import load_gate_config
from presidio_angellist.digest.latex import (
    grouped_columns,
    hbar_chart,
    hex_color,
    money,
    safe_url,
    short_name,
    tex,
    tex_url,
)
from presidio_angellist.digest.render import (
    DocMeta,
    build_aggregate_tex,
    build_vintage_tex,
    gate_check_items,
    the,
)

XELATEX = find_xelatex()
needs_xelatex = pytest.mark.skipif(XELATEX is None, reason="xelatex not installed")

INJECTIONS = [
    r"\input{/etc/passwd}",
    r"\write18{touch /tmp/pwned}",
    r"\immediate\write18{id}",
    r"}\end{document}\input{/etc/passwd}",
    r"$\csname input\endcsname{/etc/passwd}$",
    "^^5cinput{/etc/passwd}",
    r"\catcode`\@=0 @input{/etc/passwd}",
    "[evil]#&%~_{}",
    r"\href{file:///etc/passwd}{x}",
    "\x00\x1b[31mctl‮",
]


def _cfg():
    return load_gate_config(GATE)


def _meta(label="2026 vintage"):
    return DocMeta("2026-Q4", "2026-11-01", label)


# ---------------------------------------------------------------- escaping


@pytest.mark.parametrize("payload", INJECTIONS)
def test_tex_neutralises_control_sequences(payload):
    out = tex(payload)
    # No raw backslash may survive except those this module emitted for escapes.
    stripped = re.sub(
        r"\\(?:textbackslash|textasciitilde|textasciicircum|textless|"
        r"textgreater|textbar|textquotedbl)\{\}|\\[&%$#_{}]",
        "",
        out,
    )
    assert "\\" not in stripped
    # Braces only appear as escapes or the empty groups we emit.
    assert "{" not in stripped.replace("{[}", "").replace("{]}", "")
    assert "\x00" not in out and "\x1b" not in out and "‮" not in out


def test_tex_specific_mappings():
    assert tex("a & b") == r"a \& b"
    assert tex("100%") == r"100\%"
    assert tex("$5") == r"\$5"
    assert tex("#1") == r"\#1"
    assert tex("a_b") == r"a\_b"
    assert tex("{x}") == r"\{x\}"
    assert tex("~") == r"\textasciitilde{}"
    assert tex("^") == r"\textasciicircum{}"
    assert tex("\\") == r"\textbackslash{}"
    assert tex("[opt]") == "{[}opt{]}"
    assert tex("line\nbreak") == "line break"
    assert tex(None) == ""
    assert tex("a — b") == "a -- b"


def test_url_escaping_and_scheme_allowlist():
    assert tex_url("javascript:alert(1)") is None
    assert tex_url("file:///etc/passwd") is None
    assert tex_url("run:/bin/sh") is None
    assert tex_url("https://") is None
    assert tex_url("") is None
    assert tex_url("http://exa\x00mple.com") is None
    u = tex_url("https://example.com/a b?x=1&y=2#frag}\\{~^")
    assert u is not None
    assert "\\&" in u and "\\#" in u
    assert not re.search(r"[{}~^ ]", u)
    assert "\\" not in u.replace("\\%", "").replace("\\#", "").replace("\\&", "")
    assert safe_url("https://example.com/x") == "https://example.com/x"


def test_helpers():
    assert hex_color("#a1b2c3", "000000") == "A1B2C3"
    assert hex_color("red}\\", "000000") == "000000"
    assert money(None) == "--"
    assert money(0) == r"\$0"
    assert money(68_900) == r"\$68.9k"
    assert money(30_000_000) == r"\$30M"
    assert money(-2_500) == r"-\$2.5k"
    assert short_name("Acme Robotics (YC W24)") == "Acme Robotics"
    assert the("LP decision gate") == "the LP decision gate"
    assert the("the gate") == "the gate"


def test_charts_escape_labels():
    out = hbar_chart([(r"\input{x}", 5.0, "dgred"), ("n/a", None, "dggray")], 4, 10, str)
    assert r"\input{x}" not in out and r"\textbackslash{}input\{x\}" in out
    out = hbar_chart(
        [("a", 1e7, "dgred")], 4, 1e8, str, log=True, vmin=1e6, refs=[(2e7, "c", "x")]
    )
    assert "dashed" in out
    out = grouped_columns([(r"\x", [[(1.0, "dgred")], [(2.0, "a"), (0.0, "b")]])], [("l}", "a")])
    assert r"\textbackslash{}x" in out and r"l\}" in out


# ---------------------------------------------------------------- config / content


def test_brand_defaults_and_validation(tmp_path):
    b = load_brand(None)
    assert b.classification == "TLP:AMBER" and b.logo is None
    b = load_brand(BRAND)
    assert b.name == "Example Ventures" and b.file_stem == "Example-Ventures"
    with pytest.raises(DigestConfigError):
        parse_brand({"font": r"Evil}\input{x"})
    with pytest.raises(DigestConfigError):
        parse_brand({"colors": "red"})
    with pytest.raises(DigestConfigError):
        parse_brand({"logo": "logo.svg"}, tmp_path)
    with pytest.raises(DigestConfigError):
        parse_brand({"logo": "missing.png"}, tmp_path)
    (tmp_path / "logo.png").write_bytes(b"\x89PNG")
    b = parse_brand({"logo": "logo.png", "colors": {"navy": "nothex"}}, tmp_path)
    assert b.logo == tmp_path / "logo.png" and b.colors["navy"] == "1E293B"
    assert Brand(name="!!!").file_stem == "Digest"


def test_brand_json_and_bad_files(tmp_path):
    p = tmp_path / "brand.json"
    p.write_text(json.dumps({"name": "X", "doc_id_prefix": "X-D", "file_prefix": "x"}))
    assert load_brand(p).doc_id_prefix == "X-D"
    p.write_text("[1]")
    with pytest.raises(DigestConfigError):
        load_brand(p)
    p.write_text("{bad")
    with pytest.raises(DigestConfigError):
        load_brand(p)
    t = tmp_path / "brand.toml"
    t.write_text("name = ")
    with pytest.raises(DigestConfigError):
        load_brand(t)
    with pytest.raises(DigestConfigError):
        load_brand(tmp_path / "missing.toml")


def test_normalise_content_drops_junk():
    c = normalise_content(
        {
            "headline": 3,
            "thesis": {"pillars": [{"title": "T", "text": "x"}, "junk"], "statement": {}},
            "summary": {"paragraphs": ["a", None, 5], "actions": "notalist"},
            "companies": {
                "A": {
                    "status": "Wildly ahead",
                    "signals": "nope",
                    "p_up_round": 1.5,
                    "sources": [
                        {"label": "ok", "url": "https://example.com"},
                        {"label": "bad", "url": "javascript:alert(1)"},
                        "junk",
                    ],
                },
                "B": "junk",
            },
        }
    )
    assert c["headline"] == "3"
    assert c["thesis"]["pillars"] == [{"title": "T", "text": "x"}]
    assert c["summary"]["paragraphs"] == ["a", "5"]
    assert c["summary"]["actions"] == []
    a = c["companies"]["A"]
    assert a["status"] == "No signal" and a["signals"] == [] and "p_up_round" not in a
    assert a["sources"] == [{"label": "ok", "url": "https://example.com"}]
    assert c["companies"]["B"] == {}
    with pytest.raises(DigestConfigError):
        normalise_content([])
    assert load_content(None)["summary"]["paragraphs"] == []
    assert load_content(Path("/nonexistent/x.json"))["thesis"]["statement"] == ""


def test_gate_check_items_from_config_and_content():
    cfg = _cfg()
    items = gate_check_items(cfg, {"thesis": {}})
    assert any("$25M post-money" in i for i in items)
    assert any("$12k per lead per year" in i for i in items)
    assert gate_check_items(cfg, {"thesis": {"gate_checks": ["Only this."]}}) == ["Only this."]


# ---------------------------------------------------------------- document assembly


def _vintage_tex(content=None, positions=None, brand=None):
    ps = positions if positions is not None else in_years(load_positions(CSV), 2026)
    return build_vintage_tex(
        ps,
        _cfg(),
        content if content is not None else load_content(VINTAGE_CONTENT),
        brand or load_brand(BRAND),
        _meta(),
        2026,
    )


def test_vintage_tex_structure():
    out = _vintage_tex()
    assert out.startswith(r"\documentclass") and out.rstrip().endswith(r"\end{document}")
    for needle in ("Company cards", "Gate retro-check", "Portfolio at a glance", "TLP:AMBER"):
        assert needle in out
    assert r"\IfFontExistsTF{Helvetica Neue}" in out
    assert r"\href{https://example.com/kestrel?a=1\&b=2\#news}" in out


def test_vintage_tex_without_content_or_probabilities():
    out = _vintage_tex(content=normalise_content({}))
    assert "Outlook" not in out and "No advisor assessment" in out


def test_aggregate_tex_structure():
    ps = in_years(load_positions(CSV), 2017, 2020)
    out = build_aggregate_tex(
        ps, _cfg(), load_content(AGG_CONTENT), load_brand(BRAND), _meta("2017-2020"), (2017, 2020)
    )
    for needle in (
        "Would the gate have helped?",
        "TVPI, locked at cost",
        "By syndicate lead",
        "Holdings to watch",
        "Top positions by net value",
    ):
        assert needle in out
    # A holding not in the band still renders, flagged.
    content = load_content(AGG_CONTENT)
    content["holdings"]["Not In Band Co"] = {"status": "Behind"}
    out = build_aggregate_tex(ps, _cfg(), content, Brand(), _meta("2017-2020"), (2017, 2020))
    assert "not in this band" in out


def _hostile_csv() -> str:
    rows = []
    for i, name in enumerate(INJECTIONS):
        safe = name.replace('"', '""')
        rows.append(
            f'"{safe}",Live,01/0{1 + i % 9}/2026,"$1,000",Locked,$0,Locked,,"{safe}","{safe}",'
            f'Syndicate,Direct,"{safe}","{safe}",F,,"{safe}",,,,"{safe}",20%,'
        )
    return csv_text(*rows)


def _hostile_content() -> dict:
    hostile = r"\input{/etc/passwd}\write18{id}"
    return normalise_content(
        {
            "headline": hostile,
            "thesis": {
                "statement": hostile,
                "pillars": [{"title": hostile, "text": hostile}],
                "vintage_note": hostile,
                "gate_checks": [hostile],
            },
            "summary": {
                k: [hostile]
                for k in ("paragraphs", "strongest", "weakest", "actions", "lessons_for_gate")
            },
            "companies": {
                INJECTIONS[0]: {
                    "one_liner": hostile,
                    "signals": [hostile],
                    "forecast": hostile,
                    "sources": [{"label": hostile, "url": "https://e.com/}\\input{/etc/passwd}"}],
                }
            },
        }
    )


def test_hostile_csv_and_content_never_reach_tex_raw():
    ps = parse_positions(_hostile_csv())
    brand = Brand(name=r"\input{/etc/passwd}", tagline=r"\write18{id}", header_text="^^5c")
    out = _vintage_tex(content=_hostile_content(), positions=ps, brand=brand)
    for needle in (r"\input{", r"\write18", "^^5c", r"\csname", r"\catcode"):
        assert needle not in out, needle
    out = build_aggregate_tex(ps, _cfg(), _hostile_content(), brand, _meta("2026"), (2026, 2026))
    for needle in (r"\input{", r"\write18", "^^5c"):
        assert needle not in out, needle


# ---------------------------------------------------------------- compile wrapper


def test_compile_with_fake_xelatex_sandbox_flags(tmp_path):
    exe = fake_xelatex(tmp_path)
    logo = tmp_path / "brand-logo.PNG"
    logo.write_bytes(b"\x89PNG")
    out = compile_pdf("doc", tmp_path / "out" / "x.pdf", logo=logo, xelatex=exe, keep_tex=True)
    assert out.read_bytes().startswith(b"%PDF")
    assert (out.stat().st_mode & 0o777) == 0o600
    assert out.with_suffix(".tex").read_text() == "doc"
    assert xelatex_command("xe")[1] == "-no-shell-escape"


def test_compile_failure_reports_log(tmp_path):
    exe = fake_xelatex(tmp_path, fail=True)
    with pytest.raises(DigestBuildError, match="Undefined control sequence"):
        compile_pdf("doc", tmp_path / "x.pdf", xelatex=exe)


def test_compile_missing_xelatex(tmp_path, monkeypatch):
    monkeypatch.delenv("ANGELTRIAGE_XELATEX", raising=False)
    with pytest.raises(DigestBuildError, match="xelatex not found"):
        compile_pdf("doc", tmp_path / "x.pdf", xelatex=str(tmp_path / "nope"))
    monkeypatch.setenv("ANGELTRIAGE_XELATEX", str(tmp_path / "nope"))
    assert find_xelatex() is None


def test_compile_env_is_paranoid(tmp_path, monkeypatch):
    seen = {}
    import subprocess

    real_run = subprocess.run

    def spy(cmd, **kw):
        seen.update(kw["env"])
        seen["cmd"] = cmd
        return real_run(cmd, **kw)

    monkeypatch.setattr("presidio_angellist.digest.build.subprocess.run", spy)
    compile_pdf("doc", tmp_path / "x.pdf", xelatex=fake_xelatex(tmp_path))
    assert seen["openin_any"] == "p" and seen["openout_any"] == "p"
    assert seen["shell_escape"] == "f"
    assert "-no-shell-escape" in seen["cmd"]


# ---------------------------------------------------------------- real xelatex


@needs_xelatex
def test_real_render_vintage_and_aggregate(tmp_path):
    out = compile_pdf(_vintage_tex(), tmp_path / "v.pdf")
    assert out.read_bytes()[:4] == b"%PDF"
    ps = in_years(load_positions(CSV), 2017, 2020)
    tex_src = build_aggregate_tex(
        ps, _cfg(), load_content(AGG_CONTENT), load_brand(BRAND), _meta("2017-2020"), (2017, 2020)
    )
    assert compile_pdf(tex_src, tmp_path / "a.pdf").stat().st_size > 1000


@needs_xelatex
def test_real_render_hostile_input_compiles_without_reading_files(tmp_path):
    ps = parse_positions(_hostile_csv())
    out = compile_pdf(
        _vintage_tex(content=_hostile_content(), positions=ps), tmp_path / "h.pdf", keep_tex=True
    )
    assert out.is_file()
    assert not Path("/tmp/pwned").exists()  # noqa: S108 - checks the injected payload's target


@pytest.mark.parametrize(
    "body",
    [
        r"\input{/etc/passwd}",
        r"\include{x}",
        r"\immediate\write18{id}",
        r"\openin1=/etc/passwd",
        r"\catcode`\@=0",
        r"\csname input\endcsname",
        "^^5cinput",
        r"\def\x{y}",
        r"\let\a\b",
        r"\directlua{os.execute()}",
        r"\usepackage{shellesc}",
    ],
)
def test_preflight_refuses_forbidden_primitives(body):
    doc = "\\documentclass{article}\\begin{document}" + body + "\\end{document}"
    with pytest.raises(DigestBuildError, match="forbidden TeX primitive"):
        check_tex_source(doc)


def test_preflight_accepts_generated_documents():
    check_tex_source(_vintage_tex())
    ps = parse_positions(_hostile_csv())
    check_tex_source(_vintage_tex(content=_hostile_content(), positions=ps))


@needs_xelatex
def test_real_xelatex_cannot_write_outside_job_dir(tmp_path):
    # Defence in depth below the pre-flight scan: openout_any=p stops writes to
    # absolute paths even if a document were compiled unchecked.
    target = tmp_path / "escaped.txt"
    doc = (
        "\\documentclass{article}\\begin{document}\\newwrite\\f"
        f"\\immediate\\openout\\f={target}\\immediate\\write\\f{{x}}"
        "\\immediate\\closeout\\f ok\\end{document}"
    )
    with pytest.raises(DigestBuildError):
        compile_pdf(doc, tmp_path / "p.pdf", check=False)
    assert not target.exists()


@needs_xelatex
def test_real_xelatex_shell_escape_disabled(tmp_path):
    marker = tmp_path / "shell-ran"
    doc = (
        "\\documentclass{article}\\begin{document}"
        f"\\immediate\\write18{{touch {marker}}}ok\\end{{document}}"
    )
    compile_pdf(doc, tmp_path / "s.pdf", check=False)
    assert not marker.exists()


def test_tex_drops_pictographs_without_double_gap():
    from presidio_angellist.digest.latex import tex

    assert tex("Alpha \U0001f64f Beta") == "Alpha Beta"
    assert tex("Rocket❤️") == "Rocket"
