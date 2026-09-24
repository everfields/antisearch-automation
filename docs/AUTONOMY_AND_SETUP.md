# Autonomy walls + one-shot setup (AntiSearch social ops)

Owner: strategy brain (Opus 5.5), for CoS (Grok Bot) and Carlos. Written 2026-09-24,
amended the same day with the founder locks below.
Scope: how the Grok Bot squad opens and runs the AntiSearch social accounts for the
~20-day organic trial without dripping questions to Carlos, and the single list of
things only Carlos can give.

Locks kept (not reopened here): product constitution (whisper, bare input in, one
lowercase verdict out); the input is the bare phrase, never with "best" in front
(README → Input shape); video ritual (≤4s typing→verdict, caption = @handle only,
bio "ai chooses the best. nothing else."); one clip → one network; vertical map
(TikTok = beauty/hair/skin, IG = places, LinkedIn = employers / Company Page,
X = companies/SaaS, **held**); ≤2 posts/day total; eyes closed until day 21; first
posts order disfrutar → aman → psg; no ads, no spend, no `SHIP:` to `the_best`;
first post of each class needs an explicit yes in the CoS thread.

## Founder locks (Carlos, 2026-09-24)

These override anything below that reads differently.

1. **TikTok is not on Buffer.** The AntiSearch TikTok account already exists; its
   login email is `everfields@hotmail.com`. Path = direct login on the box + upload
   by Computer Use, with a mill extension that keeps the ledger (section 5).
2. **Buffer free = Instagram + LinkedIn only.** Instagram is a **new AntiSearch
   identity** on the AntiSearch mailbox, never the Everfields personal brand.
3. **Create the free AntiSearch Outlook.com mailbox.** `everfields@hotmail.com` is
   recovery only (the existing TikTok login is the one exception; see section 4).
4. **X is held.** Carlos lost the spare SIM, so the phone wall is real. Hold, and
   reserve the handle later when a phone path exists. No paid VoIP.
5. **LinkedIn goes through Buffer.** Use the AntiSearch email and recovery pattern
   rather than Google sign-in wherever there's a choice. The Page still needs a real
   admin (Carlos), per LinkedIn's rules.
6. **Persistent auth.** The setup sitting must leave long-lived sessions, TOTP
   secrets in 1Password, and Buffer OAuth (plus the TikTok session), so nobody
   re-auths every week. Refreshable tokens and stay-signed-in beat one-shot OTPs.
7. **Repos.** Both `everfields/the_best` and `everfields/antisearch-automation` are on
   the Cursor GitHub connection. Strategy Cloud Agents may **read** `the_best`
   (manifesto, prompts, eval set). Code changes happen only in
   `antisearch-automation`, unless Carlos says `SHIP:`.
8. **Vercel / GCP are optional.** Only if a lane needs them; never blocking.

---

## TL;DR

- **Mostly yes.** CoS can run the trial alone *after one sitting with Carlos on the
  box*. The drip happens because auth is done lazily, one wall at a time. Do it
  once, up front, and make it stick (lock 6).
- **Three posting paths, one per network:**
  - **Instagram + LinkedIn → Buffer (free).** Buffer posts through approved APIs,
    so there's no ban risk from scripting and no developer apps of our own. That
    uses 2 of the 3 free channels. The third stays empty, ready for X at unhold.
  - **TikTok → direct.** The existing account, logged in on the box, with uploads
    by Computer Use and the mill keeping the ledger. This is a founder-accepted
    risk: TikTok's terms don't allow automated access, so we keep it human-paced
    and inside one stable real browser session.
  - **X → held** until a phone path exists.
- **Do not ask for X / LinkedIn / TikTok / Meta API keys now.**
  - X's API has no free tier any more (pay-per-use, so it's spend).
  - LinkedIn Page posting via API needs a registered company, a business email on
    our domain, a privacy policy and a screencast review.
  - TikTok's API posts private-only until an audit.
  - The mill's X/LinkedIn adapters stay in the repo, dormant.
- **New free Outlook.com mailbox = the AntiSearch identity.** No phone on it.
  `everfields@hotmail.com` is recovery only. Password and authenticator secret live
  in 1Password. Carlos never opens it.
- **2FA rule for every account we control: never SMS; always an authenticator app
  whose secret is stored in 1Password.** 1Password autofills those codes, so
  authenticator 2FA stops being a wall.
- **Carlos's part:** one sitting (captchas, the TikTok login on the box, the LinkedIn
  Page authorization, Supabase secrets into Cursor). After that, only judgment
  calls.

---

## 1. What Grok Bot / CoS can already do alone

"Alone" means end to end with no message to Carlos, as long as none of the walls
in section 2 shows up.

| Capability | How | Limit |
| --- | --- | --- |
| Drive any website in a real browser | Computer Use on the shared box; cookies and logins persist across turns and across bots | Walls in section 2; recurring posting on X/LinkedIn must not be scripted (see 2.5) |
| Log in without seeing secrets | 1Password fills the credential | Only for logins stored in the vault |
| Fill authenticator (TOTP) codes | 1Password stores the TOTP secret in the login item and autofills the 6-digit code ([1Password docs](https://support.1password.com/one-time-passwords/)) | Only when *we* chose where the secret went. Verify once on the box that the box's 1Password fills OTP fields |
| Email one-time codes and magic links | Gmail connector; Hotmail and the AntiSearch Outlook mailbox through box browser sessions | The mailbox session must stay alive; the Operator lane re-logs it via 1Password |
| Connectors | Gmail, Calendar, Drive, GitHub, Bland | Bland places AI phone calls. It cannot receive SMS codes, and VoIP numbers get rejected at signup anyway. It is not a phone-verification path |
| Read the product | Strategy Cloud Agents read `everfields/the_best` through the Cursor GitHub connection (lock 7) | Read-only. At the time of writing this run's own GitHub token couldn't see `the_best`, so CAs that need it must be launched with that repo attached |
| Change the mill | Launch a Cursor Cloud Agent on `everfields/antisearch-automation`; it opens a PR (dry-run defaults, tests enforce bare input) | No merges by agents; no code edits to `the_best` without `SHIP:` |
| Produce clips with the real oracle | `mill produce` / `make dry-run` (the oracle answered `POST /verdict {"category":"thing"}` with 200 on 2026-09-24); `mill.yml` workflow_dispatch (dry-run unless `live` is ticked; not run yet) | Needs no credentials |
| Dry-run publishing | X/LinkedIn simulated flows; TikTok/IG write draft JSON to `out/drafts/` | Nothing leaves the machine |
| Health checks | `mill doctor --network` pings the oracle; the oracle is public | Pulse (telemetry) stays blind until the Supabase secrets exist (section 6) |

Bottom line: the only things CoS can't do alone are identity and legal steps (a
human at signup, a phone, a legal owner of a developer app) and secrets that have
to land in systems CoS can't write to. Everything after that is automatable.

---

## 2. Hard walls (blunt)

| # | Wall | Where it hits AntiSearch | Can an agent get past it? | What we do |
| --- | --- | --- | --- | --- |
| 2.1 | **SMS codes / phone-required signup** | X signup (often forced for new accounts), IG checkpoints, Gmail signup, Meta developer registration | **No.** Agents can't receive SMS. VoIP numbers (including anything Bland could rent) are rejected by most platforms and cost money. Paid SIMs are forbidden. Carlos has no spare SIM | Avoid SMS everywhere. X is held for exactly this reason (lock 4). If an IG checkpoint insists, Carlos's primary number once, then TOTP |
| 2.2 | **Authenticator-app 2FA** | Carlos's own accounts (Supabase, Vercel, GCP, Cloudflare, LinkedIn) whose secret sits on his phone | **Only if the secret is in 1Password.** For accounts we create, it is. For Carlos's existing accounts it isn't, so every expired session means pinging him | New accounts: always TOTP, secret stored in 1Password at setup. Carlos's tools: **delegate, don't impersonate** (invite a member, scoped token or service account) instead of CoS logging in as Carlos |
| 2.3 | **CAPTCHA, "press and hold", selfie video checks, passkeys** | New signups (Outlook, Instagram, Buffer), the first TikTok login from the box, sometimes a new-IP login | **No, and we won't try.** Defeating captchas breaks the platforms' terms and is unreliable | Batch them all into the one sitting. CoS drives; Carlos only does the human check |
| 2.4 | **Datacenter IP** | The box is a cloud machine. New accounts and new logins from datacenter IPs get more phone demands and checkpoints, and possibly less reach. The TikTok login from the box will likely trigger a security check the first time | Partly | One stable box session per account. No VPN hopping, no second account on the same network, human-paced activity. Residual risk accepted for a 20-day trial |
| 2.5 | **Platform automation rules** | **X:** "non-API-based forms of automation, such as scripting the X website" can lead to permanent suspension. **LinkedIn** User Agreement 8.2: no "bots or other unauthorized automated methods to … create, comment on, like, share, or re-share posts". **TikTok / Meta:** automated access without permission is not allowed | Technically yes; contractually no | IG + LinkedIn post only through Buffer (authorized). **TikTok direct upload is a founder-accepted risk (lock 1):** keep it human-paced, in the one real browser profile on the box, never headless and never from CI. If TikTok flags the account, the upload lane stops and CoS reports it in the digest |
| 2.6 | **Cloud Agent environment secrets** | Pulse needs `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` in the Cursor Cloud Agent environment | CoS can't set them from chat. Computer Use *could* copy them through Carlos's cursor.com session, but that pushes a service key through screenshots | Carlos pastes them in Cursor Dashboard → Cloud Agents → Secrets, once (section 6) |
| 2.7 | **Developer API ownership** | X developer console (now pay-per-use: $0.015 per post, $0.20 with a link; [pricing](https://docs.x.com/x-api/getting-started/pricing)); LinkedIn Community Management API (registered legal organization, verified business email, privacy policy, screencast; personal emails fail vetting; [LinkedIn](https://learn.microsoft.com/en-us/linkedin/marketing/community-management-app-review)); TikTok Content Posting API (unaudited apps post `SELF_ONLY` to private accounts; [TikTok](https://developers.tiktok.com/doc/content-sharing-guidelines)); Meta developer registration (phone or card on Carlos's Facebook account) | Agents can fill the forms. They can't be the legal or financial owner | **Deferred.** Buffer covers IG + LinkedIn; TikTok goes direct (section 5) |
| 2.8 | **LinkedIn identity** | A Company Page must be administered by a real member profile. A fake "AntiSearch" person profile breaks LinkedIn's terms and gets banned | No | LinkedIn = Carlos's profile as Page admin, permanently (lock 5). He can add a trusted human as a second admin later |
| 2.9 | **Publish gates (self-imposed, keep them)** | First post of each class; spend; X unhold; `SHIP:` to `the_best` | Not a bug | Carlos + CoS decide. CoS asks once per class, in the CoS thread |

---

## 3. The Galaxy lesson applied to AntiSearch

Galaxy (Ship by Thursday, Sep 15–17) ran the same shape we already have: one
orchestrator, specialist lanes, shared computers with persistent logins, Cursor
agents for code, humans for judgment and hard gates. Our gap isn't bots. It's
that **auth is done lazily, mid-flow**, so every wall becomes an interruption.

Rules we adopt:

1. **Front-load auth in one sitting, and make it last.** Every captcha, consent
   screen, OAuth grant and login check happens in a single session: CoS drives,
   Carlos only clicks the human-only steps. The sitting ends with long-lived
   sessions and refreshable tokens (section 4, persistence), so nothing needs him
   again except judgment.
2. **Delegate, don't impersonate.** Give the AntiSearch identity its own seat in
   Carlos's tools (Supabase org member, scoped tokens, service accounts) instead of
   CoS logging in as Carlos and hitting his phone-based 2FA every few weeks.
3. **Borrow approvals we don't have.** Buffer already passed the reviews at Meta and
   LinkedIn. Using it for IG + LinkedIn is cheaper than two developer programs and
   a legal entity.
4. **Lanes own the steady state.**
   - Clip: mill runs, clips on the box.
   - GTM: the Buffer queue (IG, LinkedIn) and the TikTok uploads.
   - Soul: taste review before anything is queued or uploaded.
   - Pulse: telemetry, eyes closed until day 21.
   - Operator: account health (expired sessions, checkpoints, token expiry).
   - CoS: orchestration and escalation.
5. **Human only for judgment:** first-of-class yes, spend yes, X unhold, the day-21
   review. Every other blocker goes into **one daily digest** from CoS, never a live
   ping, unless something is on fire (account locked, wrong content live).

---

## 4. Decision: social identity email (+ persistence)

**Decision (lock 3): a new free Outlook.com mailbox as the AntiSearch social identity.**
Candidates, first available wins: `antisearchai@outlook.com`,
`antisearch.ai@outlook.com`, `hello.antisearch@outlook.com`.
`everfields@hotmail.com` is its recovery email and nothing more.

| Option (free) | Phone at signup | Agents can run it day to day | Verdict |
| --- | --- | --- | --- |
| **Outlook.com** | Often email-only; Microsoft may still demand a phone depending on its risk check | Yes: box session, password + TOTP in 1Password, recovery to `everfields@hotmail.com` (CoS already reads Hotmail codes) | **Chosen.** Closed loop with no phone. Same ecosystem Carlos already uses |
| Proton Free | From datacenter IPs asks for human verification: captcha, email code or SMS. Email code works | Yes, web only | **Fallback** if Outlook forces a phone |
| Gmail | Increasingly forced for new accounts from new devices or datacenter IPs | Yes | No: there is no spare phone (lock 4) |
| Tuta Free | No phone, but new accounts can be held for approval, and some networks block the domain | Web only | No |

**Can agents own the mailbox day to day? Yes.** Setup:

- Stay-signed-in session in the box browser (Operator re-logs via 1Password if it drops).
- 2FA = "a different authenticator app" TOTP, secret in 1Password. Never Microsoft
  Authenticator push or passwordless-only, because both need a phone.
- Recovery email = `everfields@hotmail.com`. Unusual-sign-in checks then send a code
  there and CoS completes them.
- No phone number on the account.
- Operator signs in at least weekly (Microsoft deletes long-inactive accounts).

Carlos never needs to open it.

**Which account uses which email:**

| Account | Login email | Recovery | Note |
| --- | --- | --- | --- |
| Outlook mailbox | itself | `everfields@hotmail.com` | New |
| Instagram (new AntiSearch identity) | AntiSearch mailbox | — | Never the Everfields personal brand (lock 2). If an Everfields IG exists, leave it untouched |
| Buffer | AntiSearch mailbox, email + password (not "Continue with Google") | — | Lock 5 pattern. Buffer's reconnect emails land here, so Operator sees them |
| LinkedIn Page | Carlos's own LinkedIn (a Page has no login of its own) | — | Page notifications/contact email → AntiSearch mailbox where LinkedIn allows it |
| TikTok (existing) | `everfields@hotmail.com` | — | **Exception, per lock 1.** Don't change a working account's email before the first posts land. Moving the login to the AntiSearch mailbox is a post-day-21 option |
| X (held) | AntiSearch mailbox when reserved | — | Needs a phone path first (lock 4) |

**Optional brand layer:** `social@antisearch.ai` → the Outlook mailbox, via Cloudflare
Email Routing (free, receive-only). The DNS for antisearch.ai is on Cloudflare with no
MX records today, so nothing conflicts. It doesn't touch the website or `the_best`.
This isn't needed for the trial. It becomes useful if we ever apply for LinkedIn's
Community Management API (which requires a business email on our domain). Social
logins stay on the Outlook address, so a DNS change can never lock us out.

**If a network insists on a phone:**
- **X:** held; see the options below.
- **Instagram:** possible at a checkpoint (it may ask for a selfie video instead,
  which only Carlos can do). Carlos's primary number once, then TOTP; remove the
  number where allowed.
- **TikTok:** the account exists. Its login check should go to email (Hotmail).
- **LinkedIn:** n/a, it's Carlos's profile.

**X phone options (lock 4):**

| Option | What | Status |
| --- | --- | --- |
| (a) Hold | No X account until Carlos has a phone path. Accept that the handle may be taken meanwhile | **Preferred** |
| (b) Primary mobile once | Carlos's primary number at signup, then 2FA moves to TOTP-in-1Password and the number is removed where X allows | Allowed when Carlos chooses; not in this sitting |
| (c) Paid / VoIP number | — | **No.** It's spend, and X rejects most VoIP numbers anyway |

CoS may try **once** to reserve the handle with the AntiSearch mailbox alone. If X
asks for a phone, it stops there and doesn't ping Carlos.

### Persistence contract (lock 6)

The sitting's output is sessions and tokens that renew themselves, not codes that
work once. The rules:

- **Stay signed in everywhere.** Tick "keep me signed in", never log out, never
  clear the box browser profile. One browser profile per identity.
- **OAuth over passwords wherever there's a choice.** Buffer holds refreshable
  tokens for IG and LinkedIn and renews them itself. When it can't, it emails the
  Buffer account (the AntiSearch mailbox), and Operator reconnects using the
  sessions that are already live on the box.
- **One-time codes only at first login or on a security check,** and always by
  TOTP-in-1Password or by email to a mailbox the box reads. Never SMS.
- **Operator keeps sessions warm:** a weekly touch on every account (mailbox,
  TikTok, IG, Buffer, Carlos's LinkedIn session), and one digest line when
  something needs a re-login.
- **1Password itself must not need Carlos.** Verify in the sitting that the box's
  1Password stays usable (unlocked or via credential request) without his master
  password each time. If it doesn't, that's the one wall worth fixing first.

| Account | What persists | What renews it | Who re-auths if it breaks |
| --- | --- | --- | --- |
| Outlook mailbox | Stay-signed-in session | Password + TOTP in 1Password; recovery email to Hotmail | Operator |
| TikTok | Web session in the box's real browser profile | Password in 1Password + email code to Hotmail (+ TOTP in 1Password if 2-step is on) | Operator; Carlos only if a captcha appears |
| Instagram | Buffer OAuth token (Buffer refreshes it) + web session for bio/checkpoints | Password + TOTP in 1Password | Operator; Carlos only for a selfie/phone checkpoint |
| LinkedIn Page | Buffer OAuth token (Buffer refreshes it) + Carlos's LinkedIn session on the box | Carlos's LinkedIn login (see section 8, question 2) | Operator if the box session is alive; otherwise Carlos, rarely |
| Buffer | Stay-signed-in session; API key (valid until revoked) | Password + TOTP in 1Password | Operator |
| Supabase (Pulse) | Cloud Agent secrets (no expiry) + org membership for the AntiSearch mailbox | — | Nobody, unless the key is rotated |

---

## 5. Decision: Computer Use vs mill API, per network

The question was whether the browser can carry the 20-day trial, so we don't need
API keys. **Technically, yes** — ≤2 posts/day is trivial for Computer Use.
**Contractually, it depends on the network.** Scripted posting breaks X's and
LinkedIn's rules (2.5), so those two go through an authorized layer or wait.
TikTok goes direct by founder decision, with the risk stated plainly. **No API
keys for the trial.**

| Network (vertical) | (a) Account | (b) Posting during the trial | Mill native API (post-trial) | Ask for keys now? |
| --- | --- | --- | --- | --- |
| **TikTok** (beauty/hair/skin) | **Existing** AntiSearch account, login `everfields@hotmail.com`. Log in once on the box in the sitting (security check → email code or captcha) and keep that session | **Direct (lock 1):** GTM uploads through TikTok's web upload page with Computer Use, human-paced, caption @handle only. The mill provides the job ticket and records the result (below). **Not on Buffer** | Weak: unaudited apps post private-only, and the audit needs a production-grade app. Keep the stub | **No** |
| **Instagram** (places) | **New** AntiSearch account on the AntiSearch mailbox (never Everfields). Captcha/checkpoint → Carlos. Switch to **Creator or Business** (free) so Reels auto-publish from Buffer | **Buffer** IG channel (Reels). Connect with Instagram login if Buffer offers it, so nothing gets tied to a personal Facebook | Viable later: Instagram Login, Standard Access, no App Review for our own account ([Meta](https://developers.facebook.com/docs/instagram-platform/app-review/)). Needs Meta developer registration (phone/card on Carlos's Facebook) and a public video URL | **No** |
| **LinkedIn** (employers / Company Page) | The Page is created **from Carlos's profile**: CoS does it in his box session under his standing permission, or Carlos does it himself | **Buffer** LinkedIn Page channel. Carlos's profile authorizes Buffer once (OAuth, revocable from his LinkedIn settings). This is an authorized integration, so his profile isn't at risk | Heavy: Community Management API needs a legal entity, a domain business email, a privacy policy and a screencast review. The mill adapter stays dormant | **No** |
| **X** (companies/SaaS, **held**) | Not in the sitting (lock 4). Options (a)/(b)/(c) in section 4 | **None while held.** At unhold: Buffer's **third free slot**, which is kept empty for this ($0) | Pay-per-use, about $0.015 per post; only if Buffer is ever not an option, and only with Carlos's spend yes | **No** |

**Buffer: 3 free channels.**
1. Instagram.
2. LinkedIn Page.
3. Empty, reserved for X at unhold.

TikTok never uses a slot (lock 1).

**TikTok direct path, concretely:**

- **Upload now = Computer Use** in the box's real browser, in the same session the
  sitting leaves logged in:
  - one clip at a time, human-paced;
  - caption @handle only;
  - visibility public;
  - counted inside the ≤2 posts/day total.
- **Mill extension (Cloud Agent PR on `antisearch-automation`)**, so TikTok stays in
  the same ledger as everything else:
  - the existing TikTok draft JSON (`out/drafts/tiktok/<clip_id>.json`: file path,
    sha256, caption) becomes GTM's upload ticket;
  - a new `mill record --platform tiktok --clip <id> --url <post url>` writes a
    `published` row to `out/publish.csv`, so `mill status` and idempotency cover
    TikTok (no double posts);
  - `mill status` lists TikTok drafts still waiting for upload.
- **No scripted TikTok uploader in the repo for now.** A headless or CI uploader
  means a new device fingerprint, a datacenter IP and session cookies stored as CI
  secrets. That's the fastest way to get flagged. If CoS later wants a scripted
  helper, it runs only on the box, inside the same persistent profile,
  human-paced — and that decision waits until after day 21.

**Why this is enough for unattended operation:**

- **Phase A (trial start).**
  - Clip runs `mill.yml` (or the mill on a Cloud Agent) and gets the clips.
  - GTM loads the IG and LinkedIn clips into Buffer's web UI with Computer Use.
    That's our own tool; posting then goes out via official APIs. Buffer's free
    plan keeps 10 queued posts per channel, so one top-up covers several days.
  - GTM uploads TikTok clips directly and records each one with `mill record`.
  - No hosting, no platform keys.
- **Phase B (optional, still $0).** A mill adapter `publish/buffer.py` for IG +
  LinkedIn through Buffer's GraphQL API.
  - The API is on every plan, including Free: 1 personal key, 3,000 requests per
    30 days ([Buffer](https://support.buffer.com/en-us/articles/using-buffers-api-GtIYIQilz5)).
  - It needs a publicly reachable video URL
    ([example](https://developers.buffer.com/examples/create-video-post.html)).
    Clips get a free public bucket: Supabase Storage in a **separate free project**
    (`antisearch-mill`), so the mill never holds the product's keys.
  - Then `mill.yml` can run on a schedule with **two secrets** (`BUFFER_API_KEY` +
    the bucket key). Dry-run default and first-of-class yes stay.
  - TikTok stays manual-upload in Phase B.
- **Mill's native IG/LinkedIn adapters** remain the escape hatch if Buffer changes
  its free plan or a channel falls back to "notification publishing" (which needs
  a phone app). For IG, the fallback is the native Standard Access path.

**Buffer caveats (check at connect time, not blocking):**

- Free-plan terms can change.
- Each channel must show **automatic** publishing, not reminders.
- **≤2 posts/day total across TikTok + IG + LinkedIn.** Buffer slots and TikTok
  uploads share that budget; GTM owns the count.

---

## 6. ONE-SHOT checklist for Carlos

Everything, once. **No spend requested anywhere in this list.**

"CoS alone" means CoS does it without Carlos. "Carlos once" means only Carlos can
do it, one time. "Both" means CoS drives on the box and Carlos does the human-only
step.

| # | Item | Why | Who | Blocker if missing |
| --- | --- | --- | --- | --- |
| 1 | AntiSearch vault in 1Password on the box: confirm it autofills TOTP codes and stays usable without Carlos unlocking it each time | Every credential and 2FA secret lives there (lock 6) | CoS alone (Carlos once if the vault doesn't exist, or if unlocking needs him) | Every future login pings Carlos |
| 2 | **AntiSearch Outlook.com mailbox** (section 4), no phone, TOTP in 1Password, recovery `everfields@hotmail.com` | Social identity that isn't Carlos's personal inbox (lock 3) | Both (CoS; Carlos only for the captcha) | IG and Buffer have no identity to sign up with |
| 3 | **TikTok (existing):** log in on the box with `everfields@hotmail.com`, "stay logged in", password into 1Password, 2-step via authenticator app with the secret in 1Password (email as backup, no SMS), bio set | TikTok lane, direct path (lock 1) | Both (CoS; Carlos only if TikTok shows a captcha, or if the password isn't in 1Password yet) | No TikTok lane |
| 4 | **Instagram (new AntiSearch identity)** on the AntiSearch mailbox → Creator/Business, bio, TOTP in 1Password | IG lane (lock 2) | Both (captcha / checkpoint / possible selfie video; Carlos's primary number only if IG insists) | No IG lane |
| 5 | **LinkedIn Company Page** "AntiSearch", admin = Carlos's profile; Carlos's LinkedIn signed in on the box with "remember me" | LinkedIn lane; Pages can't exist without a real admin (lock 5) | Both (Carlos's LinkedIn login/2FA once; CoS creates the Page under standing permission) | No LinkedIn lane |
| 6 | **Buffer Free** on the AntiSearch mailbox (email + password, not Google sign-in), TOTP in 1Password | Authorized posting for IG + LinkedIn, $0 | CoS alone | No compliant IG/LinkedIn posting path |
| 7 | Connect **Instagram + LinkedIn Page** to Buffer, automatic publishing on; slot 3 left empty | IG + LinkedIn posting through official APIs (lock 2) | Both (LinkedIn OAuth runs in Carlos's session) | IG/LinkedIn posting impossible without scripting the sites |
| 8 | Supabase (Pulse): `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` in Cursor Dashboard → Cloud Agents → Secrets | Pulse telemetry, already blocked on this. A read-only Postgres role would be safer than the service key (section 8) | **Carlos once** | Pulse stays blind for the whole trial |
| 9 | Supabase: invite the AntiSearch mailbox into the org (read-only/developer role) | CoS opens the dashboard without Carlos's 2FA (delegate, don't impersonate) | Carlos once (invite); CoS accepts | Every dashboard visit needs Carlos |
| 10 | Buffer API key (free, 1 key) → 1Password | Phase B unattended cron (IG + LinkedIn) | CoS alone | Only Phase B waits |
| 11 | Supabase: separate free project `antisearch-mill` with a public Storage bucket `clips` | Public video URLs for Phase B; keeps product keys out of the mill | CoS alone (after #9, if the role allows project creation) | Only Phase B waits |
| 12 | GitHub Actions secrets `BUFFER_API_KEY` + bucket key on `antisearch-automation` | Phase B cron from `mill.yml` | CoS if its GitHub connector has repo admin, else Carlos once | Only Phase B waits |
| 13 | CoS can dispatch `mill.yml` and download its artifact through the GitHub connector | Clip handoff without a Cloud Agent in the loop | CoS alone (verify) | Clip lane uses a Cloud Agent run instead |
| 14 | Strategy Cloud Agents launched with `everfields/the_best` attached, read-only | Manifesto, prompt and eval set as ground truth (lock 7) | CoS alone | Strategy works from summaries instead of the source |
| 15 | **X** handle | Held (lock 4). Reserve when a phone path exists; CoS may try once without a phone | Later: Carlos once, only with option (b) | Handle may be taken; nothing else breaks |
| 16 | **Vercel / Google Cloud** | Optional (lock 8). Production antisearch.ai resolves to a Microsoft Azure IP running uvicorn, behind Cloudflare DNS, so neither is in the request path | CoS checks with existing box sessions; Carlos once for a scoped token **only if** a lane needs it | None |
| 17 | Cloudflare Email Routing `social@antisearch.ai` → the Outlook mailbox (optional) | Brand contact; future LinkedIn API vetting | Carlos once (or CoS if a Cloudflare member invite / session exists) | None for the trial |
| 18 | Mill platform secrets `X_*`, `LINKEDIN_*`, `TIKTOK_*`, `INSTAGRAM_*` (SETUP.md) | Native API adapters | **Nobody, not now** | None for the trial |

**Order for the sitting** (CoS drives, Carlos on the box):

1. 1Password check (#1)
2. Outlook mailbox (#2)
3. TikTok login + 2-step to TOTP (#3)
4. Instagram signup (#4)
5. LinkedIn login + Page (#5)
6. Buffer: sign up, connect IG + LinkedIn (#6, #7)
7. Supabase invite + Cursor secrets (#8, #9)
8. Cloudflare routing (#17, optional)

**Before Carlos leaves the box,** CoS confirms every session in the persistence table
(section 4) is signed in with "stay signed in", and that every secret and TOTP is in
1Password. Everything else is CoS alone, before or after.

---

## 7. What CoS does next without pinging Carlos (48h after this PR)

Ordered. Anything that hits a wall gets parked for the sitting, not pinged.

**Before the sitting (hours 0–24)**

1. **Inventory accounts.** For AntiSearch / AntiSearchAI and any Everfields-branded
   account: which exist on TikTok, IG, X and LinkedIn; which email each uses; which
   sessions are live on the box. Confirm the TikTok password is in 1Password. One
   table in the CoS thread.
2. **Try the Outlook mailbox alone.** If Microsoft shows only an email path and no
   captcha, finish it, set TOTP in 1Password and add the recovery email. That also
   proves item #1. If it hits a captcha or phone, park it.
3. **Create the Buffer account** once the mailbox exists (email verification only).
4. **Try the TikTok login on the box.** If TikTok only asks for an email code
   (Hotmail), finish it, keep the session, and move 2-step to TOTP-in-1Password. If
   there's a captcha, park it for the sitting.
5. **Launch a Cloud Agent: trial queue + TikTok ledger PR** on `antisearch-automation`:
   - `queue/trial_queue.csv` with **one platform per row** following the vertical
     map. The sample queue sends every row to all four networks, which breaks
     "one clip → one network".
   - First posts in the locked order; captions empty or @handle only; bare inputs
     (the existing tests cover every `queue/*.csv` automatically).
   - `mill record` for manual TikTok uploads, and TikTok pending drafts in
     `mill status` (section 5).
6. **Launch a Cloud Agent: Phase B PR** — `publish/buffer.py` for IG + LinkedIn
   (GraphQL, dry-run default, refuses fixture-oracle clips like the other adapters)
   + a SETUP section. No live use until the sitting and a first-of-class yes.
7. **Produce the first clips** with the live oracle (dry-run `mill.yml` or a
   Cloud Agent `make dry-run`). Soul reviews against the ritual. Keep them on the box.
8. **Optional, once:** try reserving the X handle with the AntiSearch mailbox. If X
   asks for a phone, stop (lock 4).
9. **Send Carlos the checklist once**, with the exact sitting order and only the
   steps still open after 1–4.

**After the sitting (hours 24–48)**

10. Set bios ("ai chooses the best. nothing else.") and display "antisearch.ai" on
    TikTok, IG and the LinkedIn Page. Check the persistence table: every account
    signed in, every secret and TOTP in 1Password.
11. In Buffer: set IG + LinkedIn slots so that, together with TikTok uploads, the
    total stays ≤2/day. Confirm both channels show automatic publishing.
12. Prepare the **first post of each class**: IG and LinkedIn as Buffer drafts (not
    scheduled), TikTok as a ready upload ticket. Ask for the explicit yes in the CoS
    thread, one message for all three. After a yes: fill that Buffer channel's queue
    (≤10), or upload that TikTok clip and `mill record` it. Then top up without
    asking again.
13. Operator starts the daily health check and the weekly session touch:
    - TikTok, IG, mailbox and Buffer sessions;
    - Buffer channel status;
    - checkpoints and token expiry.
    Blockers go into the daily digest.
14. Pulse: if #8 has landed, start collecting; eyes closed until day 21 (no tweaks
    driven by metrics).

---

## 8. Open questions for Carlos (only what we can't decide for you)

1. **Legal entity:** is there a registered company behind AntiSearch/everfields?
   It decides whether LinkedIn's Community Management API and Meta organization
   verification are ever possible after the trial. It doesn't affect the trial.
2. **Your LinkedIn 2FA:** OK to switch your LinkedIn 2-step to an authenticator app
   and scan the same QR into both your phone and the box's 1Password? Both then
   produce valid codes, and Operator can restore the LinkedIn session (which Buffer
   reconnects through) without you. If no, a lost LinkedIn session on the box means
   one ping to you, rarely.
3. **Pulse key:** paste the Supabase service key as asked before (fastest; it can
   read and write everything), or create a read-only Postgres role for Pulse
   (safer, a few more clicks for you)?
