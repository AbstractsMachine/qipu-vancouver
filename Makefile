# Every package has its own Makefile with the same targets. These run them in each package that has one.
PACKAGES := records updates map-pipeline viewer
TARGETS := install check test e2e demo build clean

.PHONY: $(TARGETS) help

help:
	@echo "make <target> runs it in every package: $(TARGETS)"
	@echo "make -C packages/<name> <target> runs it in one: $(PACKAGES)"

$(TARGETS):
	@set -e; for p in $(PACKAGES); do \
	  if [ -f packages/$$p/Makefile ] && $(MAKE) -C packages/$$p -n $@ >/dev/null 2>&1; then \
	    echo "== packages/$$p: make $@"; $(MAKE) -C packages/$$p $@; \
	  fi; \
	done
