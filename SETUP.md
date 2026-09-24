# SETUP: everything Carlos adds later

The mill runs end to end without any of this: `make test` and `make dry-run`
need zero credentials. This file is the **one bulk checklist** of what to add
before flipping `--live`. Put values in `.env` locally (copy `.env.example`),
and/or as GitHub Actions secrets (for `.github/workflows/mill.yml`), and/or as
Cursor Cloud Agent secrets. `mill doctor` shows what is present/missing
without printing values.

Since 2026-09-24 (evening), posting goes through our own publisher (`mill post`,
official APIs, no Buffer, no box browser). Its tokens and steps live in
[docs/PUBLISHER_SETUP.md](docs/PUBLISHER_SETUP.md). The X / LinkedIn values below
serve the older `mill publish` path. X stays held.

## Bulk checklist

### Host (already satisfied on CI / cloud agent image)
- [ ] `ffmpeg` + `ffprobe` with the `drawtext` filter (Ubuntu: `apt install ffmpeg`)
- [ ] Inter font (Ubuntu: `apt install fonts-inter`), or set `MILL_FONT` to any sans `.ttf/.otf`
- [ ] Python 3.10+, then `make install`

### X: live-capable adapter
- [ ] X developer account + Project + App at <https://developer.x.com> on a tier that allows `POST /2/tweets` and v2 media upload
- [ ] App permissions: **Read and write**
- [ ] `X_API_KEY`: app Consumer Key
- [ ] `X_API_KEY_SECRET`: app Consumer Secret
- [ ] `X_ACCESS_TOKEN`: user Access Token of the **@antisearch posting account** (generate *after* setting Read+Write)
- [ ] `X_ACCESS_TOKEN_SECRET`: matching Access Token Secret
- [ ] *(alternative, manual runs only)* `X_OAUTH2_ACCESS_TOKEN`: OAuth 2.0 user token with scopes `tweet.read tweet.write users.read media.write` (expires ~2h)

### LinkedIn: live-capable adapter
- [ ] LinkedIn app at <https://www.linkedin.com/developers/apps>, verified by the antisearch company page
- [ ] Product access: **Community Management API** (company page posting, `w_organization_social`) *or* **Share on LinkedIn** (personal, `w_member_social`)
- [ ] `LINKEDIN_ACCESS_TOKEN`: 3-legged OAuth token for an admin of the page (valid 60 days; set a reminder to rotate)
- [ ] `LINKEDIN_AUTHOR_URN`: `urn:li:organization:<page id>` (or `urn:li:person:<id>` for personal)
- [ ] *(optional)* `LINKEDIN_VERSION`: `YYYYMM` API version header, default `202609`

### TikTok: stub today (writes `out/drafts/tiktok/*.json`, never posts)
- [ ] TikTok developer app with **Content Posting API** approved (`video.upload` scope; drafts to inbox)
- [ ] `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_ACCESS_TOKEN`
- [ ] Decision: build the real adapter (`/v2/post/publish/inbox/video/init/`) once approved

### Instagram: stub today (writes `out/drafts/instagram/*.json`, never posts)
- [ ] Instagram **Business/Creator** account linked to a Facebook Page
- [ ] Meta app with `instagram_business_content_publish` (Reels)
- [ ] `INSTAGRAM_ACCESS_TOKEN` (long-lived), `INSTAGRAM_BUSINESS_ACCOUNT_ID`
- [ ] Note: Graph API Reels publishing needs the video at a **public URL**. Decide where clips get hosted (e.g. S3/R2 bucket) before building the adapter.

### Unattended runs (optional, later)
- [ ] Add the X + LinkedIn secrets above to the repo's GitHub Actions secrets (names identical)
- [ ] Decide ledger persistence for scheduled runs: `out/clips.csv` + `out/publish.csv` are the idempotency record. Today `mill.yml` only uploads them as an artifact, so a scheduled live run needs them committed back or stored in a bucket first.
- [ ] Captions: `caption` column in the queue (GTM owns this; empty = video-only post)
  - captions that quote the input quote the bare phrase (`dry shampoo`), never "best …"; see README → Input shape

## Going live (once the boxes above are ticked)

```bash
make doctor            # all live-capable platforms say "present"
make produce           # live oracle -> out/clips.csv
make publish           # dry-run again, read out/dry_run/*/*.json
make publish-live      # real posts; results in out/publish.csv
```

Safety rails that stay on in live mode:
- clips whose verdict came from the fixture oracle are never published (`skipped_not_live_oracle`)
- a clip already `published` on a platform is skipped (`skipped_already_published`)
- missing credentials skip that platform (`skipped_missing_credentials`); they never crash the run
- TikTok and Instagram only ever write drafts
