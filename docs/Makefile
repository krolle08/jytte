SPHINXOPTS    ?= -W --keep-going
SPHINXBUILD   ?= .venv/Scripts/sphinx-build
AUTOBUILD     ?= .venv/Scripts/sphinx-autobuild
SOURCEDIR     = source
BUILDDIR      = build

.PHONY: help html watch linkcheck clean

help:
	@$(SPHINXBUILD) --help

html:
	@$(SPHINXBUILD) -b html $(SOURCEDIR) $(BUILDDIR)/html $(SPHINXOPTS) $(O)
	@echo "Build finished. Open build/html/index.html"

watch:
	@echo "Starting sphinx-autobuild on http://localhost:8000"
	@$(AUTOBUILD) -a $(SOURCEDIR) $(BUILDDIR)/html

linkcheck:
	@$(SPHINXBUILD) -b linkcheck $(SOURCEDIR) $(BUILDDIR)/linkcheck $(SPHINXOPTS) $(O)

clean:
	rm -rf $(BUILDDIR)
