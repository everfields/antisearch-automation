# Reverse oracle

From a target account to the short inputs whose **real** verdict names it.

- `targets.csv` lists 89 big Instagram accounts across travel, hotels, restaurants,
  cruises, clubs, experiences, beauty and luxury. Each row has `aliases`, the verdicts
  that count as that account.
- `scripts/reverse_oracle.py` works in three steps:
  1. A generator proposes up to three inputs per target. The generator is any
     OpenAI-compatible model (secret `REVERSE_ORACLE_GENERATOR_KEY`, vars
     `REVERSE_ORACLE_GENERATOR_URL` / `REVERSE_ORACLE_MODEL`) or a candidates JSON file
     (`--candidates`). It gets the oracle's system prompt when one is given
     (`--oracle-prompt` or `ORACLE_SYSTEM_PROMPT`), plus the real input -> verdict pairs
     from `verdicts.csv`.
  2. Each input is verified with **one** `LiveOracle` call, the publisher's oracle path.
     Calls stop at `--budget` (default 100). Inputs go in rounds: every target's first
     input, then the second for targets still unmatched, and so on.
  3. The verdict is matched against every target's aliases. `exact` means the verdict
     is the account; `prefix` means it is one of the account's products or properties,
     e.g. `rosewood hong kong`.
- **Never asked twice:** an input already in `verdicts.csv` or in an earlier run's
  results is reused for free. Every live verdict is frozen (`--freeze matched` to freeze
  only the matches). A used `--run-id` never runs again.
- **Input rules:** at most 3 words, bare English, and never the target's name or another
  brand's.
- **Output** goes to `publisher-state/reverse_oracle/<run>-{candidates.json,results.csv,matches.csv}`.
  `matches.csv` is ranked exact first, then fewer words, shorter, and larger account.
  With `--check-sites`, it also records whether the brand's own site links the handle.
- Workflow: Actions -> reverse-oracle (dispatch only; dry-run unless `live`). Nothing is
  posted or scheduled.

**Run `2026-09-27-r1`:** 100 live calls, no errors. Candidates came from
`candidates-2026-09-27.json`: one batch for all 89 targets, written by the Cursor agent
from the same context the generator gets. GitHub Models, the planned generator, was
retired on 2026-07-30, and no other model key is configured. The oracle's system prompt
lives in `the_best` and is not readable here, so the context was the frozen examples only.
Result: 68 matching inputs (51 exact) for 55 of the 89 targets.
