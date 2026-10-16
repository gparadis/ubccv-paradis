# UBC CV — Gregory E. Paradis

**Current CV:** [PDF](cv.pdf) · [Markdown](cv.md)

A data-driven pipeline for maintaining an academic CV in the format prescribed
by the *Guide to Reappointment, Promotion and Tenure Procedures at UBC*
(Appendix 3, "Annotated CV for the Professoriate Stream").

You edit structured data. The pipeline produces the PDF.

```
data/*.yaml  +  data/publications.bib
        |
        v
  src/render.py  ->  Jinja2  ->  LaTeX  ->  tectonic
        |
        v
  build/ubccv.pdf
```

## Usage

```sh
make          # render build/ubccv.pdf
make tex      # render build/ubccv.tex only, to debug the template
make check    # verify data/ still accounts for everything in the Word original
make publish  # refresh the committed cv.pdf and cv.md
```

## Where things live

| Path | What it is |
| --- | --- |
| `data/profile.yaml` | Sections 1–7: identity, education, employment, leaves |
| `data/teaching.yaml` | Section 8: courses, supervision, continuing education |
| `data/research.yaml` | Section 9: statement, grants, contracts, conference participation |
| `data/service.yaml` | Sections 10–11: service to the university and the community |
| `data/awards.yaml` | Section 12: awards and distinctions |
| `data/other.yaml` | Section 13: other relevant information |
| `data/publications.bib` | The Publications Record, plus invited and other presentations |
| `src/templates/cv.tex.j2` | The UBC layout |
| `src/cvdata.py` | Loads the sources, formats references |
| `src/latexfmt.py` | Inline markup and author-list formatting |
| `src/render_md.py` | Renders the same CV as one Markdown file (`make publish`) |
| `tools/` | One-time importers from the original `.docx`, plus the QA check |
| `reference/` | The legacy Word CV, the SAC Guide, and notes on how the import was interpreted |
| `cv.pdf`, `cv.md` | The current CV, committed so GitHub can render it; refresh with `make publish` |

## Editing conventions

**Text fields** accept a small amount of inline markup, which the renderer
turns into LaTeX:

| Markup | Result |
| --- | --- |
| `**text**` | bold |
| `*text*` | italic |
| `[label](url)` | hyperlink |
| `^{x}` | superscript |
| ` \ ` (inside a table cell) | line break |

Everything else is escaped, so `&`, `%`, `$` and `_` are safe to type literally.

**Publications and presentations** live in `data/publications.bib`. Beyond the
standard BibTeX fields, these are used:

| Field | Meaning |
| --- | --- |
| `ubccv` | Which CV subsection the entry belongs in (see below) |
| `hqp` | Co-authors who are your highly qualified personnel |
| `presenter` | The presenting author(s), for entries under Other Presentations |
| `venue`, `role`, `scope`, `date` | Presentation details (`scope` is local/national/international) |
| `authorrole` | e.g. `editor`, for edited books |
| `starred` | `yes` marks a publication of primary importance; adds the `*` the guide asks for, and the symbol key appears only when at least one entry is starred |

Emphasis is **not** stored. A name is rendered bold when it is yours or appears
in `hqp`; `hqp` names get a `^` and `presenter` names get a `*`. This keeps the
symbol key honest automatically.

Valid `ubccv` values:

```
invited_presentation      other_presentation
refereed_journal          refereed_proceedings      refereed_other
nonrefereed_journal       nonrefereed_proceedings   nonrefereed_other
book_authored             book_edited               book_chapter
patent                    copyright                 artistic       other_work
work_submitted            work_in_progress
```

**Ordering** is taken from the file, not computed. The guide asks for reverse
chronological order, but ties and "in press" entries need judgement, so entries
appear in the order you write them. The numbering in the PDF counts down, as in
the original document, so the newest item carries the highest number.

**Empty sections are kept.** The guide requires every heading to appear even
when there is nothing under it; those render as *(none to report)*.

## Adding a publication

Append to `data/publications.bib`, at the top of its section:

```bibtex
@article{surname2026keyword,
  author     = {Paradis, G. and Student, A.},
  title      = {A title, sentence case},
  year       = {2026},
  journal    = {Journal Name},
  volume     = {12},
  number     = {3},
  pages      = {101--119},
  doi        = {10.1000/example},
  hqp        = {Student, A.},
  ubccv      = {refereed_journal},
}
```

## Re-importing from Word

`make bootstrap` re-runs the importers and **overwrites `data/`**. It exists to
document how the original document was interpreted (the Word file itself now
lives in `reference/`); once you are editing the YAML and BibTeX by hand, do
not run it.

`make check` is the useful one: it re-reads the original `.docx` and confirms
that every word, number and name in it is still accounted for somewhere in
`data/`. See `reference/EXTRACTION-NOTES.md` for the handful of expected
differences.

## Requirements

`python3` with `pyyaml`, `jinja2` and `bibtexparser`, plus `tectonic` (or
`latexmk` with a TeX installation) to produce the PDF.
