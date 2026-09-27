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
- **Caption:** the tag is the whole caption, `@handle`. Buffer cannot user-tag reels
  (its API has user tags on images only), so Instagram uses the caption too.
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

The seed is K18 on TikTok (`@k18hair`), confirmed on 2026-09-27 from TikTok's own
profile data (`verified: true`). Instagram has no entries yet.
