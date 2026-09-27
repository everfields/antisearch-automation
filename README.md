# antisearch-automation

Mill for antisearch.ai organic clips + publish (synthetic-oracle). Not the product repo.

A queue row goes in and a 9:16 video of about 5–8s + one metadata row come out.
The clip recreates the antisearch.ai screen as a cold monolith: a blinking
cursor, a bare phrase typed in (`thing`, `dry shampoo`), a still pause while
the oracle thinks (the typed input and the caret, nothing added), then **one
lowercase verdict** fetched live from
`POST https://antisearch.ai/verdict {"category": "thing"}`.
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
make test           # unit + ffmpeg tests, no network, no tokens (live-oracle test opt-in: MILL_TEST_NETWORK=1)
make dry-run        # proof: fresh out-dry-run/, live oracle, publish dry-run, verify, contact sheets
make dry-run-offline  # same with the fixture oracle (no network)
make doctor         # tools, font, live oracle ping, which credentials are missing
```

Credentials: see **[SETUP.md](SETUP.md)**, a single checklist of everything to
add before `--live`. Nothing blocks without them.

## Own publisher (`mill post`)

One adapter per network behind `post(media, caption) -> url`
(`src/antisearch_mill/publisher/`). Dry-run unless `--live`.
- **Routes:** native (each network's official API) everywhere by default: Bluesky,
  Instagram Reels, LinkedIn Page, TikTok. `PUBLISHER_BRIDGE=buffer` is a removable
  bridge through Buffer free while a native gate is pending. Threads, Reddit and
  Mastodon are built too.
- **Cadence:** per-network slots in America/New_York on fixed :07 minutes, ≥90 min
  apart. The day starts 09:00 ET; ≤5 per network per day, one per run.
  `PUBLISHER_CADENCE=carlos|soul|reach` switches presets.
- **Fill:** queue rows first, then (optional) one trend row per network per day, then
  `queue/pools/`; unowned words open each wall and come back one in four.
- **Lanes:** `mill winners` (inputs likely to crown an entity; the only text is its
  human-verified @handle, ≤2 a day), `mill trends` (a timely noun input from free
  sources, strictly filtered)
  and `mill replies` (Bluesky, a verdict-only answer to "what's the … X?", ≤3 a
  day). See `docs/TREND_AND_REPLY_LANES.md`.
- **Guard:** one clip → one network; an input never repeats; inputs English and never
  serial; caption = empty / bare input / @handle
  (Bluesky: empty or a verified domain handle); live only for networks in
  `PUBLISHER_LIVE_NETWORKS`.
- **One honest run:** only `--live` asks the real oracle, once per input; the verdict
  is frozen in `verdicts.csv` next to the post log. Dry-runs never call it.
- **Post log:** a `pending` row is written before every API call, so nothing
  double-posts.
- **Scheduling:** `.github/workflows/publisher.yml` (manual + cron, off by default)
  runs it without the Grok Bot box.

```bash
mill networks                        # routes, slots (ET + Madrid), credentials, pool runway
mill due                             # exit 0 if a live network has a slot open now (cron pre-check)
mill post --queue queue/bluesky_trial.csv --queue queue/tiktok_trial.csv   # dry-run plans, no oracle call
mill post --queue queue/bluesky_trial.csv --live --state state/posts.csv
```

Setup, exact env vars and the honest limits per network:
**[docs/PUBLISHER_SETUP.md](docs/PUBLISHER_SETUP.md)**. `mill publish` (below) is
the older X/LinkedIn path and stays as it was.

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
| `mill oracle "dry shampoo"` | one verdict, as JSON |

Global: `--out DIR` (default `$MILL_OUT_DIR` or `out/`), `--env-file .env`.

## Queue

`queue/sample_queue.csv`:

| column | |
| --- | --- |
| `id` | stable job id, `[a-z0-9_-]`, unique. Produce skips ids that already have a clip |
| `category` | the bare phrase that gets "typed" and POSTed as-is; lowercased, ≤55 chars (the product's input `maxlength`). See [Input shape](#input-shape) |
| `platforms` | `x\|linkedin\|tiktok\|instagram` (empty = all) |
| `caption` | optional post text (GTM). Empty = video-only post |
| `notes` | free text, ignored |

## Input shape

"best" is the oracle's hidden premise, never the user's input. The user types
only the thing and the oracle returns the single best value for it:
`thing` → `love`. The clip, the queue and the POST body carry the bare phrase;
nothing in the pipeline prepends, appends or templates "best" into it.

The `category` field/column name is historical; its value is any bare input.

- Never starts with "best ", "the best ", "top ", "#1 ", "greatest ".
- Never a question ("what is the best…", trailing "?").
- Never an ask ("recommend…", "give me…", "find me…").
- Never a ranking ("top 3…", "…ranked").
- ≤ 55 characters. Constraints are fine as plain phrases: `restaurant in barcelona`, `gift for a new mom`.

Correct: `thing` · `dry shampoo` · `restaurant in barcelona` · `pizza` · `federico valverde` ·
`running shoes` · `emotion` · `gift for a new mom`

Wrong: ~~best running shoes~~ · ~~best dry shampoo~~ · ~~best software~~ ·
~~best country for having fun~~ · ~~what is the best espresso machine?~~

`tests/test_input_shape.py` enforces this on every queue row, every fixture key,
and every code-formatted example in README/SETUP.

## Clip contract

- 1080×1920 (9:16), 30 fps, H.264 High yuv420p + silent AAC stereo track, `+faststart`
- about 5–8s. The old ≤4s cap is lifted (founder, 2026-09-25). LinkedIn and Reels still reject clips under 3s; the visible wait is why these run longer
- the product CSS evaluated on a 360×640 CSS-px phone at 3×: `#0A0A0A` background, `#E8E4D8` text,
  18px→54px sans (Inter), centered at 38% height, `0.6ch × 1.05em` block cursor blinking at 1.05s,
  dim `antisearch.ai` footer
- the blink phase restarts on every keystroke and when the pause begins
- timeline: 0.3s idle cursor → jittered typing (≤1.5s, seeded by category, so deterministic) →
  0.22s hold of the completed input → a still pause (the typed input and a blinking caret only;
  no spinner, no dots, no "thinking" text, even if antisearch.ai shows one) → verdict holds to
  the end (≥1s). Short clips are padded on the verdict hold so the total is at least 5s. The
  pause length is the oracle call's wall-clock latency, clamped to 1.2–3.5s. If that latency
  was not recorded, the pause is 2.0s
- the pause does not copy the site's loading chrome. The site fetched 2026-09-25 hides the
  typed line on submit. The `word` clip keeps the input anyway. A later spinner, dots, or status
  word on the site is not drawn
- `PUBLISHER_CLIP_STYLE=app` withdraws that word-stays lock (2026-09-26, Soul + Carlos) and
  records the live screen: keyboard in, human typing, the finished word held ≥0.5s, Enter
  clears the word and slides the keyboard out while the line moves once to 38% of the full
  height, the caret blinks alone for the real oracle latency, the verdict holds ≥1.5s.
  Target ≤4s, hard cap 5s; a long latency is not cut. Unset or `word` is the default above
  and is what already-scheduled posts keep using
- `PUBLISHER_CLIP_AUDIO=off` (default) keeps the silent AAC track. `pulse` muxes a
  procedural felt-piano bed into Instagram and TikTok only: the same C3 note on
  each caret blink during the real pause, dry, no pedal, short room. The tail is
  silent before the clip ends. `PUBLISHER_CLIP_AUDIO_VARIANT` defaults to `c`
  (blinks, then silence). `a` resolves to an open fifth with octave one register
  below, `b` to the same note an octave lower. X, LinkedIn, and Bluesky stay silent
- the template (founder, 2026-09-26). Deterministic code only: no model at render time, no
  licensed audio or samples. Every flag defaults off, so scheduled posts do not change:
  - `PUBLISHER_CLIP_FRAME=phone` plays the `app` screen inside a generic phone drawn in code
    (thin bezels, rounded corners, a centered punch-hole camera, side buttons; no logo, no
    notch, no status bar, no captions). `PUBLISHER_CLIP_PHONE_SCALE` is the phone height over
    the video height (default `0.80`, allowed 0.60–0.95). `PUBLISHER_CLIP_PHONE_BG` is a calm
    surface lighter than the phone, so it reads at a glance: `stone` (mid warm grey, default),
    `bone` (off-white), or `sage` (muted grey-green). `black` and `gradient` (very dark grey)
    are kept but the phone disappears on them. The phone is a near-black slab with a graphite
    rim and a black bezel; the app screen is unchanged. `none` is the default
  - `PUBLISHER_CLIP_AUDIO=heartbeat` (Instagram and TikTok only): a synthesized mechanical key
    click on the frame each letter appears, a heavier Enter, then a low lub-dub on every caret
    blink of the wait. The verdict is silence (variant `c`, locked). Seeded from the input, so
    the same input gives the same audio. Sample peak -3 dBFS, true peak under -1 dBTP.
    `PUBLISHER_CLIP_AUDIO_BED=on` adds a very quiet low drone (about 20 LU under the beat)
    under the wait only; `off` is the default
  - `PUBLISHER_CLIP_AUDIO=keys` (Instagram and TikTok only; founder, second pass): the only
    sound is typing and Enter. A soft laptop chiclet key per letter, on the frame it appears,
    about -22.5 dBFS peak per key (±0.8 dB), Enter about -20.8 dBFS, low-passed so there is
    almost nothing above 6 kHz. Exact silence from the first wait frame through the verdict.
    `PUBLISHER_CLIP_KEYS_SOUND` is `soft` (default, a little plastic presence around 1 kHz) or
    `muted` (a duller thock). `heartbeat` and `pulse` are kept for back-compat
  - with the phone frame, the keys, or the heartbeat, the wait is fixed: `WAIT_BLINKS = 2` caret blinks
    of 1.05s (blink, blink, verdict), 63 frames (2.1s) at 30 fps, in every clip. It overrides the
    oracle latency. Only the typing and the verdict can vary with length. Segment frames are
    in the clip's sidecar JSON (`timeline.segments_frames`)
- verdict is lowercased and whitespace-collapsed; wraps like the product if long
- the verdict frame is the cover
- renders are byte-identical for the same (category, verdict, pause, style, audio, frame)
- mp4 metadata: `title=<verdict>`, `comment=capture=synthetic-oracle;oracle=<live|fixture>;category=<...>`

X gets a 720×1280 derivative at publish time (X's documented portrait max is
1200×1900); LinkedIn, TikTok and Instagram get the 1080×1920 master. The own
publisher (`mill post`) runs an X format A/B (`PUBLISHER_X_FORMAT=alternate|video|text`,
default `alternate`): the silent phone-frame master, or plain text with the lowercase
input on line 1 and the lowercase verdict on line 2, one per post, two posts a day.

### Metadata row (`out/clips.csv`)

`clip_id, job_id, category, verdict, capture, oracle_source, oracle_url,
oracle_latency_ms, oracle_fetched_at, produced_at, clip_path, poster_path,
duration_s, width, height, fps, size_bytes, sha256, font, render_style,
mill_version, platforms, caption`

`clip_id = <job_id>-<sha8(category, verdict, oracle_source, render_style, pause)>`.
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
  timeline.py    pure frame timeline (typing → pause → verdict)
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
