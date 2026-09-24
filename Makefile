PY      ?= python3
MILL    := PYTHONPATH=src $(PY) -m antisearch_mill
QUEUE   ?= queue/sample_queue.csv
ORACLE  ?= live
OUT     ?= out
PROOF   ?= out-dry-run

.PHONY: help install test produce publish publish-live status verify sheet doctor dry-run dry-run-offline clean

help:
	@echo "make install          pip install the mill + dev deps"
	@echo "make test             unit + e2e tests (no network, no tokens)"
	@echo "make produce          queue -> live oracle -> clips + out/clips.csv"
	@echo "make publish          dry-run publish of every produced clip (default, safe)"
	@echo "make publish-live     REAL publish to X/LinkedIn (needs SETUP.md credentials)"
	@echo "make dry-run          full proof: fresh $(PROOF)/, produce (live oracle) + publish dry-run + verify + sheets"
	@echo "make dry-run-offline  same proof with the fixture oracle (no network)"
	@echo "make doctor           tools / font / credential checklist"

install:
	$(PY) -m pip install -e '.[dev]'

test:
	PYTHONPATH=src $(PY) -m pytest -q

produce:
	$(MILL) --out $(OUT) produce --queue $(QUEUE) --oracle $(ORACLE)

publish:
	$(MILL) --out $(OUT) publish

publish-live:
	$(MILL) --out $(OUT) publish --live

status:
	$(MILL) --out $(OUT) status

verify:
	$(MILL) --out $(OUT) verify

sheet:
	$(MILL) --out $(OUT) sheet

doctor:
	$(MILL) doctor --network

dry-run:
	rm -rf $(PROOF)
	$(MILL) --out $(PROOF) produce --queue $(QUEUE) --oracle $(ORACLE)
	$(MILL) --out $(PROOF) publish
	$(MILL) --out $(PROOF) verify
	$(MILL) --out $(PROOF) sheet
	$(MILL) --out $(PROOF) status

dry-run-offline:
	$(MAKE) dry-run ORACLE=fixture PROOF=$(PROOF)-offline

clean:
	rm -rf $(OUT) $(PROOF) $(PROOF)-offline
