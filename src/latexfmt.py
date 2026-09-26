"""Inline markup -> LaTeX, and author-list formatting for the UBC CV."""

from __future__ import annotations

import re

SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

TOKEN_RE = re.compile(
    r"(?P<bold>\*\*(?P<b>.+?)\*\*)"
    r"|(?P<italic>(?<!\*)\*(?P<i>[^*]+?)\*(?!\*))"
    r"|(?P<link>\[(?P<t>[^\]]*)\]\((?P<u>[^)]*)\))"
    r"|(?P<sup>\^\{(?P<s>[^}]*)\})",
    re.S,
)


def esc(text: str) -> str:
    return "".join(SPECIALS.get(c, c) for c in text)


def tex(text: str | None) -> str:
    """Render lightweight inline markup as LaTeX.

    ' \\ ' separates the paragraphs of a multi-paragraph table cell; it becomes
    a line break rather than a stray backslash.
    """
    if not text:
        return ""
    if " \\ " in text:
        return r" \newline ".join(tex(p.strip()) for p in text.split(" \\ ") if p.strip())
    out, pos = [], 0
    for m in TOKEN_RE.finditer(text):
        out.append(esc(text[pos : m.start()]))
        if m.group("bold"):
            out.append(r"\textbf{" + tex(m.group("b")) + "}")
        elif m.group("italic"):
            out.append(r"\textit{" + tex(m.group("i")) + "}")
        elif m.group("link"):
            url = m.group("u")
            label = m.group("t")
            out.append(r"\href{" + url.replace("%", r"\%").replace("#", r"\#") + "}{" + esc(label) + "}")
        elif m.group("sup"):
            out.append(r"\textsuperscript{" + esc(m.group("s")) + "}")
        pos = m.end()
    out.append(esc(text[pos:]))
    return _dashes("".join(out))


PUNCT = {
    "–": "--",
    "—": "---",
    "’": "'",
    "‘": "`",
    "”": "''",
    "“": "``",
    "…": r"\ldots{}",
    "\u00a0": "~",
}


def _dashes(text: str) -> str:
    for src, dst in PUNCT.items():
        text = text.replace(src, dst)
    return text


def cellpar(text: str | None) -> str:
    """A table cell that may hold several paragraphs (joined with ' \\ ')."""
    if not text:
        return ""
    parts = [p.strip() for p in str(text).split(" \\ ") if p.strip()]
    return r" \newline ".join(tex(p) for p in parts)


# ---------------------------------------------------------------------------
# Author lists
# ---------------------------------------------------------------------------
def split_names(field: str | None) -> list[str]:
    if not field:
        return []
    return [n.strip() for n in re.split(r"\s+and\s+", field) if n.strip()]


def display_name(name: str) -> str:
    return name[1:-1].strip() if name.startswith("{") and name.endswith("}") else name


def format_authors(
    field: str | None,
    hqp: str | None = None,
    presenter: str | None = None,
    self_surname: str = "Paradis",
) -> str:
    """Bold the candidate and HQP, mark HQP with ^ and presenters with *.

    This mirrors the convention used throughout the original CV, but derives
    the emphasis from the data instead of storing it.
    """
    names = split_names(field)
    hqp_set = set(split_names(hqp))
    pres_set = set(split_names(presenter))
    out = []
    for name in names:
        shown = esc(display_name(name))
        marks = ""
        if name in pres_set:
            marks += "*"
        if name in hqp_set:
            marks += r"\textsuperscript{\textasciicircum}"
        is_self = display_name(name).split(",")[0].strip() == self_surname
        if is_self or name in hqp_set:
            shown = r"\textbf{" + shown + "}"
        out.append(shown + marks)
    if len(out) > 1:
        return ", ".join(out[:-1]) + " and " + out[-1]
    return out[0] if out else ""
