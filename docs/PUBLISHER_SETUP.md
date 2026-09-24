# Publisher: one sitting to go live (Bluesky video + TikTok inbox drafts)

**[HUMAN IP]** = done by Carlos on his own phone or laptop (home or mobile network),
**never** from the Grok Bot box. Signups, consents and CAPTCHAs from a datacenter IP
are what burned Instagram. Every other step is an API call or a settings page, and
CoS can do it.

Secrets go in: github.com/everfields/antisearch-automation → Settings → Secrets and
variables → Actions → **Secrets**. Switches go under **Variables**.

## Bluesky (stand-in for the held X vertical; posts the frozen ≤4s 9:16 clip only)

1. **[HUMAN IP]** bsky.app → Sign up (hCaptcha) → email `antisearch@outlook.com`,
   password from 1Password, handle `antisearch` → **confirm the email code** (video
   uploads need it).
2. **[HUMAN IP]** Settings → Privacy and security → App passwords → Add `publisher`
   → copy it.
3. Secrets: `BLUESKY_HANDLE` = `antisearch.bsky.social`, `BLUESKY_APP_PASSWORD` =
   the app password.
4. **[HUMAN IP]** Settings → Account → Handle → "I have my own domain" → enter
   `antisearch.ai` → copy the TXT value.
   Cloudflare → antisearch.ai → DNS → Add record: type `TXT`, name `_atproto`,
   content `did=did:plc:…` (the copied value). This is additive and doesn't touch
   the website.
   Back in Bluesky → Verify. Then set the secret `BLUESKY_HANDLE` = `antisearch.ai`.
5. **[HUMAN IP]** Profile:
   - avatar = [`docs/assets/bluesky-avatar.png`](assets/bluesky-avatar.png)
     (cursor block `#E8E4D8` on `#0A0A0A`);
   - display name `antisearch.ai`;
   - bio `ai chooses the best. nothing else.`;
   - no banner, no pinned post.

## TikTok (inbox drafts; a human taps Post in the app)

6. **[HUMAN IP]** developers.tiktok.com → Manage apps → Connect an app →
   - add **Login Kit** (Web, redirect URI `https://antisearch.ai/`);
   - add **Content Posting API** (scope `video.upload`);
   - switch to **Sandbox** → Target users → add the AntiSearch TikTok account.
7. Secrets: `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`.
8. CoS runs `mill oauth tiktok url` and sends the link. **[HUMAN IP]** On the phone
   logged into the AntiSearch TikTok: open it → Authorize → send CoS the address
   you land on (`https://antisearch.ai/?code=…`).
9. CoS runs `mill oauth tiktok exchange --code '<that address>'` → secret
   `TIKTOK_REFRESH_TOKEN`.

## Go live

10. CoS: Actions → publisher → Run workflow (leave `live` unticked). This dry-run
    never calls the oracle.
11. Carlos's yes → Variables:
    - `PUBLISHER_LIVE_NETWORKS` = `bluesky,tiktok` (this is the recorded
      first-of-class yes);
    - `PUBLISHER_CRON` = `live`.

    Result: **10:07 Madrid** posts `thing` to Bluesky; **19:07** sends the
    `dry shampoo` draft to the TikTok inbox.
12. **[HUMAN IP]** Each TikTok draft: TikTok → inbox → the draft → caption **only**
    the crowned brand's verified @handle, or nothing → Post.

Recurring: step 12 per TikTok draft. On the second Bluesky company row, CoS sets the
held tag (below). Nothing else.

---

## How the rules are enforced

- **One honest run per input.** Only a live run asks the real oracle, once per
  input. The answer is frozen in `verdicts.csv` on the `publisher-state` branch
  before anything else happens; retries and re-renders replay it (renders are
  byte-identical for the same verdict). Dry-runs never call the oracle.
  - Don't use `mill oracle` on a queued input: that would spend its honest run
    outside the log.
- **Cadence:** ≤2 posts per day in total, ≤1 per network (Madrid day), one post per
  scheduled run.
- **One clip → one network, never twice:** a `pending` row is written before every
  API call, and a `pending` row with no outcome blocks that row until checked.
- **Bluesky:** the video clip only. No images, text-only posts, replies, follows,
  reposts or likes (the code has none of these calls).
  - Caption: empty, or a company's verified **domain** handle that resolves to an
    account (a dead tag fails the post).
  - **Frozen once `x` is added to `PUBLISHER_LIVE_NETWORKS`**, so one vertical never
    runs on two networks.
- **Tags after the honest run:** company rows carry the caption `@?`. The live run
  freezes the verdict, reports `held_for_tag`, and holds later Bluesky rows. CoS
  then edits the row's caption in `queue/bluesky_trial.csv` (PR) to
  `@<company domain>` if a verified domain handle exists, else `-` (none). The next
  run posts it.
- **Queues:** [`queue/bluesky_trial.csv`](../queue/bluesky_trial.csv)
  (thing, password manager, silence, note-taking app, a year) and
  [`queue/tiktok_trial.csv`](../queue/tiktok_trial.csv) (dry shampoo). The workflow
  reads both, Bluesky first.

## Env vars for this sitting

| Name | Where | Notes |
| --- | --- | --- |
| `BLUESKY_HANDLE` | secret | `antisearch.bsky.social`, then `antisearch.ai` |
| `BLUESKY_APP_PASSWORD` | secret | App password; revoke it to cut access. No expiry |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` | secret | |
| `TIKTOK_REFRESH_TOKEN` | secret | 365 days; if a run log says "rotated", update it |
| `PUBLISHER_LIVE_NETWORKS` | variable | `bluesky,tiktok`. Adding `x` later freezes Bluesky |
| `PUBLISHER_CRON` | variable | unset = off; `dry-run`; `live` |
| `PUBLISHER_QUEUE` | variable, optional | Default `queue/bluesky_trial.csv queue/tiktok_trial.csv` |
| `PUBLISHER_DAILY_CAP` | variable, optional | 0–2 |

The cron runs at 08:07 and 17:07 UTC, which is 10:07 and 19:07 Madrid until the
clocks change on 2026-10-25 (then 09:07 and 18:07).

## Other adapters (built, tested, not in this sitting)

`mill networks` prints each one's status. In short:
- **LinkedIn Page:** needs Community Management approval (a registered company).
  It works today only as Carlos's personal profile, which needs his explicit yes.
- **Threads:** a Meta developer account on Carlos's Facebook, plus a public media
  host.
- **Instagram:** suspended, plus the same Meta needs.
- **Reddit:** the API is closed to new apps.
- **Mastodon:** email signup; small reach.
