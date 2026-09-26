#!/usr/bin/env python3
"""Render the UBC CV from data/ to build/ubccv.pdf."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

import jinja2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cvdata import build_context  # noqa: E402
from latexfmt import cellpar, tex  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def environment() -> jinja2.Environment:
    """Jinja configured so that templates stay readable, valid-ish LaTeX."""
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(os.path.join(HERE, "templates")),
        variable_start_string=r"\VAR{",
        variable_end_string="}",
        block_start_string=r"\BLOCK{",
        block_end_string="}",
        # LaTeX's \newcommand bodies contain '{#1}', which would otherwise be
        # read as the start of a Jinja comment
        comment_start_string="((#",
        comment_end_string="#))",
        line_statement_prefix="%%",
        line_comment_prefix="%#",
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
        undefined=jinja2.ChainableUndefined,
    )


def names(value) -> str:
    """Render a PI/co-I cell, which may be a list of people."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return r" \newline ".join(tex(str(v)) for v in value)
    return cellpar(str(value))


def render_tex() -> str:
    env = environment()
    env.globals.update(t=lambda v: tex(str(v)) if v is not None else "", names=names)
    context = build_context()
    return env.get_template("cv.tex.j2").render(**context)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", default=os.path.join(ROOT, "build", "ubccv.pdf"))
    ap.add_argument("--tex-only", action="store_true", help="write the .tex and stop")
    args = ap.parse_args()

    build = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(build, exist_ok=True)
    tex_path = os.path.join(build, "ubccv.tex")
    with open(tex_path, "w", encoding="utf-8") as fh:
        fh.write(render_tex())
    print(f"wrote {tex_path}")
    if args.tex_only:
        return 0

    engine = shutil.which("tectonic")
    if engine:
        cmd = [engine, "-o", build, "--keep-logs", "--print", tex_path]
    elif shutil.which("latexmk"):
        cmd = ["latexmk", "-pdf", "-interaction=nonstopmode", f"-outdir={build}", tex_path]
    else:
        print("no LaTeX engine found (tectonic or latexmk)", file=sys.stderr)
        return 2

    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout[-4000:])
        sys.stderr.write(proc.stderr[-4000:])
        return proc.returncode
    produced = os.path.join(build, "ubccv.pdf")
    if produced != os.path.abspath(args.output):
        shutil.move(produced, args.output)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
