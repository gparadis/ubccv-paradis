#!/usr/bin/env python3
"""Render the UBC CV from data/ to a browser-friendly Markdown file.

This mirrors src/templates/cv.tex.j2: same sections, same order, same wording,
same symbol conventions, so the two renderings can be compared side by side.
Only the layout differs, and only where Markdown cannot express LaTeX.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cvdata import by_section, is_starred, load_bib, load_yaml  # noqa: E402
from latexfmt import TOKEN_RE, display_name, split_names  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

MD_SPECIALS = {"_": r"\_", "`": r"\`", "|": r"\|"}
BR = "<br>"


def esc(text) -> str:
    return "".join(MD_SPECIALS.get(c, c) for c in str(text)).replace("--", "\u2013")


def flat(text) -> str:
    """Collapse real newlines (YAML block scalars) to single spaces."""
    return re.sub(r"\s+", " ", str(text)).strip()


def mdt(text) -> str:
    """Inline markup -> Markdown, mirroring latexfmt.tex()."""
    if text is None:
        return ""
    text = str(text)
    if not text:
        return ""
    if " \\ " in text:
        return BR.join(mdt(p.strip()) for p in text.split(" \\ ") if p.strip())
    out, pos = [], 0
    for m in TOKEN_RE.finditer(text):
        out.append(esc(text[pos : m.start()]))
        if m.group("bold"):
            out.append("**" + mdt(m.group("b")) + "**")
        elif m.group("italic"):
            out.append("*" + mdt(m.group("i")) + "*")
        elif m.group("link"):
            out.append("[" + esc(m.group("t")) + "](" + m.group("u") + ")")
        elif m.group("sup"):
            out.append("<sup>" + esc(m.group("s")) + "</sup>")
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out)


def cell(value) -> str:
    """A table cell / inline field: markup rendered, newlines flattened."""
    if value is None:
        return ""
    return mdt(flat(value))


def names_cell(value) -> str:
    """A PI/co-I cell, which may be a list of people."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return BR.join(mdt(flat(v)) for v in value)
    return cell(value)


# ---------------------------------------------------------------------------
# Reference rendering (mirrors cvdata.reference, in Markdown)
# ---------------------------------------------------------------------------
def _authors(e: dict, self_surname: str) -> str:
    hqp = set(split_names(e.get("hqp")))
    pres = set(split_names(e.get("presenter")))
    out = []
    for name in split_names(e.get("author")):
        shown = esc(display_name(name))
        if name in hqp or display_name(name).split(",")[0].strip() == self_surname:
            shown = "**" + shown + "**"
        if name in pres:
            shown += "<sup>*</sup>"
        if name in hqp:
            shown += "<sup>^</sup>"
        out.append(shown)
    if len(out) > 1:
        return ", ".join(out[:-1]) + " and " + out[-1]
    return out[0] if out else ""


def reference_md(e: dict, self_surname: str) -> str:
    bits = []
    authors = _authors(e, self_surname)
    if authors:
        role = f" ({e['authorrole']})" if e.get("authorrole") else ""
        year = f" ({e['year']})." if e.get("year") else ""
        bits.append(authors + role + year)
    elif e.get("year"):
        bits.append(f"({e['year']}).")
    if e.get("title"):
        bits.append("*" + mdt(e["title"]) + "*.")

    venue = e.get("journal") or e.get("booktitle") or e.get("venue")
    if venue:
        chunk = mdt(venue)
        if e.get("volume"):
            chunk += f", {esc(e['volume'])}"
            if e.get("number"):
                chunk += f"({esc(e['number'])})"
        if e.get("pages"):
            chunk += f", {esc(e['pages'])}"
        bits.append(chunk + ".")
    if e.get("role"):
        bits.append(mdt(e["role"]) + ".")
    if e.get("date"):
        bits.append(esc(e["date"]) + ".")
    if e.get("note"):
        bits.append("(" + mdt(e["note"]) + ")")

    text = " ".join(b for b in bits if b)
    if e.get("doi"):
        text += f" DOI [{esc(e['doi'])}](https://doi.org/{e['doi']})."
    elif e.get("url") and e["url"] != (e.get("journal") or e.get("booktitle") or e.get("venue")):
        text += f" {e['url']}"
    if e.get("scope"):
        text += f" [{esc(e['scope'])}]"
    text = re.sub(r"\s+", " ", text).replace(" .", ".").strip()
    if is_starred(e):
        text = r"\*" + text
    return text


# ---------------------------------------------------------------------------
# Block helpers
# ---------------------------------------------------------------------------
def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    if not rows:
        return ["*(none to report)*"]
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    out.extend("| " + " | ".join(r) + " |" for r in rows)
    return out


def bullets(items) -> list[str]:
    if not items:
        return ["*(none to report)*"]
    return [f"- {cell(i)}" for i in items]


def reflist(items: list[str]) -> list[str]:
    """Descending-numbered reference list (the number is literal text, so
    Markdown does not renumber it)."""
    if not items:
        return ["*(none to report)*"]
    out, n = [], len(items)
    for r in items:
        out.append(f"{n}\\. {r}")
        n -= 1
    return out


def coursenotes(items) -> list[str]:
    out = []
    for c in items:
        head = f"**{cell(c.get('code'))}**"
        if c.get("credits"):
            head += f" ({cell(c['credits'])} credits)"
        head += f" *{cell(c.get('title'))}*"
        if c.get("institution"):
            head += f" [{cell(c['institution'])}]"
        desc = cell(c.get("description"))
        if c.get("contact_pattern"):
            desc += f" [{cell(c['contact_pattern'])}]"
        out.append(head + "  ")
        out.append(desc)
        out.append("")
    return out


def courses_table(groups) -> list[str]:
    headers = ["Session", "Course", "Sched. hrs", "Class size", "Lect.", "Tut.", "Labs", "Other"]
    rows = []
    for g in groups or []:
        rows.append([f"**{cell(g.get('group'))}**"] + [""] * 7)
        if g.get("entries"):
            for c in g["entries"]:
                rows.append(
                    [
                        cell(c.get("session")),
                        cell(c.get("course")),
                        cell(c.get("scheduled_hours")),
                        cell(c.get("class_size")),
                        cell(c.get("lectures")),
                        cell(c.get("tutorials")),
                        cell(c.get("labs")),
                        cell(c.get("other")),
                    ]
                )
        else:
            rows.append(["*(no courses taught)*"] + [""] * 7)
    return table(headers, rows)


def supervision_table(groups) -> list[str]:
    headers = ["Student Name", "Program", "Start", "Finish", "Supervisory Role"]
    rows = []
    for g in groups or []:
        if g.get("group"):
            rows.append([f"**{cell(g['group'])}**"] + [""] * 4)
        for s in g.get("entries") or []:
            rows.append(
                [
                    cell(s.get("student")),
                    cell(s.get("program")),
                    cell(s.get("start")),
                    cell(s.get("finish")),
                    cell(s.get("role")),
                ]
            )
    return table(headers, rows)


def funding_table(items) -> list[str]:
    headers = ["Agency", "Subject", "COMP", "$ (total)", "Year", "Principal Investigator", "Co-Investigator(s)"]
    rows = [
        [
            cell(f.get("agency")),
            cell(f.get("subject")),
            cell(f.get("comp")),
            cell(f.get("amount")),
            cell(f.get("year")),
            names_cell(f.get("pi")),
            names_cell(f.get("coi")),
        ]
        for f in items or []
    ]
    return table(headers, rows)


def award_table(items) -> list[str]:
    headers = ["Name of Award", "Awarding Organization", "Dates", "Award Details"]
    rows = [
        [
            cell(a.get("name")),
            cell(a.get("organization")),
            cell(a.get("dates")),
            cell(a.get("details")),
        ]
        for a in items or []
    ]
    return table(headers, rows)


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------
def render_md() -> str:
    data = load_yaml()
    entries = load_bib()
    sections = by_section(entries)
    p = data["profile"]
    surname = p.get("surname", "Surname")
    refs = {name: [reference_md(e, surname) for e in items] for name, items in sections.items()}
    has_starred = any(is_starred(e) for e in entries)
    t, r, sv, aw, ot = (
        data["teaching"],
        data["research"],
        data["service"],
        data["awards"],
        data["other"],
    )
    emp = p.get("employment") or {}

    L: list[str] = []

    def add(*lines: str) -> None:
        L.extend(lines)

    # ------------------------------------------------------------------ CV
    add("# THE UNIVERSITY OF BRITISH COLUMBIA", "")
    add("**Curriculum Vitae for Faculty Members**", "")
    add(f"**Date**: {cell(p.get('date'))} · **Initials**: {cell(p.get('initials'))}", "")

    add("## 1. SURNAME", "")
    add(
        f"**SURNAME:** {cell(p.get('surname'))}  ",
        f"**FIRST NAME:** {cell(p.get('first_name'))}  ",
        f"**MIDDLE NAME(S):** {cell(p.get('middle_names'))}",
        "",
    )

    add("## 2. DEPARTMENT/SCHOOL", "")
    add(cell(p.get("department")), "")

    add("## 3. FACULTY", "")
    add(cell(p.get("faculty")), "")

    add("## 4. PRESENT RANK", "")
    add(f"{cell(p.get('present_rank'))} — **SINCE:** {cell(p.get('rank_since'))}", "")

    add("## 5. POST-SECONDARY EDUCATION", "")
    add(
        *table(
            ["University or Institution", "Degree", "Subject Area", "Dates"],
            [
                [cell(e.get("institution")), cell(e.get("degree")), cell(e.get("subject")), cell(e.get("dates"))]
                for e in p.get("education") or []
            ],
        )
    )
    add("", "### Special Professional Qualifications", "")
    add(*bullets(p.get("special_qualifications")), "")

    add("## 6. EMPLOYMENT RECORD", "")
    add("### (a) Prior to coming to UBC", "", "**University employment**", "")
    add(
        *table(
            ["University", "Rank or Title", "Dates"],
            [
                [cell(e.get("organization")), cell(e.get("title")), cell(e.get("dates"))]
                for e in emp.get("prior_university") or []
            ],
        )
    )
    add("", "**Non-university employment**", "")
    add(
        *table(
            ["Company or Organization", "Rank or Title", "Dates"],
            [
                [cell(e.get("organization")), cell(e.get("title")), cell(e.get("dates"))]
                for e in emp.get("prior_other") or []
            ],
        )
    )
    add("", "### (b) At UBC", "")
    add(
        *table(
            ["Rank or Title", "Dates"],
            [[cell(e.get("title")), cell(e.get("dates"))] for e in emp.get("at_ubc") or []],
        )
    )
    add("", "### (c) Date of granting of tenure at UBC", "")
    add(cell(emp.get("tenure_date")) or "*(not yet granted)*", "")

    add("## 7. LEAVES OF ABSENCE", "")
    add(
        *table(
            ["Organization", "Type of Leave", "Dates"],
            [
                [cell(e.get("organization")), cell(e.get("type")), cell(e.get("dates"))]
                for e in p.get("leaves_of_absence") or []
            ],
        ),
        "",
    )

    # ------------------------------------------------------------- teaching
    add("## 8. TEACHING", "")
    add("### (a) Areas of special interest and accomplishments", "")
    add(cell(t.get("statement")), "")
    add("### (b) Courses Taught at UBC (both undergraduate & graduate)", "")
    add(*courses_table(t.get("courses_ubc")), "")
    add(*coursenotes(t.get("course_descriptions") or []), "")
    add("### (c) Graduate Research Supervision", "")
    add(*supervision_table(t.get("graduate_research_supervision")), "")
    add("### (d) Graduate Program Supervision", "")
    add(*supervision_table(t.get("graduate_program_supervision")), "")
    add("### (e) Continuing Education Activities", "")
    ce = t.get("continuing_education") or {}
    add("**Workshop Development and Presentation**", "")
    add(
        *table(
            ["Workshop Title", "Host", "Role", "Date", "Hours"],
            [
                [cell(w.get("title")), cell(w.get("host")), cell(w.get("role")), cell(w.get("date")), cell(w.get("hours"))]
                for w in ce.get("developed_and_presented") or []
            ],
        )
    )
    add("", "**Workshop Attendance**", "")
    add(
        *table(
            ["Workshop Title", "Host", "Date", "Hours"],
            [
                [cell(w.get("title")), cell(w.get("host")), cell(w.get("date")), cell(w.get("hours"))]
                for w in ce.get("attended") or []
            ],
        )
    )
    add("", "### (f) Visiting and Guest Lecturer (indicate university/organization and dates)", "")
    add(
        *table(
            ["University", "Course", "Topic", "Date", "Hours"],
            [
                [cell(v.get("university")), cell(v.get("course")), cell(v.get("topic")), cell(v.get("date")), cell(v.get("hours"))]
                for v in t.get("visiting_lecturer") or []
            ],
        )
    )
    add("", "### (g) Other", "")
    oth = t.get("other") or {}
    add("**Directed Studies Student Supervision**", "")
    add(
        *table(
            ["Session", "Course", "Topic", "Credits"],
            [
                [cell(d.get("session")), cell(d.get("course")), cell(d.get("topic")), cell(d.get("credits"))]
                for d in oth.get("directed_studies") or []
            ],
        )
    )
    add("", "**Work Learn and Student Internship Supervision**", "")
    add(
        *table(
            ["Student Name", "Program Type", "Start Date", "End Date"],
            [
                [cell(w.get("student")), cell(w.get("program")), cell(w.get("start")), cell(w.get("end"))]
                for w in oth.get("work_learn") or []
            ],
        )
    )
    add("", "**Courses Taught Prior to UBC**", "")
    add(*courses_table(t.get("courses_prior_to_ubc")), "")
    add(*coursenotes(t.get("course_descriptions_prior_to_ubc") or []), "")

    # ------------------------------------------------------------- research
    add("## 9. SCHOLARLY AND PROFESSIONAL ACTIVITIES", "")
    add("### (a) Areas of special interest and accomplishments", "")
    add(cell(r.get("statement")), "")
    add(
        "### (b) Research or equivalent grants (indicate under COMP whether grants were obtained competitively (C) or non-competitively (NC))",
        "",
    )
    add(*funding_table(r.get("grants")), "")
    add(
        "### (c) Research or equivalent contracts (indicate under COMP whether contracts were obtained competitively (C) or non-competitively (NC))",
        "",
    )
    add(*funding_table(r.get("contracts")), "")
    add("### (d) Invited Presentations (Identify whether International/National/Local)", "")
    add(*reflist(refs.get("invited_presentation", [])), "")
    add("### (e) Other Presentations", "")
    add("Symbol key: `*` presenting author; `^` highly qualified personnel (HQP)", "")
    add(*reflist(refs.get("other_presentation", [])), "")
    add("### (f) Other", "")
    add(*bullets(r.get("other")), "")
    add("### (g) Conference Participation (Organizer, Keynote Speaker, etc.)", "")
    add(*bullets(r.get("conference_participation")), "")

    # -------------------------------------------------------------- service
    add("**SERVICE TO THE UNIVERSITY AND THE COMMUNITY**", "")
    add("## 10. SERVICE TO THE UNIVERSITY", "")
    uni = sv.get("university") or {}
    add("### (a) Areas of special interest and accomplishments", "")
    add(cell(uni.get("statement")), "")
    add(
        "### (b) Areas of service undertaken to advance the inclusion of all those who have been historically excluded based on gender, race, religion, sexuality, age, disability, or economic circumstance",
        "",
    )
    add(*bullets(uni.get("inclusion")), "")
    add("### (c) Memberships on committees, including offices held and dates", "")
    add(*bullets(uni.get("committees")), "")
    add("### (d) Other service, including dates", "")
    add(*bullets(uni.get("other")), "")

    add("## 11. SERVICE TO THE COMMUNITY", "")
    com = sv.get("community") or {}
    add("### (a) Service undertaken to advance the inclusion of all those who have been historically excluded based on gender, race, religion, sexuality, age, disability, or economic circumstance", "")
    add(*bullets(com.get("inclusion")), "")
    add("### (b) Memberships on scholarly societies, including offices held and dates", "")
    add(*bullets(com.get("scholarly_societies")), "")
    add("### (c) Memberships on other societies, including offices held and dates", "")
    add(*bullets(com.get("other_societies")), "")
    add("### (d) Memberships on scholarly committees, including offices held and dates", "")
    add(*bullets(com.get("scholarly_committees")), "")
    add("### (e) Memberships on other committees, including offices held and dates", "")
    add(*bullets(com.get("other_committees")), "")
    add("### (f) Editorships (list journal and dates)", "")
    add(*bullets(com.get("editorships")), "")
    add("### (g) Reviewer (journal, agency, etc. including dates)", "")
    add(
        *table(
            ["Role", "Journal or Organization", "Date"],
            [
                [cell(v.get("role")), cell(v.get("venue")), cell(v.get("date"))]
                for v in com.get("reviewer") or []
            ],
        )
    )
    add("", "### (h) External examiner (indicate universities and dates)", "")
    add(*bullets(com.get("external_examiner")), "")
    add("### (i) Consultant (indicate organization and dates)", "")
    add(*bullets(com.get("consultant")), "")
    add("### (j) Other service to the community", "")
    add(*bullets(com.get("other")), "")
    add("### (k) Popular Media", "")
    add(
        *table(
            ["Role", "Description", "Date"],
            [
                [cell(m.get("role")), cell(m.get("description")), cell(m.get("date"))]
                for m in com.get("popular_media") or []
            ],
        ),
        "",
    )

    # --------------------------------------------------------------- awards
    add("## 12. AWARDS AND DISTINCTIONS", "")
    add("### (a) Awards for Teaching (indicate name of award, awarding organizations, date)", "")
    add(*award_table(aw.get("teaching")), "")
    add("### (b) Awards for Scholarship (indicate name of award, awarding organizations, date)", "")
    if aw.get("scholarship_note"):
        add(cell(aw["scholarship_note"]), "")
    add(*award_table(aw.get("scholarship")), "")
    if aw.get("hqp_note"):
        add("", cell(aw["hqp_note"]), "")
    add(
        "",
        *table(
            ["HQP Name", "Name of Award", "Awarding Organization", "Dates", "Details"],
            [
                [
                    cell(a.get("hqp")),
                    cell(a.get("name")),
                    cell(a.get("organization")),
                    cell(a.get("dates")),
                    cell(a.get("details")),
                ]
                for a in aw.get("hqp") or []
            ],
        ),
    )
    add("", "### (c) Awards for Service (indicate name of award, awarding organizations, date)", "")
    add(*bullets(aw.get("service")), "")
    add("### (d) Other Awards", "")
    add(*bullets(aw.get("other")), "")

    # ---------------------------------------------------------------- other
    add("## 13. OTHER RELEVANT INFORMATION (Maximum One Page)", "")
    for para in ot.get("paragraphs") or []:
        add(cell(para), "")

    # -------------------------------------------------- Publications Record
    add("---", "")
    add("# THE UNIVERSITY OF BRITISH COLUMBIA", "")
    add("**Publications Record**", "")
    add(
        f"**SURNAME**: {cell(p.get('surname'))} · **FIRST NAME**: {cell(p.get('first_name'))} · **Initials**: {cell(p.get('initials'))}  ",
        f"**MIDDLE NAME(S)**: {cell(p.get('middle_names'))} · **Date**: {cell(p.get('date'))}",
        "",
    )
    key = "Symbol key: `^` highly qualified personnel (HQP)"
    if has_starred:
        key += "; `*` publication of primary importance"
    add(key + ".", "")

    add("## 1. REFEREED PUBLICATIONS", "")
    add("### (a) Journals", "")
    add(*reflist(refs.get("refereed_journal", [])), "")
    add("### (b) Conference Proceedings", "")
    add(*reflist(refs.get("refereed_proceedings", [])), "")
    add("### (c) Other", "")
    add(*reflist(refs.get("refereed_other", [])), "")

    add("## 2. NON-REFEREED PUBLICATIONS", "")
    add("### (a) Journals", "")
    add(*reflist(refs.get("nonrefereed_journal", [])), "")
    add("### (b) Conference Proceedings", "")
    add(*reflist(refs.get("nonrefereed_proceedings", [])), "")
    add("### (c) Other", "")
    add(*reflist(refs.get("nonrefereed_other", [])), "")

    add("## 3. BOOKS", "")
    add("### (a) Authored", "")
    add(*reflist(refs.get("book_authored", [])), "")
    add("### (b) Edited", "")
    add(*reflist(refs.get("book_edited", [])), "")
    add("### (c) Chapters", "")
    add(*reflist(refs.get("book_chapter", [])), "")

    add("## 4. PATENTS", "")
    add(*reflist(refs.get("patent", [])), "")
    add("## 5. SPECIAL COPYRIGHTS", "")
    add(*reflist(refs.get("copyright", [])), "")
    add("## 6. ARTISTIC WORKS, PERFORMANCES, DESIGNS", "")
    add(*reflist(refs.get("artistic", [])), "")
    add("## 7. OTHER WORKS", "")
    add(*reflist(refs.get("other_work", [])), "")
    add("## 8. WORK SUBMITTED (including publisher and date of submission)", "")
    add(*reflist(refs.get("work_submitted", [])), "")
    add("## 9. WORK IN PROGRESS (including degree of completion)", "")
    add(*reflist(refs.get("work_in_progress", [])), "")

    text = "\n".join(L)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", default=os.path.join(ROOT, "cv.md"))
    args = ap.parse_args()
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(render_md())
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
