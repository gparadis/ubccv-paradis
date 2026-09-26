"""Shared helpers for turning docx blocks into source data."""

from __future__ import annotations

import json
import re


def load(path: str = "build/cv_blocks.json") -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def md(runs: list[dict]) -> str:
    """Render a run list as lightweight inline markup.

    Bold and italic carry meaning in this CV (candidate name, HQP co-authors,
    publication titles), so they are preserved rather than flattened.
    """
    out = []
    for run in runs:
        text = run["text"]
        if run.get("footnote"):
            out.append(f"[^{text}]")
            continue
        stripped = text.strip()
        if not stripped:
            out.append(text)
            continue
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()) :]
        body = stripped
        if run.get("vertAlign") == "superscript":
            body = f"^{{{body}}}"
        if run.get("bold"):
            body = f"**{body}**"
        if run.get("italic"):
            body = f"*{body}*"
        if run.get("href"):
            body = f"[{body}]({run['href']})"
        out.append(f"{lead}{body}{trail}")
    return tidy("".join(out))


def tidy(text: str) -> str:
    text = text.replace("\t", " ").replace("\xa0", " ")
    text = re.sub(r"\*\*\s*\*\*", "", text)
    text = re.sub(r"(?<!\*)\*\*(\s+)", r"\1**", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    return text.strip()


def cell(c: dict) -> str:
    """Flatten a table cell to inline markup, joining its paragraphs."""
    parts = [md(p["runs"]) for p in c.get("paras", []) if p.get("runs")]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    return " \\ ".join(parts) if len(parts) > 1 else parts[0]


def rows(table: dict, skip: int = 1) -> list[list[str]]:
    return [[cell(c) for c in row] for row in table["rows"][skip:]]


def nonempty(row: list[str]) -> bool:
    return any(v.strip() for v in row)


def plain(text: str) -> str:
    """Strip inline markup, for comparison and for plain fields."""
    text = re.sub(r"\[\^[^\]]*\]", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\^\{([^}]*)\}", r"\1", text)
    return text.replace("**", "").replace("*", "").strip()


def sections(blocks: list[dict]) -> dict[str, int]:
    """Map heading text to block index for underlined bold headings."""
    found = {}
    for i, b in enumerate(blocks):
        if b["type"] != "p":
            continue
        runs = [r for r in b["runs"] if r["text"].strip()]
        if runs and all(r.get("underline") for r in runs):
            key = re.sub(r"^[0-9]+\.\s*", "", plain(b["text"])).strip()
            found.setdefault(key, i)
    return found


def subsections(blocks: list[dict], start: int, end: int) -> list[tuple[str, int]]:
    """Find italic '(a) Title' subsection markers within a block range."""
    out = []
    for i in range(start, end):
        b = blocks[i]
        if b["type"] != "p":
            continue
        runs = [r for r in b["runs"] if r["text"].strip()]
        if not runs or not all(r.get("italic") for r in runs):
            continue
        m = re.match(r"^\(([a-z])\)\s*(.*)$", plain(b["text"]))
        if m:
            out.append((m.group(1), i))
    return out
