# antisearch-automation

Mill for antisearch.ai organic clips + publish (synthetic-oracle). Not the product repo.

A queue row goes in and a ≤4s 9:16 video + one metadata row come out. The clip
recreates the antisearch.ai screen as a cold monolith: a blinking cursor, the
category typed in, the input vanishing on submit, then **one lowercase verdict**
fetched live from `POST https://antisearch.ai/verdict {"category": "..."}`.
Nothing else: no captions, no logos, no motion design. Captions are GTM's job
later (the queue's `caption` column).

Every row, log line and draft is tagged `capture=synthetic-oracle`. The pixels
are synthetic (ffmpeg, not a screen recording); the verdict is real.

```
queue/sample_queue.csv ──produce──▶ POST antisearch.ai/verdict ──▶ ffmpeg monolith
                                                                    │
            out/clips/<clip_id>.mp4 / .png / .json  ◀───────────────┘
            out/clips.csv  (metadata row per clip)
                          │
                       publish (dry-run default)
                          ├─ x         v2 media upload + POST /2/tweets
                          ├─ linkedin  Videos API + Posts API
                          ├─ tiktok    draft json only (stub)
                          └─ instagram draft json only (stub)
            out/publish.csv, out/dry_run/<platform>/*.json, out/drafts/<platform>/*.json
            out/logs/mill.jsonl
```

## Quick start

```bash
make install        # pip install -e '.[dev]'  (needs ffmpeg + a sans font, see SETUP.md)
make test           # 60 tests, no network, no tokens
make dry-run        # proof: fresh out-dry-run/, live oracle, publish dry-run, verify, contact sheets
make dry-run-offline  # same with the fixture oracle (no network)
make doctor         # tools, font, live oracle ping, which credentials are missing
```

Credentials: see **[SETUP.md](SETUP.md)**, a single checklist of everything to
add before `--live`. Nothing blocks without them.

## CLI

`mill` (or `PYTHONPATH=src python3 -m antisearch_mill`):

| command | what it does |
| --- | --- |
| `mill produce [--queue q.csv] [--oracle live\|fixture] [--limit N] [--only id] [--force]` | ask the oracle, render, validate, write metadata |
| `mill publish [--live] [--platform x] [--clip id]` | publish produced clips; **dry-run unless `--live`** |
| `mill status` | clips and the latest publish state per platform |
| `mill verify` | re-probe every clip against the contract (size, length, codec, sha256, tag) |
| `mill sheet` | contact-sheet PNGs into `out/proof/` |
| `mill doctor [--network]` | environment + credential check (never prints values) |
| `mill oracle "best chef knife"` | one verdict, as JSON |

Global: `--out DIR` (default `$MILL_OUT_DIR` or `out/`), `--env-file .env`.

## Queue

`queue/sample_queue.csv`:

| column | |
| --- | --- |
| `id` | stable job id, `[a-z0-9_-]`, unique. Produce skips ids that already have a clip |
| `category` | what gets "typed"; lowercased, ≤55 chars (the product's input `maxlength`) |
| `platforms` | `x\|linkedin\|tiktok\|instagram` (empty = all) |
| `caption` | optional post text (GTM). Empty = video-only post |
| `notes` | free text, ignored |

## Clip contract

- 1080×1920 (9:16), 30 fps, H.264 High yuv420p + silent AAC stereo track, `+faststart`
- 3.8s default, hard window 3.0–4.0s (LinkedIn and Reels reject clips under 3s; the constitution caps at 4s)
- the product CSS evaluated on a 360×640 CSS-px phone at 3×: `#0A0A0A` background, `#E8E4D8` text,
  18px→54px sans (Inter), centered at 38% height, `0.6ch × 1.05em` block cursor blinking at 1.05s,
  dim `antisearch.ai` footer
- the blink phase restarts on every keystroke and on submit (native caret behaviour), so the
  cursor never blinks out during typing or the lone-cursor submit beat of a ≤4s clip
- timeline: 0.3s idle cursor → jittered typing (≤1.5s, seeded by category, so deterministic) →
  0.22s hold → submit (input vanishes, lone cursor 0.45s) → verdict holds to the end (≥1s)
- verdict is lowercased and whitespace-collapsed; wraps like the product if long
- mp4 metadata: `title=<verdict>`, `comment=capture=synthetic-oracle;oracle=<live|fixture>;category=<...>`
- renders are byte-identical for the same (category, verdict)

X gets a 720×1280 derivative at publish time (X's documented portrait max is
1200×1900); LinkedIn, TikTok and Instagram get the 1080×1920 master.

### Metadata row (`out/clips.csv`)

`clip_id, job_id, category, verdict, capture, oracle_source, oracle_url,
oracle_latency_ms, oracle_fetched_at, produced_at, clip_path, poster_path,
duration_s, width, height, fps, size_bytes, sha256, font, render_style,
mill_version, platforms, caption`

`clip_id = <job_id>-<sha8(category, verdict, oracle_source, render_style)>`.
The oracle is not deterministic (the same category can return a different pick
on a later call), so the row freezes the verdict that was actually shown.

## Oracle

Retry policy mirrors the product frontend: one 20s budget, ≤2 attempts, retry
only on 5xx / network / timeout, never on 4xx. On 429 the mill waits
`Retry-After` (or 60s) once, then gives up on that job. Calls are spaced ≥1.5s.
A failed verdict fails that job only; it is logged (`oracle.failed`) and the run continues.

`--oracle fixture` (`fixtures/oracle_fixtures.json`) exists for tests and
no-network runs. Fixture verdicts are marked `oracle_source=fixture` and the
publisher **refuses to post them live**.

## Publish modes

| mode | x / linkedin | tiktok / instagram |
| --- | --- | --- |
| dry-run (default) | full upload flow runs against a simulated API; every request (auth redacted) is written to `out/dry_run/<platform>/<clip_id>.json`; `dry_run_ok` | draft json, `draft_logged` |
| `--live` | real API; needs credentials, else `skipped_missing_credentials`; idempotent per (clip, platform) | still draft json only |

Publish statuses: `dry_run_ok`, `published`, `draft_logged`,
`skipped_missing_credentials`, `skipped_not_live_oracle`,
`skipped_already_published`, `invalid_clip`, `failed`.

## Layout

```
src/antisearch_mill/
  oracle.py      live + fixture verdict oracles
  timeline.py    pure frame timeline (typing → loading → verdict)
  render.py      product-CSS layout → ffmpeg drawtext/drawbox graph, probe, poster, sheets
  fonts.py       font resolution + HarfBuzz-shaped metrics (Pillow/raqm)
  produce.py     queue → verdict → clip → metadata row
  ledger.py      queue CSV, clips.csv, publish.csv, mill.jsonl
  publish/       x.py, linkedin.py, stubs.py (tiktok, instagram), http.py (live/dry-run transport)
  cli.py
tests/           unit, ffmpeg render, sandboxed X/LinkedIn flows, CLI e2e
.github/workflows/ci.yml    tests + offline dry-run on every PR
.github/workflows/mill.yml  manual mill run (dry-run unless `live` ticked)
```
