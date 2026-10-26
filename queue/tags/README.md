# Tag allowlist (Instagram, TikTok and X)

`allowlist.json` is the only source of tags. A post tags the verdict's official account
only if every rule below holds, otherwise it goes out untagged.

- **Who:** brands, products, and companies only (`"kind": "brand" | "product" | "company"`).
  Never a private individual or a minor. If you are unsure, don't add it. Exception (founder, 2026-10-26):
  mega public figures and groups for the TikTok celebrity lane (`kind: person` or `group`, `public_figure: true`,
  TikTok block only, verified official account checked twice with scripts/tiktok_profile.py and curl).
- **Match:** the verdict equals the entry name or one of its `aliases` (lowercase).
- **Verified:** set `verified` to match TikTok's badge on the profile page JSON. If the
  badge is false but the brand's own site (or Linktree) links the handle, set
  `verified: false` and add `official_evidence` with that URL. Always include
  `checked`, `by`, and `evidence`. A check older than 30 days stops the tag until
  someone re-checks.
- **Networks:** `instagram`, `tiktok` and `x`.
- **X** (founder, 2026-09-28): the entry's `x` block is the post's one mention, on its third
  line (`input`, `verdict`, `@handle`). It is used only when the account is the verdict itself,
  never the same account within 14 days, and with no half-of-the-day cap. Evidence for an `x`
  block: Wikidata `P2002` and/or the official site linking `x.com/<handle>`, plus the badge
  from the X profile data. Seeds (2026-09-28): `kagi` → `@KagiHQ`, `brave` → `@brave`,
  `instagram` → `@instagram`. `PUBLISHER_X_MENTIONS=off` stops X mentions (on by default);
  `PUBLISHER_TAG_NETWORKS` does not affect X.
- **Caption:** on TikTok the tag is the whole caption, `@handle`. On Instagram the caption
  is `#<input> #<verdict> #ai` and the tag rides last as its one `@mention` (Buffer
  cannot user-tag reels; its API has user tags on images only).
- **Instagram:** only a verified **US** brand account, marked `"market": "us"` on the
  entry's `instagram` block, or a brand's single worldwide account the founder picked,
  marked `"market": "global"`. Never the same handle within **14 days**.
- **Spam guard:** one tag per handle per network per 7 days, and at most half of a
  network's posts on a day are tagged. A scheduled post's tag counts on the day it goes out.
- **Concept mention reels** (`queue/manual/2026-09-28-ig-mentions.csv`): an entry is added
  only after a check on the day of scheduling shows the account is official, verified,
  and has posted in the last 7 days. On 2026-09-27: `hermès` → `@hermes` from web evidence;
  `new zealand` → `@purenewzealand`, `bora bora` → `@tahititourisme`, `santorini` →
  `@visitgreecegr` and `bali` → `@wonderfulindonesia` from a direct Instagram profile view
  by CoS (badge and latest post), with official links from web evidence. `@indtravel` is
  rejected: not verified, 3,020 followers.
- **Breaker:** `PUBLISHER_TAG_NETWORKS` (for example `tiktok` or `instagram,tiktok`).
  Empty, the default, means no tags anywhere.
- Never hashtags, collaborator invites, or hidden text.

Entry shape:

```json
"k18": {
  "kind": "brand",
  "aliases": ["k18 hair"],
  "tiktok": {"handle": "@k18hair", "verified": true, "checked": "2026-09-27", "by": "...", "evidence": "..."}
}
```

Seeds: K18 on TikTok (`@k18hair`) and Japan on Instagram (`@visitjapan.us`, JNTO
Americas), both confirmed on 2026-09-27 from the network's own public profile data.

Never amika or any Bansk brand: an entry naming amika, or with `"owner": "bansk"`, is
refused. Mark any other Bansk brand with that owner field.

**Pending Instagram rows** (the live verdict matched Soul's expected one on 2026-09-27;
`queue/ig_mentions.csv`), not added because Instagram's logged-out profile data was
unavailable that day (429 / server error) and a row needs a verified account with a post
in the last 7 days. Add each only after that check:

| verdict | handle | note |
| --- | --- | --- |
| aman new york | `@amannewyork` | |
| dyson airwrap co-anda2x | `@dysonhair` | Instagram returned "not found" for this handle; confirm Dyson's real hair account first |
| skinceuticals c e ferulic | `@skinceuticals` | |

People are never rows on Instagram or X, whatever the verdict. On TikTok only, a `person`/`group` row with
`public_figure: true` tags like a brand (celebrity lane, src/antisearch_mill/publisher/celeb.py). No athletes,
politicians or film/series accounts.

**Reverse-oracle candidates** (`candidates-2026-09-27.csv`): large Instagram lifestyle
accounts, each paired with a short input whose live verdict (one call each, frozen in
`verdicts.csv` on publisher-state) names that account. None of them is in the allowlist
yet. The verified badge and last-post date are still unconfirmed because Instagram blocked
logged-out checks. They are awaiting review with Soul and the founder. Superseded by the
programmatic run in `queue/reverse_oracle/` (run `2026-09-27-r1`), which includes them.

**TikTok brand guard** (2026-10-26, after `protector solar` → `la roche-posay anthelios uvmune 400 spf50+`
went out with no @ on 2026-10-25): a TikTok verdict with no allowlisted handle that looks like a
brand or product is skipped (`skipped_brand_untagged`) and the next pool input goes instead; it never
posts untagged. "Looks like a brand": names an allowlist brand with a TikTok block but no usable handle
(or with no network block at all), names a brand in `brands.txt` (brands seen as verdicts with no verified
handle yet), carries a model token (`spf50+`, `990v6`, `al13`), or is 3+ words with a product noun
(`serum`, `crema`, `champú`...). Heuristic and tests: `src/antisearch_mill/publisher/brand_guard.py`,
`tests/test_brand_guard.py`. To unblock a skipped input, add the brand's verified TikTok handle here.
`PUBLISHER_TIKTOK_BRAND_GUARD=off` is the breaker.

Added 2026-10-26 (each fetched twice, `scripts/tiktok_profile.py` and plain curl; verified badge, nickname
matches): `la roche-posay` @larocheposay, `aquaphor` @aquaphor, `armani beauty` @armanibeauty, `oribe` @oribe,
`chanel` @chanelofficial, `laneige` @laneige_us, `l'occitane` @loccitane, `dove advanced care` @dove,
`clarins` @clarinsusa. Not added (no verified, nickname-matching account found): medik8, lancôme, ghd, 3m,
bioderma (@biodermausa unverified), henson (@hensonshaving unverified), mason pearson (@masonpearson
unverified), latisse, sk-ii, st. tropez (@sttropeztan unverified), mountain valley, unsplash, roberta's.
