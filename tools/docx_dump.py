#!/usr/bin/env python3
"""Dump a .docx into a faithful intermediate JSON block list.

Paragraphs become {"type": "p", "text": ..., "runs": [...], "style": ...}
Tables become {"type": "table", "rows": [[cell, ...], ...]} where each cell
carries both plain text and the run list, so bold/italic markers (used in this
CV to flag the candidate and HQP co-authors) survive the round trip.
"""

from __future__ import annotations

import json
import sys
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _rels(zf: zipfile.ZipFile) -> dict[str, str]:
    try:
        root = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
    except KeyError:
        return {}
    ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    return {r.get("Id"): r.get("Target") for r in root.findall(f"{ns}Relationship")}


def _footnotes(zf: zipfile.ZipFile) -> dict[str, str]:
    try:
        root = ET.fromstring(zf.read("word/footnotes.xml"))
    except KeyError:
        return {}
    out = {}
    for fn in root.findall(f"{W}footnote"):
        out[fn.get(f"{W}id")] = "".join(t.text or "" for t in fn.iter(f"{W}t"))
    return out


def _run(el: ET.Element) -> dict | None:
    props = el.find(f"{W}rPr")
    text = "".join(
        ("\n" if t.tag == f"{W}br" else "\t" if t.tag == f"{W}tab" else (t.text or ""))
        for t in el.iter()
        if t.tag in (f"{W}t", f"{W}br", f"{W}tab")
    )
    if not text:
        return None
    run: dict = {"text": text}
    if props is not None:
        for name, key in (("b", "bold"), ("i", "italic"), ("u", "underline")):
            node = props.find(f"{W}{name}")
            if node is not None and node.get(f"{W}val") not in ("false", "0", "none"):
                run[key] = True
        vert = props.find(f"{W}vertAlign")
        if vert is not None:
            run["vertAlign"] = vert.get(f"{W}val")
        high = props.find(f"{W}highlight")
        if high is not None:
            run["highlight"] = high.get(f"{W}val")
    return run


def _runs(parent: ET.Element, rels: dict, notes: dict) -> list[dict]:
    runs: list[dict] = []
    for child in parent:
        if child.tag == f"{W}r":
            ref = child.find(f"{W}footnoteReference")
            if ref is not None:
                fid = ref.get(f"{W}id")
                if notes.get(fid, "").strip():
                    runs.append({"text": notes[fid].strip(), "footnote": True})
            run = _run(child)
            if run:
                runs.append(run)
        elif child.tag == f"{W}hyperlink":
            target = rels.get(child.get(f"{R}id"), "")
            inner = _runs(child, rels, notes)
            for run in inner:
                if target:
                    run["href"] = target
            runs.extend(inner)
        elif child.tag in (f"{W}smartTag", f"{W}sdt", f"{W}sdtContent", f"{W}ins"):
            runs.extend(_runs(child, rels, notes))
    return runs


def _merge(runs: list[dict]) -> list[dict]:
    out: list[dict] = []
    for run in runs:
        keys = {k: v for k, v in run.items() if k != "text"}
        if out and {k: v for k, v in out[-1].items() if k != "text"} == keys:
            out[-1]["text"] += run["text"]
        else:
            out.append(dict(run))
    return [r for r in out if r["text"].strip() or "\n" in r["text"]]


def _para(el: ET.Element, rels: dict, notes: dict) -> dict:
    props = el.find(f"{W}pPr")
    style = None
    numbering = None
    if props is not None:
        node = props.find(f"{W}pStyle")
        if node is not None:
            style = node.get(f"{W}val")
        num = props.find(f"{W}numPr")
        if num is not None:
            ilvl = num.find(f"{W}ilvl")
            numid = num.find(f"{W}numId")
            numbering = {
                "ilvl": ilvl.get(f"{W}val") if ilvl is not None else None,
                "numId": numid.get(f"{W}val") if numid is not None else None,
            }
    runs = _merge(_runs(el, rels, notes))
    block = {"type": "p", "text": "".join(r["text"] for r in runs), "runs": runs}
    if style:
        block["style"] = style
    if numbering:
        block["num"] = numbering
    return block


def _table(el: ET.Element, rels: dict, notes: dict) -> dict:
    rows = []
    for tr in el.findall(f"{W}tr"):
        row = []
        for tc in tr.findall(f"{W}tc"):
            paras = [_para(p, rels, notes) for p in tc.findall(f"{W}p")]
            row.append(
                {
                    "text": "\n".join(p["text"] for p in paras).strip(),
                    "paras": [p for p in paras if p["runs"]],
                }
            )
        rows.append(row)
    return {"type": "table", "rows": rows}


def dump(path: str) -> list[dict]:
    with zipfile.ZipFile(path) as zf:
        rels, notes = _rels(zf), _footnotes(zf)
        body = ET.fromstring(zf.read("word/document.xml")).find(f"{W}body")
    blocks = []
    for child in body:
        if child.tag == f"{W}p":
            blocks.append(_para(child, rels, notes))
        elif child.tag == f"{W}tbl":
            blocks.append(_table(child, rels, notes))
    return blocks


if __name__ == "__main__":
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "-"
    blocks = dump(src)
    text = json.dumps(blocks, indent=1, ensure_ascii=False)
    if out == "-":
        sys.stdout.write(text)
    else:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"{len(blocks)} blocks -> {out}", file=sys.stderr)
