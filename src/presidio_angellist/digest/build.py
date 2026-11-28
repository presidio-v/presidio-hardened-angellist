"""
Compile digest LaTeX to PDF with an external ``xelatex``, in a sandboxed way.

Controls (defence in depth behind the escaping in :mod:`latex`):

- ``-no-shell-escape``: ``\\write18`` can never run a command, whatever the
  local ``texmf.cnf`` says; ``shell_escape=f`` is also forced in the environment.
- A pre-flight scan (:func:`check_tex_source`) refuses to compile a document that
  contains any file-, shell- or catcode-level primitive (``\\input``, ``\\write``,
  ``\\openin``, ``\\catcode``, ``\\csname``, ``^^`` ...). The templates never use
  these, so their presence means escaping was bypassed somewhere; the build fails
  closed instead of running TeX on it.
- ``openout_any=p`` (kpathsea "paranoid"): TeX may not write outside the job
  directory or to dot-files. ``openin_any=p`` additionally refuses dot-files on
  read. (It does **not** stop reading an absolute path on current TeX Live, which
  is why the pre-flight scan exists.)
- The job runs in a fresh temporary directory holding only the ``.tex`` source and
  the copied logo; nothing else of the caller's filesystem is in reach by
  relative path. The directory is deleted afterwards.
- ``-interaction=nonstopmode -halt-on-error`` and a wall-clock timeout, so a bad
  document fails fast instead of hanging an unattended run.
- The command line is a fixed argument list (no shell), and the binary is
  resolved once with :func:`shutil.which` or taken from explicit configuration.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_log = logging.getLogger("presidio_angellist")

_DEFAULT_TIMEOUT = 300.0
_EXTRA_BIN_DIRS = ("/Library/TeX/texbin", "/usr/local/texlive/bin", "/opt/homebrew/bin")


class DigestBuildError(RuntimeError):
    """Raised when xelatex is missing or fails to build the PDF."""


# Primitives the digest templates never emit. Any occurrence means untrusted text
# reached the source unescaped, so the build is refused.
_FORBIDDEN_RE = re.compile(
    r"\\(?:input|include(?![a-z])|InputIfFileExists|openin|openout|write|read(?![a-z])|"
    r"immediate|catcode|csname|endcsname|directlua|latelua|special|"
    r"[egx]?def(?![a-z])|let(?![a-z])|futurelet|expandafter|scantokens|"
    r"lowercase|uppercase|errmessage|message|typeout|usepackage|documentclass)"
    r"|\^\^",
)


def check_tex_source(source: str) -> None:
    """Fail closed if the document contains a primitive the templates never use."""
    body = source.split("\\begin{document}", 1)
    scan = body[1] if len(body) == 2 else source
    m = _FORBIDDEN_RE.search(scan)
    if m:
        raise DigestBuildError(
            f"refusing to compile: forbidden TeX primitive {m.group(0)!r} in the document body"
        )


def find_xelatex(explicit: str | None = None) -> str | None:
    """Locate ``xelatex``: explicit path, ``$ANGELTRIAGE_XELATEX``, ``PATH``, MacTeX dir."""
    for cand in (explicit, os.environ.get("ANGELTRIAGE_XELATEX")):
        if cand:
            return cand if Path(cand).is_file() else None
    found = shutil.which("xelatex")
    if found:
        return found
    for d in _EXTRA_BIN_DIRS:
        p = Path(d) / "xelatex"
        if p.is_file():
            return str(p)
    return None


def xelatex_command(binary: str) -> list[str]:
    return [binary, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "d.tex"]


def _sandbox_env(binary: str) -> dict[str, str]:
    env = {
        "PATH": os.pathsep.join([str(Path(binary).parent), "/usr/bin", "/bin"]),
        "HOME": os.environ.get("HOME", "/nonexistent"),
        "openin_any": "p",
        "openout_any": "p",
        "shell_escape": "f",
        "LANG": "C.UTF-8",
    }
    # TeX caches (font name lookups) must be writable; keep them under TMPDIR if set.
    for key in ("TMPDIR", "TEXMFVAR", "TEXMFCONFIG", "TEXMFHOME"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def _first_errors(log: str) -> str:
    errs = [ln for ln in log.splitlines() if ln.startswith("!")]
    i = log.find("\n!")
    tail = log[i : i + 600] if i >= 0 else log[-600:]
    return "\n".join(errs[:5]) + "\n" + tail


def compile_pdf(
    tex_source: str,
    out_pdf: str | Path,
    *,
    logo: Path | None = None,
    xelatex: str | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    keep_tex: bool = False,
    check: bool = True,
) -> Path:
    """Compile ``tex_source`` to ``out_pdf``. Returns the output path.

    ``logo`` is copied into the job directory as ``logo<suffix>``; the LaTeX must
    reference it by that relative name. ``check`` runs :func:`check_tex_source`
    first; it is only turned off by tests that exercise the TeX-level controls.
    """
    if check:
        check_tex_source(tex_source)
    binary = find_xelatex(xelatex)
    if binary is None:
        raise DigestBuildError(
            "xelatex not found; install TeX Live / MacTeX or set ANGELTRIAGE_XELATEX"
        )
    out = Path(out_pdf)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="angeltriage-digest-") as td:
        job = Path(td)
        if logo is not None:
            shutil.copyfile(logo, job / f"logo{logo.suffix.lower()}")
        (job / "d.tex").write_text(tex_source, encoding="utf-8")
        env = _sandbox_env(binary)
        for _ in range(2):  # second pass resolves LastPage
            try:
                res = subprocess.run(
                    xelatex_command(binary),
                    cwd=job,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise DigestBuildError(f"xelatex timed out after {timeout:g}s") from exc
            if res.returncode != 0:
                log_path = job / "d.log"
                log = (
                    log_path.read_text(errors="replace")
                    if log_path.is_file()
                    else res.stdout + res.stderr
                )
                raise DigestBuildError("xelatex failed:\n" + _first_errors(log))
        pdf = job / "d.pdf"
        if not pdf.is_file():
            raise DigestBuildError("xelatex reported success but wrote no PDF")
        shutil.copyfile(pdf, out)
        if keep_tex:
            shutil.copyfile(job / "d.tex", out.with_suffix(".tex"))
    # Confidential output: owner-only.
    os.chmod(out, 0o600)
    if keep_tex:
        os.chmod(out.with_suffix(".tex"), 0o600)
    _log.info("presidio_angellist: digest written to %s", out)
    return out
