# Autonomy walls + one-shot setup (AntiSearch social ops)

Owner: strategy brain (Opus 5.5), for CoS (Grok Bot) and Carlos. Written 2026-09-24.
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

---

## TL;DR

- **Mostly yes.** CoS can run the trial alone *after one sitting with Carlos on the
  box*. The drip happens because auth is done lazily, one wall at a time. Do it
  once, up front.
- **Posting goes through Buffer (free plan), not through a scripted browser and not
  through our own developer apps.** X and LinkedIn explicitly ban scripted-browser
  posting (X threatens permanent suspension; on LinkedIn the risk lands on Carlos's
  personal profile, because a Company Page is administered by a real member).
  Buffer already holds approved API access to TikTok, Instagram, LinkedIn Pages and
  X. Its free plan gives 3 channels with 10 queued posts each, which covers
  TikTok + IG + LinkedIn for the trial. X stays held.
- **Do not ask for X / LinkedIn / TikTok / Meta API keys now.** X's API has no free
  tier any more (pay-per-use, spend). LinkedIn Page posting via API needs a
  registered company, a business email on our domain, a privacy policy and a
  screencast review. TikTok's API posts private-only until an audit. The mill's
  X/LinkedIn adapters stay in the repo, dormant.
- **Social identity email: a new free Outlook.com mailbox that the agents own.** No
  phone on it. Recovery goes to `everfields@hotmail.com`, which CoS already reads.
  Its password and authenticator secret live in 1Password. Carlos never opens it.
  Optional later: `social@antisearch.ai` forwarding via Cloudflare Email Routing
  (free; the domain's DNS is already on Cloudflare and has no MX records).
- **2FA rule for every account we create: never SMS; always an authenticator app
  whose secret is stored in 1Password.** 1Password autofills those codes, so for
  agent-owned accounts authenticator 2FA stops being a wall.
- **Carlos's part:** one sitting (captchas, his existing phone number if a network
  insists, the LinkedIn Page authorization, Supabase secrets into Cursor). After
  that, only judgment calls.

---

## 1. What Grok Bot / CoS can already do alone

"Alone" means end to end with no message to Carlos, as long as none of the walls
in section 2 shows up.

| Capability | How | Limit |
| --- | --- | --- |
| Drive any website in a real browser | Computer Use on the shared box; cookies and logins persist across turns and across bots | Walls in section 2; recurring *posting* must not be scripted on X/LinkedIn (see 2.5) |
| Log in without seeing secrets | 1Password fills the credential | Only for logins stored in the vault |
| Fill authenticator (TOTP) codes | 1Password stores the TOTP secret in the login item and autofills the 6-digit code ([1Password docs](https://support.1password.com/one-time-passwords/)) | Only when *we* chose where the secret went. Verify once on the box that the box's 1Password fills OTP fields |
| Email one-time codes and magic links | Gmail connector; Hotmail and (soon) the AntiSearch Outlook mailbox through box browser sessions | The mailbox session must stay alive; the Operator lane re-logs it via 1Password |
| Connectors | Gmail, Calendar, Drive, GitHub, Bland | Bland places AI phone calls. It cannot receive SMS codes, and VoIP numbers get rejected at signup anyway. It is not a phone-verification path |
| Change the mill | Launch a Cursor Cloud Agent on `everfields/antisearch-automation`; it opens a PR (dry-run defaults, tests enforce bare input) | No merges by agents; no edits to `the_best` |
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
| 2.1 | **SMS codes / phone-required signup** | X signup (often forced for new accounts), IG checkpoints, Gmail signup, Meta developer registration | **No.** Agents can't receive SMS. VoIP numbers (including anything Bland could rent) are rejected by most platforms and cost money. Paid SIMs are forbidden | Avoid SMS everywhere. If a network insists, use **Carlos's existing mobile number once** during the setup sitting (not a new SIM). Then switch 2FA to TOTP-in-1Password and remove the number where the network allows it |
| 2.2 | **Authenticator-app 2FA** | Carlos's own accounts (Supabase, Vercel, GCP, Cloudflare, LinkedIn) whose secret sits on his phone | **Only if the secret is in 1Password.** For accounts we create, it is. For Carlos's existing accounts it isn't, so every expired session means pinging him | New accounts: always TOTP, secret stored in 1Password at setup. Carlos's tools: **delegate, don't impersonate** (invite a member, scoped token or service account) instead of CoS logging in as Carlos |
| 2.3 | **CAPTCHA, "press and hold", selfie video checks, passkeys** | Every signup (Outlook, TikTok, IG, X), sometimes the first login from a new IP | **No, and we won't try.** Defeating captchas breaks the platforms' terms and is unreliable | Batch every signup into the one sitting. CoS drives; Carlos only does the human check |
| 2.4 | **Datacenter IP** | The box is a cloud machine. New accounts created from datacenter IPs get more phone demands and checkpoints, and possibly less reach | Partly | One stable box session per account. No VPN hopping, no second account on the same network, human-paced activity. Residual risk accepted for a 20-day trial |
| 2.5 | **Platform automation rules** | **X:** "non-API-based forms of automation, such as scripting the X website" can lead to permanent suspension. **LinkedIn** User Agreement 8.2: no "bots or other unauthorized automated methods to … create, comment on, like, share, or re-share posts". **TikTok / Meta:** automated access without permission is not allowed | Technically yes; contractually no | Computer Use is fine for one-time setup actions a human would do (create account, set bio, connect Buffer). **Recurring posting goes only through an authorized API integration (Buffer).** On LinkedIn this also protects Carlos's personal profile |
| 2.6 | **Cloud Agent environment secrets** | Pulse needs `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` in the Cursor Cloud Agent environment | CoS can't set them from chat. Computer Use *could* copy them through Carlos's cursor.com session, but that pushes a service key through screenshots | Carlos pastes them in Cursor Dashboard → Cloud Agents → Secrets, once (section 6) |
| 2.7 | **Developer API ownership** | X developer console (now pay-per-use: $0.015 per post, $0.20 with a link; [pricing](https://docs.x.com/x-api/getting-started/pricing)); LinkedIn Community Management API (registered legal organization, verified business email, privacy policy, screencast; personal emails fail vetting; [LinkedIn](https://learn.microsoft.com/en-us/linkedin/marketing/community-management-app-review)); TikTok Content Posting API (unaudited apps post `SELF_ONLY` to private accounts; [TikTok](https://developers.tiktok.com/doc/content-sharing-guidelines)); Meta developer registration (phone or card on Carlos's Facebook account) | Agents can fill the forms. They can't be the legal or financial owner | **Deferred.** Buffer substitutes for the trial (section 5) |
| 2.8 | **LinkedIn identity** | A Company Page must be administered by a real member profile. A fake "AntiSearch" person profile breaks LinkedIn's terms and gets banned | No | LinkedIn = Carlos's profile as Page admin, permanently. He can add a trusted human as a second admin later |
| 2.9 | **Publish gates (self-imposed, keep them)** | First post of each class; spend; X unhold; `SHIP:` to `the_best` | Not a bug | Carlos + CoS decide. CoS asks once per class, in the CoS thread |

---

## 3. The Galaxy lesson applied to AntiSearch

Galaxy (Ship by Thursday, Sep 15–17) ran the same shape we already have: one
orchestrator, specialist lanes, shared computers with persistent logins, Cursor
agents for code, humans for judgment and hard gates. Our gap isn't bots. It's
that **auth is done lazily, mid-flow**, so every wall becomes an interruption.

Rules we adopt:

1. **Front-load auth in one sitting.** Every captcha, consent screen, OAuth grant
   and phone code happens in a single session: CoS drives, Carlos only clicks the
   human-only steps. After that sitting there should be nothing left that
   needs him except judgment.
2. **Delegate, don't impersonate.** Give the AntiSearch identity its own seat in
   Carlos's tools (Supabase org member, scoped tokens, service accounts) instead of
   CoS logging in as Carlos and hitting his phone-based 2FA every few weeks.
3. **Borrow approvals we don't have.** Buffer already passed the reviews at X,
   LinkedIn, Meta and TikTok. Using it is cheaper than four developer programs
   and a legal entity.
4. **Lanes own the steady state.**
   - Clip: mill runs, clips on the box.
   - GTM: the Buffer queue and schedule.
   - Soul: taste review before anything is queued.
   - Pulse: telemetry, eyes closed until day 21.
   - Operator: account health (expired sessions, checkpoints, token expiry).
   - CoS: orchestration and escalation.
5. **Human only for judgment:** first-of-class yes, spend yes, X unhold, the day-21
   review. Every other blocker goes into **one daily digest** from CoS, never a live
   ping, unless something is on fire (account locked, wrong content live).

---

## 4. Decision: social identity email

**Decision: a new free Outlook.com mailbox as the AntiSearch social identity.**
Candidates, first available wins: `antisearchai@outlook.com`,
`antisearch.ai@outlook.com`, `hello.antisearch@outlook.com`.

| Option (free) | Phone at signup | Agents can run it day to day | Verdict |
| --- | --- | --- | --- |
| **Outlook.com** | Often email-only; Microsoft may still demand a phone depending on its risk check | Yes: box session, password + TOTP in 1Password, recovery to `everfields@hotmail.com` (CoS already reads Hotmail codes) | **Chosen.** Closed loop with no phone. Same ecosystem Carlos already uses |
| Proton Free | From datacenter IPs asks for human verification: captcha, email code or SMS. Email code works | Yes, web only | **Fallback 1** if Outlook forces a phone |
| Gmail | Increasingly forced for new accounts from new devices or datacenter IPs | Yes (the connector may even read it) | **Fallback 2**, only with Carlos's existing number once |
| Tuta Free | No phone, but new accounts can be held for approval, and some networks block the domain | Web only | No |
| Mailbox on antisearch.ai (Zoho free etc.) | n/a | Yes | Not now. Free plans keep changing, and it's more to maintain than we need |

**Can agents own the mailbox day to day? Yes.** Setup:

- Stay-signed-in session in the box browser (Operator re-logs via 1Password if it drops).
- 2FA = "a different authenticator app" TOTP, secret in 1Password. Never Microsoft
  Authenticator push or passwordless-only, because both need a phone.
- Recovery email = `everfields@hotmail.com`. Unusual-sign-in checks then send a code
  there and CoS completes them.
- No phone number on the account.
- Operator signs in at least weekly (Microsoft deletes long-inactive accounts).

Carlos never needs to open it.

**Every social account then uses this mailbox** for login, recovery and email codes.
For 2FA it uses TOTP in 1Password. That turns 2.1 and 2.2 into non-walls for our
own accounts.

**Accounts already on `everfields@hotmail.com`:** keep them working. When it's cheap,
CoS switches the login email to the new mailbox. The email-change flow sends codes
to the old and new inbox, and CoS can read both. Not blocking.

**Optional brand layer:** `social@antisearch.ai` → the Outlook mailbox, via Cloudflare
Email Routing (free, receive-only). The DNS for antisearch.ai is on Cloudflare with no
MX records today, so nothing conflicts. It doesn't touch the website or `the_best`.
This isn't needed for the trial. It becomes useful if we ever apply for LinkedIn's
Community Management API (which requires a business email on our domain). Social
logins stay on the Outlook address, so a DNS change can never lock us out.

**If a network insists on a phone:**
- **X:** most likely.
- **Instagram:** possible at a checkpoint (it may ask for a selfie video instead,
  which only Carlos can do).
- **TikTok:** rarely.
- **LinkedIn:** n/a, it's Carlos's profile.

Minimal touch: Carlos types his **existing** mobile number and the code during the
setup sitting. Then CoS switches that account's 2FA to TOTP-in-1Password and removes
the number where the network allows it. No new SIM, ever.

---

## 5. Decision: Computer Use vs mill API, per network

The question was whether the browser can carry the 20-day trial, so we don't need
X / LinkedIn API keys. **Technically, yes.** ≤2 posts/day is trivial for Computer
Use. **Contractually, no:** scripted posting breaks X's and LinkedIn's rules
(2.5), and TikTok's and Meta's. Checkpoints also make it fragile. A $0 authorized
path exists, so we take it:

- **Account creation:** Computer Use, in the setup sitting.
- **Posting:** Buffer (free), fed with mill clips.
- **Mill's own API adapters:** dormant until after the trial.

**Answer: no API keys for the trial.**

| Network (vertical) | (a) Account creation | (b) Posting during the trial | Mill native API (post-trial) | Ask for keys now? |
| --- | --- | --- | --- | --- |
| **TikTok** (beauty/hair/skin) | Computer Use on tiktok.com with the AntiSearch mailbox. Captcha → Carlos in the sitting. Then switch to a **Business account** (free, in settings) so Buffer can auto-publish | **Buffer** TikTok channel | Weak: unaudited apps post private-only, and the audit needs a production-grade app. Keep the stub | **No** |
| **Instagram** (places) | Computer Use on instagram.com with the AntiSearch mailbox. Captcha/checkpoint → Carlos. Switch to **Creator or Business** (free) so Reels auto-publish from Buffer | **Buffer** IG channel (Reels) | Viable later: Instagram Login, Standard Access, no App Review for our own account ([Meta](https://developers.facebook.com/docs/instagram-platform/app-review/)). Needs Meta developer registration (phone/card on Carlos's Facebook) and a public video URL | **No** |
| **LinkedIn** (employers / Company Page) | The Page is created **from Carlos's profile**: CoS does it in his box session under his standing permission, or Carlos does it himself | **Buffer** LinkedIn Page channel. Carlos's profile authorizes Buffer once (OAuth, revocable from his LinkedIn settings). This is an authorized integration, so his profile isn't at risk | Heavy: Community Management API needs a legal entity, a domain business email, a privacy policy and a screencast review. The mill adapter stays dormant | **No** |
| **X** (companies/SaaS, **held**) | Computer Use in the sitting, to reserve the handle and set the bio. Expect a phone demand → Carlos's existing number | **None while held.** At unhold: either (i) move one Buffer slot to X (free; lifetime limit of 8 unique channels per network, so swaps are cheap), or (ii) the mill X adapter with pay-per-use credits: about $0.015 per post (captions carry no link). Carlos must approve that spend and put a card in the X console | Viable, but it's spend. Only if we want X on cron while all 3 free Buffer slots are busy | **No.** Revisit at unhold |

**Why this is enough for unattended operation:**

- **Phase A (trial start).** Clip runs `mill.yml` (or the mill on a Cloud Agent) and
  gets the clips. GTM uploads them into Buffer's web UI with Computer Use. That's
  our own tool; posting then goes out via official APIs. Buffer's free plan keeps
  10 queued posts per channel, so one top-up covers several days. No code, no
  hosting, no keys.
- **Phase B (optional, still $0).** A mill adapter `publish/buffer.py` that posts
  through Buffer's GraphQL API. The API is on every plan, including Free: 1
  personal key, 3,000 requests per 30 days
  ([Buffer](https://support.buffer.com/en-us/articles/using-buffers-api-GtIYIQilz5)).
  It needs a publicly reachable video URL
  ([example](https://developers.buffer.com/examples/create-video-post.html)), so
  clips get a free public bucket: Supabase Storage in a **separate free project**
  (`antisearch-mill`), so the mill never holds the product's keys. Then
  `mill.yml` can run on a schedule with **two secrets** (`BUFFER_API_KEY` + the
  bucket key) instead of eight platform secrets. Dry-run default and
  first-of-class yes stay.
- **Mill's native X/LinkedIn adapters** remain the escape hatch if Buffer changes
  its free plan or a channel falls back to "notification publishing" (which needs
  a phone app). That would be a wall; the fallback for IG is the native Standard
  Access path.

**Buffer caveats (check at connect time, not blocking):**

- A third party holds OAuth tokens for the brand accounts. That's a vendor-trust
  call (see section 8).
- Free-plan terms can change.
- Each channel must show **automatic** publishing, not reminders.
- Posting slots must be set so the **sum across channels is ≤2 per day**.

---

## 6. ONE-SHOT checklist for Carlos

Everything, once. **No spend requested anywhere in this list.**

"CoS alone" means CoS does it without Carlos. "Carlos once" means only Carlos can
do it, one time. "Both" means CoS drives on the box and Carlos does the human-only
step.

| # | Item | Why | Who | Blocker if missing |
| --- | --- | --- | --- | --- |
| 1 | AntiSearch vault in 1Password available on the box; confirm it autofills TOTP codes | Every new credential and 2FA secret lives there, so agents never need Carlos's phone | CoS alone (Carlos once only if the vault doesn't exist yet) | Every future login pings Carlos |
| 2 | **AntiSearch Outlook.com mailbox** (section 4), no phone, TOTP in 1Password, recovery `everfields@hotmail.com` | Social identity that isn't Carlos's personal inbox | Both (CoS; Carlos only for the captcha, or a phone if Microsoft forces one) | Socials stay on Carlos's personal Hotmail |
| 3 | Carlos's **existing** mobile number at hand during the sitting | Only if X/IG insist on a phone (2.1). Removed afterwards where allowed | Carlos once | X handle can't be reserved; an IG checkpoint may stall |
| 4 | **TikTok** account (AntiSearch / AntiSearchAI) → Business account, bio, TOTP | TikTok lane | Both (captcha) | No TikTok lane |
| 5 | **Instagram** account → Creator/Business, bio, TOTP | IG lane | Both (captcha / checkpoint / possible selfie video) | No IG lane |
| 6 | **LinkedIn Company Page** "AntiSearch", admin = Carlos's profile; CoS logged into his LinkedIn on the box | LinkedIn lane; Pages can't exist without a real admin | Both (Carlos's LinkedIn 2FA once; CoS creates the Page under standing permission) | No LinkedIn lane |
| 7 | **X** account reserved (held; bio set, nothing posted) | Keeps the handle for the unhold | Both (captcha + likely phone) | Handle may be taken; nothing else breaks |
| 8 | **Buffer Free** account on the AntiSearch mailbox, TOTP in 1Password | Authorized publishing layer, $0 | CoS alone | No compliant posting path |
| 9 | Connect **TikTok, IG, LinkedIn Page** to Buffer; set automatic publishing; slots ≤2/day total | Posting goes through official APIs | Both (LinkedIn OAuth runs in Carlos's session; captchas) | Posting impossible without scripting the sites |
| 10 | Buffer API key (free, 1 key) → 1Password | Phase B unattended cron | CoS alone | Only Phase B waits |
| 11 | GitHub Actions secrets `BUFFER_API_KEY` + bucket key on `antisearch-automation` | Phase B cron from `mill.yml` | CoS if its GitHub connector has repo admin, else Carlos once | Only Phase B waits |
| 12 | **Supabase (Pulse):** `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` in Cursor Dashboard → Cloud Agents → Secrets | Pulse telemetry, already blocked on this. A read-only Postgres role would be safer than the service key (section 8) | **Carlos once** | Pulse stays blind for the whole trial |
| 13 | Supabase: invite the AntiSearch mailbox into the org (read-only/developer role) | CoS opens the dashboard without Carlos's 2FA (delegate, don't impersonate) | Carlos once (invite); CoS accepts | Every dashboard visit needs Carlos |
| 14 | Supabase: separate free project `antisearch-mill` with a public Storage bucket `clips` | Public video URLs for Phase B; keeps product keys out of the mill | CoS alone (after #13, if the role allows project creation) | Only Phase B waits |
| 15 | **Vercel** | Production antisearch.ai isn't served from Vercel today: it resolves to a Microsoft Azure IP running uvicorn, behind Cloudflare DNS. CoS checks what (if anything) lives on Vercel using the existing box session | CoS alone to check; Carlos once for a scoped token **only if** a lane needs it | None known |
| 16 | **Google Cloud** | Same as Vercel: not in the production request path. CoS checks. If needed: a service account with Viewer role, JSON key into 1Password | CoS alone to check; Carlos once **only if** needed | None known |
| 17 | Cloudflare Email Routing `social@antisearch.ai` → the Outlook mailbox (optional) | Brand contact; future LinkedIn API vetting | Carlos once (or CoS if a Cloudflare member invite / session exists) | None for the trial |
| 18 | Mill platform secrets `X_*`, `LINKEDIN_*`, `TIKTOK_*`, `INSTAGRAM_*` (SETUP.md) | Native API adapters | **Nobody, not now** | None for the trial |
| 19 | CoS can dispatch `mill.yml` and download its artifact through the GitHub connector | Clip handoff without a Cloud Agent in the loop | CoS alone (verify) | Clip lane uses a Cloud Agent run instead |

**Order for the sitting** (CoS drives, Carlos on the box):

1. Outlook mailbox (#2)
2. TikTok and Instagram signups (#4, #5)
3. X reservation (#7; phone if needed, #3)
4. LinkedIn login + Page + Buffer authorization (#6, #9)
5. Buffer: connect TikTok and IG (#9)
6. Supabase invite + Cursor secrets (#12, #13)
7. Cloudflare routing (#17, optional)

Everything else is CoS alone, before or after.

---

## 7. What CoS does next without pinging Carlos (48h after this PR)

Ordered. Anything that hits a wall gets parked for the sitting, not pinged.

**Before the sitting (hours 0–24)**

1. **Inventory accounts.** Which AntiSearch / AntiSearchAI handles already exist on
   TikTok, IG, X and LinkedIn; which email each uses; which sessions are live on
   the box. One table in the CoS thread. Existing accounts get reused, not
   recreated.
2. **Inventory infra, read-only.** Using existing box sessions, confirm what's on
   Vercel, GCP and Supabase (and that production is on Azure behind Cloudflare).
   Drop checklist items #15/#16 if nothing there matters to a lane.
3. **Try the Outlook mailbox alone.** If Microsoft shows only an email path and no
   captcha, finish it, set TOTP in 1Password and add the recovery email. That also
   proves item #1. If it hits a captcha or phone, park it.
4. **Create the Buffer account** once the mailbox exists (email verification only).
5. **Launch a Cloud Agent: trial queue PR** on `antisearch-automation`:
   - `queue/trial_queue.csv` with **one platform per row** following the vertical
     map. The sample queue sends every row to all four networks, which breaks
     "one clip → one network".
   - First posts in the locked order.
   - Captions empty or @handle only.
   - Bare inputs; the existing tests cover every `queue/*.csv` automatically.
6. **Launch a Cloud Agent: Phase B PR** — `publish/buffer.py` (GraphQL, dry-run
   default, refuses fixture-oracle clips like the other adapters) + SETUP
   section. No live use until the sitting and a first-of-class yes.
7. **Produce the first clips** with the live oracle (dry-run `mill.yml` or a
   Cloud Agent `make dry-run`). Soul reviews against the ritual. Keep them on the box.
8. **Send Carlos the checklist once**, with the exact sitting order and only the
   steps that are still open after 1–4.

**After the sitting (hours 24–48)**

9. Set bios ("ai chooses the best. nothing else."), display "antisearch.ai" and
   TOTP on every account. Store every secret in 1Password. Remove Carlos's number
   where allowed.
10. In Buffer: set posting slots so the total is ≤2/day across channels; confirm
    each channel shows automatic publishing.
11. Put the **first post of each class** (TikTok, IG, LinkedIn) into Buffer as a
    draft, not scheduled, and ask for the explicit yes in the CoS thread, one
    message for all three. After a yes, fill that channel's queue (≤10), then top
    up from the mill without asking again.
12. Operator starts the daily health check: sessions, checkpoints, Buffer channel
    status, token expiry. Blockers go into the daily digest.
13. Pulse: if #12 has landed, start collecting; eyes closed until day 21 (no tweaks
    driven by metrics).
14. Low priority: move logins of old accounts from `everfields@hotmail.com` to the
    new mailbox.

---

## 8. Open questions for Carlos (only what we can't decide for you)

1. **Buffer as publishing layer:** OK for a third party (free plan) to hold posting
   access to the brand accounts and to your LinkedIn Page authorization
   (revocable any time)? If no, the trial falls back to native APIs, which need
   the developer and legal steps in 2.7.
2. **Your existing mobile number, once:** OK to use it if X or Instagram insist
   during the sitting, then we move 2FA to 1Password and remove it where allowed?
   If no, X stays unreserved.
3. **Legal entity:** is there a registered company behind AntiSearch/everfields?
   It decides whether LinkedIn's Community Management API and Meta organization
   verification are ever possible after the trial. It doesn't affect the trial.
4. **X at unhold:** swap a free Buffer slot to X ($0; one of TikTok/IG/LinkedIn
   pauses), or approve X API pay-per-use (about $0.015 per post, card in the X
   console) so all four run at once?
5. **Pulse key:** paste the Supabase service key as asked before (fastest; it can
   read and write everything), or create a read-only Postgres role for Pulse
   (safer, a few more clicks for you)?
