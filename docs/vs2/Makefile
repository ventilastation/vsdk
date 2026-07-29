# Build the VS2 documentation.
#
#   python3 -m venv .venv
#   .venv/bin/pip install -r requirements.txt
#   make html          (or: make SPHINXBUILD=../../.venv/bin/sphinx-build html)
#
# Read the Docs uses ../../.readthedocs.yaml instead and ignores this file.

SPHINXOPTS    ?= -W --keep-going
SPHINXBUILD   ?= sphinx-build
SOURCEDIR      = .
BUILDDIR       = _build

.PHONY: help html linkcheck clean

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)

html:
	@$(SPHINXBUILD) -b html "$(SOURCEDIR)" "$(BUILDDIR)/html" $(SPHINXOPTS)
	@echo "Open $(BUILDDIR)/html/index.html"

linkcheck:
	@$(SPHINXBUILD) -b linkcheck "$(SOURCEDIR)" "$(BUILDDIR)/linkcheck" $(SPHINXOPTS)

clean:
	rm -rf "$(BUILDDIR)"
