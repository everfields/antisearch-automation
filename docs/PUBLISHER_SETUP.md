# Own publisher: setup, env vars, and what each API can't do

`mill post` posts a finished clip (or its verdict frame) from the queue through each
network's **official API**. It uses no browser, no Buffer and no Grok Bot box, and it
runs from GitHub Actions (`.github/workflows/publisher.yml`). It is dry-run unless
`--live` is set. Written 2026-09-24.

## Today's lesson, as a rule

Instagram burned because the same accounts were touched from the Grok Bot box
(datacenter IP) and from Carlos's home IP. So:

- **Humans create accounts, developer apps and OAuth consents once, from their own
  phone or laptop** (home / mobile IP). Steps tagged **[own device]** below.
- **After that, only API calls**, from GitHub Actions. Platforms expect server-to-server
  API traffic from cloud IPs; what they flag is *browser sessions* from cloud IPs.
- **Nobody opens these accounts' web UI from the Grok Bot box. Ever.**

Steps tagged **[anywhere]** are API calls or secret pasting that CoS or a Cloud Agent
can do.

## Status per network (go-live priority order)

| # | Network | Can go live | What a free / unaudited app cannot do |
| --- | --- | --- | --- |
| 1 | **Bluesky** | **Today.** Email-only signup + app password | Video needs a confirmed email and is capped per day by Bluesky; images ≤ 1 MB; text ≤ 300 characters |
| 2 | Threads | Blocked | Needs a Meta developer app (Carlos's Facebook, phone- or card-verified) and a **public URL** for every media file (no direct upload). Tokens last 60 days |
| 3 | **LinkedIn** | **Today as Carlos's profile** (Share on LinkedIn, self-serve). **Company Page is blocked** | Page posting (`w_organization_social`) needs Community Management API approval: registered legal organization, business email on antisearch.ai, privacy policy, review. Tokens last 60 days |
| 4 | **TikTok** | **Today as inbox drafts** | TikTok **does not audit apps that only post to your own accounts**, so we never get public Direct Post. `inbox` mode: the clip lands in the TikTok app inbox and a human taps Post (max 5 pending per 24h). `direct` mode: `SELF_ONLY` on a private account |
| 5 | Instagram | Blocked | Account suspended pending selfie verification. Needs a Professional account, a Meta app and a public media URL. Tokens last 60 days |
| 6 | Reddit | Blocked | Self-service API keys ended Nov 2025; a script app needs Reddit's explicit approval (rarely granted). The post URL arrives by websocket, so we log the profile's submissions page |
| 7 | Mastodon | Today | Email signup (some instances need approval), small reach, per-instance limits |

## How it runs

```bash
mill networks                                   # adapters, credentials, blocked reasons
mill post --queue queue/X.csv                   # dry-run: plans in out/dry_run_posts/<network>/<job>.json
mill post --queue queue/X.csv --live --state state/posts.csv
mill oauth tiktok url | mill oauth tiktok exchange --code '<url you landed on>'
mill oauth linkedin url --scope w_member_social | mill oauth linkedin exchange --code '<url>'
```

**Locks the code enforces** (`src/antisearch_mill/publisher/guard.py`):

- **≤ 2 posts per day in total**, across all networks, Europe/Madrid calendar day.
  `PUBLISHER_DAILY_CAP` can lower it; raising it needs a code change.
- **One clip → one network:** a queue row must list exactly one network, and a row
  that went out once (anywhere) never goes out again.
- **Caption is empty, the bare input, or an @handle.** Nothing that starts with a
  ranking word.
- **First of each class needs Carlos's yes:** a network posts live only if it's
  listed in `PUBLISHER_LIVE_NETWORKS`. Adding it there *is* the recorded yes.
- **Never double-post:** every live attempt writes a `pending` row before calling the
  API. A `pending` row with no outcome (crash mid-post) blocks that row until a human
  checks the network. Failures retry only with `--retry-failed`. Mastodon also gets
  an `Idempotency-Key`.
- **Only real verdicts:** fixture verdicts and the oracle's `no` never go out.
- **Clips are made just in time:** only rows that will post this run are rendered, so
  the mill adds at most 2 calls a day to the oracle's traffic.

**Queue:** the same CSV as the mill (`id,category,platforms,caption,notes`), with
`platforms` holding exactly one of `bluesky threads linkedin tiktok instagram reddit
mastodon`. `--kind image` posts the verdict frame (the raw screenshot) instead of
the clip.

**GitHub Actions** (`publisher.yml`) is **off by default**.
- **Manual:** Actions → publisher → Run workflow.
- **Cron:** twice a day, one post per run. It only runs when the repo variable
  `PUBLISHER_CRON` is `dry-run` or `live`.
- **Post log:** kept on the `publisher-state` branch, so runs never double-post.
- **Minutes:** about 3 per run; this fits the private-repo free minutes.

## Environment variables (exact list)

Secrets go in GitHub → repo Settings → Secrets and variables → Actions → **Secrets**.
Switches go under **Variables**. For local runs, use `.env`.

| Name | Kind | Network | Notes |
| --- | --- | --- | --- |
| `BLUESKY_HANDLE` | secret | Bluesky | e.g. `antisearch.bsky.social` or `antisearch.ai` |
| `BLUESKY_APP_PASSWORD` | secret | Bluesky | App password, not the account password |
| `BLUESKY_SERVICE` | optional | Bluesky | Default `https://bsky.social` |
| `THREADS_USER_ID` | secret | Threads | |
| `THREADS_ACCESS_TOKEN` | secret | Threads | Long-lived, 60 days |
| `LINKEDIN_ACCESS_TOKEN` | secret | LinkedIn | 60 days |
| `LINKEDIN_AUTHOR_URN` | secret | LinkedIn | `urn:li:organization:<id>` (Page) or `urn:li:person:<id>` (Carlos) |
| `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` | secret | LinkedIn | Also used by `mill oauth linkedin` |
| `LINKEDIN_REFRESH_TOKEN` | secret, optional | LinkedIn | Only if LinkedIn issues one; then the access token is minted each run |
| `LINKEDIN_VERSION` | optional | LinkedIn | Default `202609` |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` | secret | TikTok | |
| `TIKTOK_REFRESH_TOKEN` | secret | TikTok | 365 days; if TikTok rotates it, the run log says so and the secret must be updated |
| `TIKTOK_ACCESS_TOKEN` | optional | TikTok | 24h; manual runs only |
| `TIKTOK_MODE` | variable | TikTok | `inbox` (default) or `direct` |
| `TIKTOK_PRIVACY_LEVEL` | optional | TikTok | `direct` only; default `SELF_ONLY` |
| `INSTAGRAM_BUSINESS_ACCOUNT_ID`, `INSTAGRAM_ACCESS_TOKEN` | secret | Instagram | |
| `INSTAGRAM_GRAPH_VERSION` | optional | Instagram | Default `v24.0` |
| `PUBLISHER_PUBLIC_BASE_URL` | variable | Threads, Instagram | Public folder the clip files are already served from (not automated yet) |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD` | secret | Reddit | Script app; the account can't have 2FA for the password grant |
| `REDDIT_SUBREDDIT`, `REDDIT_USER_AGENT` | optional | Reddit | Default `u_<username>` |
| `MASTODON_BASE_URL`, `MASTODON_ACCESS_TOKEN` | secret | Mastodon | Token scopes `write:media write:statuses` |
| `MASTODON_VISIBILITY` | optional | Mastodon | Default `public` |
| `PUBLISHER_LIVE_NETWORKS` | variable | all | e.g. `bluesky,linkedin`. The first-of-class yes, recorded |
| `PUBLISHER_CRON` | variable | all | unset = off; `dry-run`; `live` |
| `PUBLISHER_QUEUE` | variable | all | Queue CSV for the workflow |
| `PUBLISHER_KIND` | variable | all | `video` (default) or `image` |
| `PUBLISHER_DAILY_CAP` | variable | all | 0–2 |
| `PUBLISHER_TZ` | optional | all | Default `Europe/Madrid` |
| `PUBLISHER_OAUTH_REDIRECT_URI` | optional | TikTok, LinkedIn | Default `https://antisearch.ai/` (the code only needs to land in the address bar) |

---

## One sitting: Bluesky + LinkedIn + TikTok live

Carlos on his own phone or laptop; CoS on chat. The steps are in the order they
happen.

| # | Step | Where |
| --- | --- | --- |
| 1 | **Bluesky:** bsky.app → Sign up → email `antisearch@outlook.com`, password from 1Password, handle `antisearch` → confirm the email code | [own device] |
| 2 | Bluesky → Settings → Privacy and security → **App passwords** → Add `publisher` → paste it into the GitHub secret `BLUESKY_APP_PASSWORD` (and `BLUESKY_HANDLE`) | [own device] → GitHub |
| 3 | **LinkedIn:** linkedin.com/developers/apps/new → name `AntiSearch Publisher`, LinkedIn Page `AntiSearch` (create it first at linkedin.com/company/setup/new if it doesn't exist), logo → Create. Settings tab → **Verify** → open the link as Page admin → Verify | [own device] |
| 4 | Products tab → **Share on LinkedIn** + **Sign In with LinkedIn using OpenID Connect** (instant). Only if there's a registered company: also request **Community Management API** | [own device] |
| 5 | Auth tab → add redirect URL `https://antisearch.ai/` → send CoS the Client ID; paste the Client Secret into the GitHub secret | [own device] → GitHub |
| 6 | **TikTok:** developers.tiktok.com → Manage apps → Connect an app → add **Login Kit** (redirect URI `https://antisearch.ai/`) + **Content Posting API** (scopes `video.upload`, `video.publish`) → switch to **Sandbox** → Target users → add the AntiSearch TikTok account → send CoS the Client key; paste the Client secret into the GitHub secret | [own device] |
| 7 | CoS sends **two links** (`mill oauth linkedin url --scope "openid profile w_member_social"` and `mill oauth tiktok url`). Open each, logged in as the right account (LinkedIn: Carlos; TikTok: AntiSearch, on the phone), Approve, and send back the URL you land on | [own device] |
| 8 | CoS exchanges both codes, stores `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_AUTHOR_URN` (`urn:li:person:<sub>` from `GET https://api.linkedin.com/v2/userinfo`) and `TIKTOK_REFRESH_TOKEN`, then runs the workflow in dry-run | [anywhere] |
| 9 | Carlos's **yes per network** → CoS sets `PUBLISHER_LIVE_NETWORKS` (e.g. `bluesky,linkedin,tiktok`) and, when he says so, `PUBLISHER_CRON=live` | GitHub |

After that, the only recurring human act is **tapping Post on TikTok drafts** in the
app. Tokens need rotating every 60 days (LinkedIn) and every 365 days (TikTok).

If `PUBLISHER_CRON=live` runs with the LinkedIn token above, it posts **as Carlos's
personal profile**, not the Page. That's a deviation from the "LinkedIn = Company
Page" lock and needs his explicit yes. Without it, LinkedIn stays dry-run until
Community Management is approved.

---

## Per network: exact steps

### 1. Bluesky (live today)
1. [own device] bsky.app → Sign up → hosting provider Bluesky Social → email, password, birthdate, handle → captcha if shown.
2. [own device] Confirm the email. **Video uploads need a confirmed email.**
3. [own device] Settings → Privacy and security → App passwords → Add → copy once → secret `BLUESKY_APP_PASSWORD`; `BLUESKY_HANDLE` = the handle.
4. Optional, on-brand: handle `@antisearch.ai`. Settings → Account → Handle → "I have my own domain" → add the shown `_atproto` TXT record in Cloudflare DNS (additive; doesn't touch the website) → Verify. Then update `BLUESKY_HANDLE`.
5. Profile: display name `antisearch.ai`, bio `ai chooses the best. nothing else.`. Add the self-label "bot" only if replies-on-mention ships (GTM doc).

No expiry. Revoke the app password to cut access.

### 2. Threads (blocked: Meta developer + media host)
1. [own device] Create the Threads profile (the Threads app; Instagram is no longer required).
2. [own device] developers.facebook.com with Carlos's Facebook (Meta requires a phone or card on it) → Create app → use case "Access the Threads API" → add the Threads profile as Threads Tester and accept the invite in Threads → Settings → Account → Website permissions.
3. [own device] App dashboard → Threads API → generate a user token with `threads_basic, threads_content_publish` → exchange it for a long-lived token → secrets `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`.
4. [anywhere] Media host: a public folder that serves `.mp4` with the right content type (e.g. GitHub Pages on a separate public repo). Set `PUBLISHER_PUBLIC_BASE_URL`. Uploading the clip there before posting is **not automated yet**.

### 3. LinkedIn
Company Page (the lock): request **Community Management API**. The form needs a
legal company name and address, a business email on antisearch.ai (e.g. Cloudflare
Email Routing `social@antisearch.ai`), a privacy policy URL and a use case; Standard
tier later needs a screencast. Without a registered company, expect a refusal.
Then run `mill oauth linkedin url` (default scope `w_organization_social`) and set
`LINKEDIN_AUTHOR_URN=urn:li:organization:<id>` (the number in the Page admin URL).
Carlos's profile (works today): steps 3–8 of the sitting above.

### 4. TikTok (inbox drafts today)
Steps 6–8 of the sitting. **Verify on the first run** that a sandbox app's inbox
draft can be posted publicly from the app. If TikTok forces private there too, the
API can't carry public TikTok for us at all, and the path is Carlos posting the
clip file from his phone.

### 5. Instagram (blocked)
Wait out the suspension on Carlos's phone only (the selfie check). Then: Professional
account → Meta app with "Instagram API with Instagram login" (Standard Access, no
App Review for our own account) → token with `instagram_business_basic,
instagram_business_content_publish` → secrets. A Facebook Page is **not** required
with Instagram login. It needs the same media host as Threads.

### 6. Reddit (blocked)
[own device] Submit Reddit's Data API access request (Responsible Builder Policy).
Only after written approval: reddit.com/prefs/apps → create a **script** app → secrets.
The account must not have 2FA for the password grant. Post only to our own profile
(`u_<name>`) unless a subreddit's rules allow it.

### 7. Mastodon (live today)
1. [own device] Sign up on an instance with open email signups; profile → mark as bot.
2. [own device] Preferences → Development → New application → scopes `write:media write:statuses` → copy the access token → secrets `MASTODON_ACCESS_TOKEN`, `MASTODON_BASE_URL`.

No expiry.

## Rotation calendar (Operator lane)

| Token | Lasts | Action |
| --- | --- | --- |
| Bluesky app password, Mastodon token | Until revoked | — |
| LinkedIn access token | 60 days | Rerun `mill oauth linkedin` (one tap by Carlos) before day 55 |
| TikTok refresh token | 365 days, may rotate | Watch run logs for "rotated"; update the secret |
| Threads / Instagram long-lived token | 60 days | Refresh before expiry |
