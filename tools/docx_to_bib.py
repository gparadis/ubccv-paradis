#!/usr/bin/env python3
"""Convert publication and presentation blocks into data/publications.bib.

Bold/italic are read from the run properties rather than from flattened text,
because the CV uses literal '*' (presenting author) and '^' (HQP) characters
that would otherwise collide with markdown emphasis.

Bold is not stored: it is derivable, since a name is bold exactly when it is
the candidate or carries the '^' HQP marker. The renderer re-applies it.
"""

from __future__ import annotations

import re
import sys
import unicodedata

sys.path.insert(0, "tools")
from lib_blocks import load  # noqa: E402

SELF_SURNAME = "Paradis"

NAME_RE = re.compile(
    # a brace-wrapped name is a single unbreakable token (corporate author, or
    # a surname whose initial the original document never recorded)
    r"(?:\{(?P<braced>[^}]+)\}(?P<bmarks>[*^\u2217]*),?"
    r"|"
    r"(?P<last>(?:[A-ZÀ-ÖØ-Þ][\w'’\-]*)(?:\s+(?:de|van|von|den|der|III|Jr\.?|II)\b|\s+[A-ZÀ-ÖØ-Þ][\w'’\-]*)*)"
    r",\s*"
    # initials must be dotted (G., M.Z., T.-Y.); a bare capital is only
    # accepted at a name boundary, otherwise it eats the first word of a title
    r"(?P<init>[A-ZÀ-ÖØ-Þ]\.(?:\s*-?\s*[A-ZÀ-ÖØ-Þ]\.)*|[A-ZÀ-ÖØ-Þ](?=\s*(?:,|$)))"
    r"(?P<marks>[*^\u2217]*)"
    r")"
)


def _name_of(m: re.Match) -> tuple[str, str]:
    """Return (name, markers) for a NAME_RE match, in 'Last, F.' form."""
    if m.group("braced"):
        return "{" + m.group("braced").strip() + "}", m.group("bmarks") or ""
    last = re.sub(r"\s+", " ", m.group("last")).strip()
    init = re.sub(r"\s+", "", m.group("init"))
    return f"{last}, {init}", m.group("marks") or ""
# A name must be followed by a separator, an opening paren (the year), the end
# of the string, or a capital letter -- the last case meaning the author list
# has ended and the title begins.
AFTER_NAME_RE = re.compile(r"\s*(?:,|;|\band\b|&|\(|$|(?=[A-ZÀ-ÖØ-Þ]))")

YEAR_RE = re.compile(r"\((?P<year>(?:19|20)\d{2}[a-z]?)\)")
DOI_RE = re.compile(r"(?:DOI[: ]\s*|doi\.org/|https?://doi\.org/)(10\.\S+?)(?:[.,;]?\s|$)", re.I)
URL_RE = re.compile(r"https?://\S+")


class Entry:
    def __init__(self) -> None:
        self.fields: dict[str, str] = {}
        self.etype = "misc"
        self.key = ""


# Typos in the Word original, repaired on the way in. Each one was confirmed by
# reading the raw run text; see reference/EXTRACTION-NOTES.md.
TYPO_FIXES = [
    (re.compile(r"\bM\s+acFarlane\b"), "MacFarlane"),          # stray tab mid-name
    (re.compile(r"\bLebel\s+(L\.)"), r"Lebel, \1"),            # missing comma
    (re.compile(r"\bSharma,\s+(?=Shaw\b)"), "{Sharma}, "),     # initial missing
]


def fix_runs(runs: list[dict]) -> list[dict]:
    """Apply the typo repairs run by run so italic offsets stay in sync."""
    out = []
    for r in runs:
        text = r["text"]
        for pattern, repl in TYPO_FIXES:
            text = pattern.sub(repl, text)
        out.append({**r, "text": text})
    return out


def flat(runs: list[dict]) -> str:
    return "".join(r["text"] for r in runs)


def italic_spans(runs: list[dict]) -> list[tuple[int, int]]:
    spans, pos = [], 0
    for r in runs:
        n = len(r["text"])
        if r.get("italic"):
            if spans and spans[-1][1] >= pos - 2 and not flat(runs)[spans[-1][1] : pos].strip():
                spans[-1] = (spans[-1][0], pos + n)
            else:
                spans.append((pos, pos + n))
        pos += n
    return spans


def links(runs: list[dict]) -> list[str]:
    return [r["href"] for r in runs if r.get("href")]


def clean(text: str) -> str:
    text = text.replace("\t", " ").replace("\xa0", " ")
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" .,;")


def parse_authors(segment: str) -> tuple[list[str], list[str], list[str]]:
    """Return (all authors, hqp subset, presenter subset) in 'Last, F.' form."""
    authors, hqp, presenter = [], [], []
    for m in NAME_RE.finditer(segment):
        name, marks = _name_of(m)
        authors.append(name)
        if "^" in marks:
            hqp.append(name)
        if "*" in marks or "\u2217" in marks:
            presenter.append(name)
    return authors, hqp, presenter


def leading_authors(text: str) -> tuple[list[str], list[str], list[str], int]:
    """Parse the contiguous run of names at the start of a string.

    Stops at the first gap, so a title that happens to contain a 'Word, X.'
    pattern cannot be absorbed into the author list. Also returns the offset
    where the author list ends.
    """
    authors, hqp, presenter, pos = [], [], [], 0
    while True:
        skip = re.match(r"\s*", text[pos:])
        pos += skip.end() if skip else 0
        m = NAME_RE.match(text, pos)
        if not m:
            break
        after = AFTER_NAME_RE.match(text, m.end())
        if not after:
            break
        name, marks = _name_of(m)
        authors.append(name)
        if "^" in marks:
            hqp.append(name)
        if "*" in marks or "\u2217" in marks:
            presenter.append(name)
        pos = m.end()
        sep = re.match(r"\s*(?:,\s*|;\s*|\s*&\s*)?(?:and\s+)?", text[pos:])
        pos += sep.end() if sep else 0
    return authors, hqp, presenter, pos


def bibkey(authors: list[str], year: str, title: str, used: set[str]) -> str:
    first = authors[0].split(",")[0] if authors else "anon"
    first = unicodedata.normalize("NFKD", first).encode("ascii", "ignore").decode()
    first = re.sub(r"\W", "", first).lower() or "anon"
    words = [w for w in re.findall(r"[A-Za-z]{3,}", title) if w.lower() not in STOP]
    slug = (words[0].lower() if words else "untitled")[:14]
    base = f"{first}{year or 'nd'}{slug}"
    key, n = base, 1
    while key in used:
        n += 1
        key = f"{base}{chr(ord('a') + n - 1)}"
    used.add(key)
    return key


STOP = {"the", "and", "for", "with", "from", "into", "that", "are", "was"}


def split_entry(runs: list[dict]) -> dict:
    """Break one bibliographic paragraph into author / year / title / tail."""
    text = flat(runs)
    text = re.sub(r"^\s*\d+[.)]\s*", "", text)
    offset = len(flat(runs)) - len(text)
    spans = [(a - offset, b - offset) for a, b in italic_spans(runs)]
    spans = [(a, b) for a, b in spans if b > 0]

    # The year must follow the author list almost immediately. Otherwise a year
    # mentioned inside a title -- 'benchmark of Daugherty (1991)' -- would be
    # mistaken for the publication year and swallow the title with it.
    _, _, _, author_end = leading_authors(text)
    limit = spans[0][0] if spans else len(text)
    ymatch = None
    for cand in YEAR_RE.finditer(text[: max(limit, 1)]):
        if cand.start() - author_end <= 12:
            ymatch = cand
            break
    title, tail, head = "", "", text
    if spans:
        a, b = spans[0]
        # an italic run that starts at position 0 is a title-only entry
        head = text[:a]
        title = clean(text[a:b])
        tail = text[b:]
        for s, e in spans[1:]:
            if s - b <= 3 and not text[b:s].strip():
                title = clean(title + " " + text[s:e])
                tail = text[e:]
                b = e
    elif ymatch:
        head = text[: ymatch.end()]
        rest = text[ymatch.end() :]
        m = re.match(r"\s*\.?\s*(?P<t>[^.]+(?:\.[^.\s][^.]*)*?)\.\s", rest)
        if m:
            title = clean(m.group("t"))
            tail = rest[m.end() :]
        else:
            title = clean(rest)
    else:
        # no italic title and no usable year: the title is the sentence that
        # follows the author list
        rest = text[author_end:].lstrip(" .,;")
        head = text[:author_end]
        m = re.search(r"\.\s+(?=[A-Z(])", rest)
        title, tail = (rest[: m.start()], rest[m.end() :]) if m else (rest, "")
        title = clean(title)

    if ymatch and ymatch.start() < len(head):
        author_seg = text[: ymatch.start()]
        year = ymatch.group("year")
        between = text[ymatch.end() : len(head)]
    else:
        author_seg = head
        year = ymatch.group("year") if ymatch else ""
        between = ""
    return {
        "author_segment": author_seg,
        "year": year,
        "title": title,
        "tail": clean(between + " " + tail),
        "raw": clean(text),
    }


JOURNAL_RE = re.compile(
    r"^(?P<journal>[^,\d]+?)[,\s]+(?P<volume>\d+)"
    r"(?:\s*\((?P<number>[^)]+)\))?"
    # a page range, or a bare article number for online-first journals
    r"(?:[,:]\s*(?P<pages>[\dA-Za-z]+\s*[–—-]+\s*[\dA-Za-z]+|\d{3,6}))?"
)


def venue_fields(tail: str) -> dict:
    """Split a trailing venue string into journal/volume/number/pages."""
    out: dict[str, str] = {}
    rest = tail
    # rejoin DOIs that Word wrapped across a space, e.g. '10.1007/s11676- 025-01840-z'
    rest = re.sub(r"(10\.\d{4,}/\S*[-/])\s+(\S)", r"\1\2", rest)
    doi = DOI_RE.search(rest)
    if doi:
        out["doi"] = doi.group(1).rstrip(".,;").replace(" ", "")
        rest = (rest[: doi.start()] + " " + rest[doi.end() :]).strip()
    rest = re.sub(r"\bDOI\b[: ]*", "", rest, flags=re.I).strip(" .,;")
    note_bits = []
    for pat in (r"\(in press\)", r"Editor[’']s Choice\.?", r"\[computer software\]"):
        m = re.search(pat, rest, re.I)
        if m:
            note_bits.append(m.group(0).strip(" .").strip("()"))
            rest = (rest[: m.start()] + " " + rest[m.end() :]).strip()
    rest = clean(rest)
    m = JOURNAL_RE.match(rest)
    if m and m.group("journal"):
        out["journal"] = clean(m.group("journal"))
        for key in ("volume", "number", "pages"):
            if m.group(key):
                out[key] = re.sub(r"\s*[–—-]+\s*", "--", m.group(key).strip())
        leftover = clean(rest[m.end() :])
        if leftover:
            note_bits.append(leftover)
    elif rest:
        out["journal"] = rest
    # a trailing bare DOI, printed without the 'DOI' label
    if "doi" not in out:
        for i, bit in enumerate(note_bits):
            if re.fullmatch(r"\(?10\.\d{4,}/\S+?\)?", bit):
                out["doi"] = bit.strip("()")
                note_bits.pop(i)
                break
    if note_bits:
        out["note"] = "; ".join(note_bits)
    return out


SCOPE_RE = re.compile(r"\[\s*(international|national|local|regional)\s*\]\.?\s*$", re.I)
PRES_DATE_RE = re.compile(r"(?:^|[\s,.])((?:19|20)\d{2}(?:/\d{2}(?:/\d{2})?)?)\.?\s*$")
ROLE_RE = re.compile(
    r"\b(Invited (?:speaker|panelist|presenter|lecturer)|Keynote(?: speaker)?|"
    r"Guest (?:speaker|lecturer)|Panelist|Plenary(?: speaker)?)\b\.?",
    re.I,
)


def parse_presentation(runs: list[dict], section: str, used: set[str]) -> Entry | None:
    """Presentations read 'Authors. Title. Role. Venue. Place. YYYY/MM [scope]'."""
    parts = split_entry(runs)
    if not parts["raw"]:
        return None
    authors, hqp, presenter = parse_authors(parts["author_segment"])

    title = parts["title"]
    tail = parts["tail"]
    if not authors and not parts["year"] and not tail:
        # no italic title and no year: split the flat string ourselves
        text = parts["raw"]
        authors, hqp, presenter, cut = leading_authors(text)
        rest = text[cut:].lstrip(" .,;")
        m = re.search(r"[.?!]\s+", rest)
        title, tail = (rest[: m.start() + 1], rest[m.end() :]) if m else (rest, "")
        title = clean(title)

    e = Entry()
    e.etype = "misc"
    if authors:
        e.fields["author"] = " and ".join(authors)
    e.fields["title"] = title or parts["raw"]

    scope = SCOPE_RE.search(tail)
    if scope:
        e.fields["scope"] = scope.group(1).lower()
        tail = tail[: scope.start()].strip(" .,;")
    role = ROLE_RE.search(tail)
    if role:
        e.fields["role"] = clean(role.group(1)).capitalize()
        tail = clean(tail[: role.start()] + " " + tail[role.end() :])
    date = PRES_DATE_RE.search(tail)
    if date:
        e.fields["date"] = date.group(1)
        tail = tail[: date.start()].strip(" .,;")
    tail = clean(re.sub(r"^Presented at\s+", "", tail, flags=re.I))
    if tail:
        e.fields["venue"] = tail
    year = parts["year"] or (e.fields.get("date", "")[:4])
    if year:
        e.fields["year"] = year
    if hqp:
        e.fields["hqp"] = " and ".join(dict.fromkeys(hqp))
    if presenter:
        e.fields["presenter"] = " and ".join(dict.fromkeys(presenter))
    e.fields["ubccv"] = section
    e.key = bibkey(authors, year, e.fields["title"], used)
    return e


def build(runs: list[dict], etype: str, section: str, used: set[str]) -> Entry | None:
    parts = split_entry(runs)
    if not parts["raw"]:
        return None
    authors, hqp, presenter = parse_authors(parts["author_segment"])
    e = Entry()
    e.etype = etype
    e.fields["title"] = parts["title"] or parts["raw"]

    seg = parts["author_segment"]
    role = re.search(r"\((editor|editors|eds?\.?)\)", seg, re.I)
    if role:
        e.fields["authorrole"] = role.group(1).lower().rstrip(".")
        seg = seg[: role.start()] + seg[role.end() :]
    if not authors:
        # corporate author, e.g. 'FABLE (2024). ...'
        org = re.match(r"\s*([A-Z][A-Za-z&.\- ]{1,60}?)\s*(?:\(|$)", seg)
        if org and org.group(1).strip():
            authors = [f"{{{org.group(1).strip()}}}"]
    if authors:
        e.fields["author"] = " and ".join(authors)
    if parts["year"]:
        e.fields["year"] = parts["year"]
    e.fields.update(venue_fields(parts["tail"]))
    if etype in ("inproceedings", "incollection") and "journal" in e.fields:
        e.fields["booktitle"] = e.fields.pop("journal")
    urls = links(runs)
    if urls and "doi" not in e.fields:
        e.fields["url"] = urls[0]
    if hqp:
        e.fields["hqp"] = " and ".join(dict.fromkeys(hqp))
    if presenter:
        e.fields["presenter"] = " and ".join(dict.fromkeys(presenter))
    e.fields["ubccv"] = section
    e.key = bibkey(authors, parts["year"], e.fields["title"], used)
    return e


SECTIONS = [
    # (label, block range, bibtex type)
    ("invited_presentation", (134, 176), "misc"),
    ("other_presentation", (177, 292), "misc"),
    ("refereed_journal", (499, 525), "article"),
    ("refereed_proceedings", (526, 531), "inproceedings"),
    ("refereed_other", (532, 535), "misc"),
    ("nonrefereed_journal", (537, 539), "article"),
    ("nonrefereed_proceedings", (540, 541), "inproceedings"),
    ("nonrefereed_other", (542, 635), "misc"),
    ("book_authored", (638, 639), "book"),
    ("book_edited", (640, 643), "book"),
    ("book_chapter", (644, 648), "incollection"),
    ("work_submitted", (661, 668), "unpublished"),
    ("work_in_progress", (669, 680), "unpublished"),
]

SKIP_RE = re.compile(r"^\s*(Symbol Key|\([a-z]\)\s*$)", re.I)


def main() -> None:
    blocks = load()
    used: set[str] = set()
    entries: list[Entry] = []
    for label, (start, end), etype in SECTIONS:
        for i in range(start, min(end, len(blocks))):
            b = blocks[i]
            if b["type"] != "p":
                continue
            runs = fix_runs([r for r in b["runs"] if r["text"].strip()])
            text = flat(runs).strip()
            if not text or SKIP_RE.match(text):
                continue
            if re.match(r"^\(?[a-z]\)", text) and len(text) < 90:
                continue
            if label.endswith("presentation"):
                e = parse_presentation(runs, label, used)
            else:
                e = build(runs, etype, label, used)
            if e:
                entries.append(e)

    order = [
        "author",
        "authorrole",
        "title",
        "year",
        "journal",
        "booktitle",
        "volume",
        "number",
        "pages",
        "venue",
        "role",
        "scope",
        "date",
        "doi",
        "url",
        "note",
        "starred",
        "hqp",
        "presenter",
        "ubccv",
    ]
    out = [
        "% UBC CV publication record.",
        "% 'ubccv' selects the CV subsection; 'hqp'/'presenter' drive the ^ and * markers.",
        "",
    ]
    for e in entries:
        out.append(f"@{e.etype}{{{e.key},")
        for k in order:
            if k in e.fields and e.fields[k]:
                out.append(f"  {k:<10} = {{{e.fields[k]}}},")
        out.append("}\n")
    with open("data/publications.bib", "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print(f"wrote data/publications.bib: {len(entries)} entries")
    from collections import Counter

    for k, v in Counter(e.fields["ubccv"] for e in entries).items():
        print(f"  {k:<26} {v}")


if __name__ == "__main__":
    main()
