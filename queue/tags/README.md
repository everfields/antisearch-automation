# Tag allowlist (Instagram and TikTok)

`allowlist.json` is the only source of tags. A post tags the verdict's official account
only if every rule below holds, otherwise it goes out untagged.

- **Who:** brands, products, and companies only (`"kind": "brand" | "product" | "company"`).
  Never a person, a private individual, or a minor. If you are unsure, don't add it.
- **Match:** the verdict equals the entry name or one of its `aliases` (lowercase).
- **Verified:** a human opened the account on that network, saw the verified badge, and
  set `verified: true`, `checked: YYYY-MM-DD`, `by: <who>`, and `evidence`. A check
  older than 30 days stops the tag until someone re-checks.
- **Networks:** `instagram` and `tiktok` only. X is never tagged.
- **Caption:** on TikTok the tag is the whole caption, `@handle`. On Instagram the caption
  is `#<input> #<verdict> #ai` and the tag rides last as its one `@mention` (Buffer
  cannot user-tag reels; its API has user tags on images only).
- **Instagram:** only a verified **US** brand account, marked `"market": "us"` on the
  entry's `instagram` block, and never the same handle within **14 days**.
- **Spam guard:** one tag per handle per network per 7 days, and at most half of a
  network's posts on a day are tagged.
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

People are never rows (LeBron James, Taylor Swift), whatever the verdict.
