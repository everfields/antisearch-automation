# Reverse oracle

From a target account to the short inputs whose **real** verdict names it.

- `targets.csv` lists 89 big Instagram accounts across travel, hotels, restaurants,
  cruises, clubs, experiences, beauty and luxury. Each row has `aliases`, the verdicts
  that count as that account.
- `scripts/reverse_oracle.py` works in three steps:
  1. **Generator = the oracle run backwards.** It reads, and never edits or imports,
     the product's `prompts.py` (`PROMPTS[ACTIVE]`), `settings.py` and `oracle.py`
     (`--oracle-source <the_best>/app`). The deployed env overrides settings, as it does
     in the product (`OPENAI_MODEL`, `OPENAI_BASE_URL`, `REASONING_EFFORT`,
     `ORACLE_PROMPT_VERSION`). It then makes the product's exact call: the same model,
     the system prompt with today's date, `reasoning_effort` and `max_completion_tokens`,
     with the user message in the same `<<<QUERY … QUERY>>>` form. The only thing that
     differs is the query, a reverse question about the target's winner:
     `category topped by {winner}` and `what {winner} is the answer to`
     (`--template`, `--per-target`, cap `--generator-calls` 200). No other model is used.
     `candidates.json` records the model, prompt version and prompt sha256.
  2. Each proposed input is verified forward with **one** `LiveOracle` call, the
     publisher's oracle path. Calls stop at `--budget` (default 100). Inputs go in
     rounds: every target's first input, then the second for targets still unmatched.
  3. The verdict is matched against every target's aliases. `exact` means the verdict
     is the account; `prefix` means it is one of the account's products or properties.
- **Never asked twice:** an input already in `verdicts.csv` or in an earlier run's
  results is reused for free. Every live verdict is frozen. A used `--run-id` never
  runs again.
- **Input rules:** at most 3 words, bare English, and never the target's name or another
  brand's.
- **Output** goes to `publisher-state/reverse_oracle/<run>-{candidates.json,results.csv,matches.csv}`,
  ranked exact first, then fewer words, shorter, and larger account. `--check-sites`
  records whether the brand's own site links the handle.
- **Run it locally** with read access to the product's source and its model endpoint key
  in `OPENAI_API_KEY`. There is no workflow, because a runner can reach neither. Nothing
  is posted or scheduled.

**Run `2026-09-27-r1`** (superseded): its candidates were written by the Cursor agent
(`candidates-2026-09-27.json`), not the oracle. Its 100 verdicts are real and frozen,
and later runs reuse them for free.

**Run `2026-09-27-r2`** (the oracle backwards, `publisher-state` `e0ab3c1`):
- Generator: `gpt-6-astra`, prompt `v1.6.4` (sha256 `a88e28ed…`), `reasoning_effort` medium,
  `max_completion_tokens` 2048. 178 backwards calls gave 138 distinct inputs.
- Verification: 84 forward calls with no errors, plus 16 inputs already frozen; the
  candidates ran out before the budget of 100.
- Result: 56 matching inputs (45 exact) for 50 of 89 targets.
- Not a real match: `three-dimensional shape` → `sphere` (the shape, not @spherevegas).
