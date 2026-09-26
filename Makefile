PYTHON ?= python3
DOCX   ?= ubccv_gparadis-nohighlighting.docx
BUILD  ?= build

.PHONY: all pdf tex check clean bootstrap blocks

all: pdf

## Render data/ -> build/ubccv.pdf
pdf:
	$(PYTHON) src/render.py -o $(BUILD)/ubccv.pdf

## Render the intermediate LaTeX only (useful when debugging the template)
tex:
	$(PYTHON) src/render.py --tex-only

## Verify that data/ still accounts for everything in the original Word file
check: $(BUILD)/cv_blocks.json
	$(PYTHON) tools/qa_coverage.py

blocks: $(BUILD)/cv_blocks.json

$(BUILD)/cv_blocks.json: $(DOCX) tools/docx_dump.py
	@mkdir -p $(BUILD)
	$(PYTHON) tools/docx_dump.py $(DOCX) $@

## One-time re-import from the Word original. Overwrites data/ -- do not run
## this after you have started editing the YAML and BibTeX by hand.
bootstrap: $(BUILD)/cv_blocks.json
	$(PYTHON) tools/docx_to_yaml.py
	$(PYTHON) tools/docx_to_bib.py

clean:
	rm -rf $(BUILD)/ubccv.pdf $(BUILD)/ubccv.tex $(BUILD)/*.log $(BUILD)/*.aux
