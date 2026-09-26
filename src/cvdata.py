"""Load the YAML + BibTeX sources into the structure the template expects."""

from __future__ import annotations

import os
import re

import bibtexparser
import yaml

from latexfmt import esc, format_authors, tex

DATA = os.environ.get("CV_DATA", "data")

YAML_FILES = ("profile", "teaching", "research", "service", "awards", "other")


def load_yaml() -> dict:
    out = {}
    for name in YAML_FILES:
        with open(os.path.join(DATA, f"{name}.yaml"), encoding="utf-8") as fh:
            out[name] = yaml.safe_load(fh) or {}
    return out


def load_bib() -> list[dict]:
    library = bibtexparser.parse_file(os.path.join(DATA, "publications.bib"))
    entries = []
    for e in library.entries:
        fields = {k: v for k, v in ((f.key, f.value) for f in e.fields)}
        fields["_type"] = e.entry_type
        fields["_key"] = e.key
        entries.append(fields)
    return entries


def by_section(entries: list[dict]) -> dict[str, list[dict]]:
    """Group entries by CV subsection, keeping the order given in the .bib.

    Order is deliberately not computed. The guide requires reverse
    chronological order, but ties and 'in press' items need human judgement,
    so the .bib file is the place to express it.
    """
    out: dict[str, list[dict]] = {}
    for e in entries:
        out.setdefault(e.get("ubccv", "unfiled"), []).append(e)
    return out


# ---------------------------------------------------------------------------
# Reference rendering
# ---------------------------------------------------------------------------
def _authors(e: dict, self_surname: str) -> str:
    return format_authors(
        e.get("author"), e.get("hqp"), e.get("presenter"), self_surname
    )


def _year(e: dict) -> str:
    return f" ({e['year']})." if e.get("year") else ""


def _doi_or_url(e: dict) -> str:
    if e.get("doi"):
        doi = e["doi"]
        return r" DOI \href{https://doi.org/" + doi + "}{" + esc(doi) + "}."
    if e.get("url"):
        url = e["url"]
        return r" \href{" + url + "}{" + esc(url) + "}."
    return ""


def reference(e: dict, self_surname: str = "Paradis") -> str:
    """Format one bibliography entry in the style used across the CV."""
    bits = []
    authors = _authors(e, self_surname)
    if authors:
        role = f" ({e['authorrole']})" if e.get("authorrole") else ""
        bits.append(authors + role + _year(e))
    elif e.get("year"):
        bits.append(f"({e['year']}).")
    if e.get("title"):
        bits.append(r"\textit{" + tex(e["title"]) + "}.")

    venue = e.get("journal") or e.get("booktitle") or e.get("venue")
    if venue:
        chunk = tex(venue)
        if e.get("volume"):
            chunk += f", {esc(e['volume'])}"
            if e.get("number"):
                chunk += f"({esc(e['number'])})"
        if e.get("pages"):
            chunk += f", {esc(e['pages'])}"
        bits.append(chunk + ".")
    if e.get("role"):
        bits.append(tex(e["role"]) + ".")
    if e.get("date"):
        bits.append(esc(e["date"]) + ".")
    if e.get("note"):
        bits.append("(" + tex(e["note"]) + ")")
    text = " ".join(b for b in bits if b)
    text = _doi_or_url(e).join([text, ""]) if _doi_or_url(e) else text
    if e.get("scope"):
        text += f" [{esc(e['scope'])}]"
    text = re.sub(r"\s+", " ", text).replace(" .", ".").strip()
    if is_starred(e):
        # the guide asks for publications of primary importance to be starred
        text = "*" + text
    return text


def is_starred(e: dict) -> bool:
    return str(e.get("starred", "")).strip().lower() in ("yes", "true", "1")


def build_context() -> dict:
    data = load_yaml()
    entries = load_bib()
    sections = by_section(entries)
    surname = data["profile"].get("surname", "Paradis")
    refs = {
        name: [reference(e, surname) for e in items] for name, items in sections.items()
    }
    return {
        **data,
        "refs": refs,
        "counts": {k: len(v) for k, v in sections.items()},
        "has_starred": any(is_starred(e) for e in entries),
    }
