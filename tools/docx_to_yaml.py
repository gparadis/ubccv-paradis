#!/usr/bin/env python3
"""Convert the extracted docx blocks into the YAML source files under data/.

Run once to bootstrap the repository from the legacy Word document. After that
the YAML files are the source of truth and this script is only a reference for
how the original was interpreted.
"""

from __future__ import annotations

import re
import sys

import yaml

sys.path.insert(0, "tools")
from lib_blocks import cell, load, md, nonempty, plain, rows, subsections  # noqa: E402


class Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def _str_presenter(dumper, data):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


Dumper.add_representer(str, _str_presenter)


def write(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, Dumper=Dumper, allow_unicode=True, sort_keys=False, width=100)
    print(f"wrote {path}")


B = load()


def texts(start: int, end: int) -> list[str]:
    """Inline-markup text of every non-empty paragraph in a block range."""
    out = []
    for i in range(start, end):
        if B[i]["type"] != "p":
            continue
        t = md(B[i]["runs"])
        if t:
            out.append(t)
    return out


def para_after(idx: int) -> str:
    for i in range(idx + 1, len(B)):
        if B[i]["type"] == "p" and md(B[i]["runs"]):
            return md(B[i]["runs"])
    return ""


def table_at(idx: int) -> dict:
    return B[idx]


def field(text: str, label: str) -> str:
    """Read 'LABEL: value', stopping at the next ALL-CAPS label on the line."""
    m = re.search(rf"(?<![A-Z]){label}\s*:\s*([^\n]*)", text)
    if not m:
        return ""
    value = m.group(1)
    nxt = re.search(r"\s{2,}[A-Z][A-Z ()/]{2,}\s*:", value)
    if nxt:
        value = value[: nxt.start()]
    return value.strip()


# --------------------------------------------------------------------------
# 1-7  Identity, education, employment
# --------------------------------------------------------------------------
def profile() -> dict:
    head = plain(md(B[3]["runs"]))
    names = plain(md(B[5]["runs"]))
    rank = plain(md(B[11]["runs"]))
    return {
        "date": field(head, "Date").split("Initials")[0].strip(),
        "initials": field(head, "Initials"),
        "surname": field(names, "SURNAME").strip(),
        "first_name": field(names, r"FIRST\s*NAME"),
        "middle_names": field(names, r"MIDDLE NAME\(S\)"),
        "department": field(plain(B[7]["text"]), r"DEPARTMENT/SCHOOL"),
        "faculty": field(plain(B[9]["text"]), "FACULTY"),
        "present_rank": field(rank, "PRESENT RANK").split("SINCE")[0].strip(),
        "rank_since": field(rank, "SINCE"),
        "education": [
            {"institution": r[0], "degree": r[1], "subject": r[2], "dates": r[3]}
            for r in rows(table_at(15))
            if nonempty(r)
        ],
        "special_qualifications": texts(18, 22),
        "employment": {
            "prior_university": [
                {"organization": r[0], "title": r[1], "dates": r[2]}
                for r in rows(table_at(28))
                if nonempty(r)
            ],
            "prior_other": [
                {"organization": r[0], "title": r[1], "dates": r[2]}
                for r in rows(table_at(31))
                if nonempty(r)
            ],
            "at_ubc": [
                {"title": r[0], "dates": r[1]} for r in rows(table_at(39)) if nonempty(r)
            ],
            "tenure_date": "",
        },
        "leaves_of_absence": [],
    }


# --------------------------------------------------------------------------
# 8  Teaching
# --------------------------------------------------------------------------
COURSE_KEYS = (
    "session",
    "course",
    "scheduled_hours",
    "class_size",
    "lectures",
    "tutorials",
    "labs",
    "other",
)


def course_table(idx: int) -> list[dict]:
    """Courses table: grouped by an academic-year banner row."""
    groups: list[dict] = []
    for r in rows(table_at(idx), skip=2):
        vals = [v.strip() for v in r]
        if not nonempty(vals):
            continue
        if len(vals) == 1:
            groups.append({"group": plain(vals[0]), "entries": []})
            continue
        if not groups:
            groups.append({"group": "", "entries": []})
        vals += [""] * (8 - len(vals))
        groups[-1]["entries"].append(
            {k: v for k, v in zip(COURSE_KEYS, vals[:8]) if v}
        )
    return groups


def descriptions(start: int, end: int) -> list[dict]:
    """Course blurbs: bold code + (credits) + italic title, then a description."""
    out: list[dict] = []
    for i in range(start, end):
        if B[i]["type"] != "p":
            continue
        text = md(B[i]["runs"])
        m = re.match(
            r"^\*\*(?P<code>[^*]+?)\s*\*\*\s*\(?(?P<cr>[\d.]+)?\s*credits?\)?\s*\*(?P<title>[^*]+)\*\s*(?P<note>.*)$",
            text,
        )
        if not m:
            m = re.match(r"^\*\*(?P<code>[^*]+?)\s*\*\*\s*\*(?P<title>[^*]+)\*\s*(?P<note>.*)$", text)
            if not m:
                continue
        entry = {"code": plain(m.group("code")).strip(), "title": plain(m.group("title")).strip()}
        try:
            if m.group("cr"):
                entry["credits"] = m.group("cr")
        except IndexError:
            pass
        note = plain(m.group("note")).strip(" []")
        if note:
            entry["institution"] = note
        desc = para_after(i)
        if desc and not desc.startswith("**"):
            body = plain(desc)
            hours = re.search(r"\[([\d\-]+)\]\s*$", body)
            if hours:
                entry["contact_pattern"] = hours.group(1)
                body = body[: hours.start()].strip()
            entry["description"] = body
        out.append(entry)
    return out


def supervision(idx: int) -> list[dict]:
    groups: list[dict] = []
    for r in rows(table_at(idx), skip=2):
        vals = [v.strip() for v in r]
        if not nonempty(vals):
            continue
        if len([v for v in vals if v]) == 1 and not re.search(r"\d{4}", vals[0]):
            groups.append({"group": plain(vals[0]), "entries": []})
            continue
        if not groups:
            groups.append({"group": "", "entries": []})
        vals += [""] * (5 - len(vals))
        entry = {"student": vals[0], "program": vals[1], "start": vals[2]}
        if vals[3]:
            entry["finish"] = vals[3]
        entry["role"] = vals[4]
        groups[-1]["entries"].append(entry)
    return groups


def keyed(idx: int, keys: tuple[str, ...], skip: int = 1) -> list[dict]:
    out = []
    for r in rows(table_at(idx), skip=skip):
        vals = [v.strip() for v in r] + [""] * len(keys)
        if not nonempty(vals):
            continue
        out.append({k: v for k, v in zip(keys, vals) if v})
    return out


def teaching() -> dict:
    subs = dict(subsections(B, 45, 119))
    return {
        "statement": plain(para_after(subs["a"])),
        "courses_ubc": course_table(52),
        "course_descriptions": descriptions(53, 72),
        "graduate_research_supervision": supervision(74),
        "graduate_program_supervision": supervision(78),
        "continuing_education": {
            "developed_and_presented": keyed(
                84, ("title", "host", "role", "date", "hours")
            ),
            "attended": keyed(88, ("title", "host", "date", "hours")),
        },
        "visiting_lecturer": keyed(93, ("university", "course", "topic", "date", "hours")),
        "other": {
            "directed_studies": keyed(103, ("session", "course", "topic", "credits")),
            "work_learn": keyed(107, ("student", "program", "start", "end")),
        },
        "courses_prior_to_ubc": course_table(111),
        "course_descriptions_prior_to_ubc": descriptions(112, 119),
    }


# --------------------------------------------------------------------------
# 9  Scholarly and professional activities (minus presentations -> bib)
# --------------------------------------------------------------------------
FUND_KEYS = ("agency", "subject", "comp", "amount", "year", "pi", "coi")


def funding(idx: int) -> list[dict]:
    out = []
    for r in rows(table_at(idx), skip=1):
        vals = [v.strip() for v in r] + [""] * 7
        if not nonempty(vals):
            continue
        entry = {k: v for k, v in zip(FUND_KEYS, vals) if v}
        for key in ("pi", "coi"):
            if key in entry:
                entry[key] = [p.strip() for p in entry[key].split(" \\ ") if p.strip()]
        out.append(entry)
    return out


def research() -> dict:
    subs = dict(subsections(B, 119, 326))
    return {
        "statement": plain(para_after(subs["a"])),
        "grants": funding(127),
        "contracts": funding(131),
        "other": texts(subs["f"] + 1, subs["g"]),
        "conference_participation": texts(subs["g"] + 1, 326),
    }


# --------------------------------------------------------------------------
# 10-11  Service
# --------------------------------------------------------------------------
def service() -> dict:
    uni = dict(subsections(B, 329, 372))
    com = dict(subsections(B, 372, 451))
    return {
        "preamble_statement": "",
        "university": {
            "statement": plain(para_after(uni["a"])),
            "inclusion": texts(uni["b"] + 1, uni["c"]),
            "committees": texts(uni["c"] + 1, uni["d"]),
            "other": texts(uni["d"] + 1, 372),
        },
        "community": {
            "inclusion": texts(com["a"] + 1, com["b"]),
            "scholarly_societies": texts(com["b"] + 1, com["c"]),
            "other_societies": texts(com["c"] + 1, com["d"]),
            "scholarly_committees": texts(com["d"] + 1, com["e"]),
            "other_committees": texts(com["e"] + 1, com["f"]),
            "editorships": texts(com["f"] + 1, com["g"]),
            "reviewer": keyed(416, ("role", "venue", "date")),
            "external_examiner": texts(com["h"] + 1, com["i"]),
            "consultant": texts(com["i"] + 1, com["j"]),
            "other": texts(com["j"] + 1, com["k"]),
            "popular_media": keyed(443, ("role", "description", "date")),
        },
    }


# --------------------------------------------------------------------------
# 12-13  Awards, other information
# --------------------------------------------------------------------------
AWARD_KEYS = ("name", "organization", "dates", "details")


def awards() -> dict:
    subs = dict(subsections(B, 451, 479))
    return {
        "teaching": keyed(455, AWARD_KEYS),
        "scholarship_note": plain(md(B[461]["runs"])),
        "scholarship": keyed(463, AWARD_KEYS),
        "hqp_note": plain(md(B[465]["runs"])),
        "hqp": keyed(467, ("hqp",) + AWARD_KEYS),
        "service": texts(subs["c"] + 1, subs["d"]),
        "other": texts(subs["d"] + 1, 479),
    }


def other_information() -> dict:
    """Section 13.

    In the Word original the 'THE UNIVERSITY OF BRITISH COLUMBIA' banner that
    opens the Publications Record is glued onto the end of the last paragraph
    here, as a bold+underlined run. The template regenerates that banner, so
    strip any such run rather than carrying it into the prose.
    """
    paragraphs = []
    for i in range(480, 490):
        if B[i]["type"] != "p":
            continue
        runs = [
            r
            for r in B[i]["runs"]
            if not (r.get("bold") and r.get("underline"))
        ]
        text = md(runs)
        if text:
            paragraphs.append(text)
    return {"paragraphs": paragraphs}


if __name__ == "__main__":
    write("data/profile.yaml", profile())
    write("data/teaching.yaml", teaching())
    write("data/research.yaml", research())
    write("data/service.yaml", service())
    write("data/awards.yaml", awards())
    write("data/other.yaml", other_information())
