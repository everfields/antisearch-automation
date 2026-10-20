# TikTok handle audit (English vertical pool)

Audit date: **2026-10-20** (independent profile re-check after PR #63 corrections).

**Tagged coverage:** 53/60 pool lines (frozen oracle fixture `tests/fixtures/tiktok_en_oracle_verdicts_2026-10-20.json`).

Allowlist `verified` mirrors TikTok's page JSON flag. When `verified: false`, tagging requires `official_evidence` (brand site or link-in-bio URL) per `tags.allowlisted()`.

Profile snapshots: `tests/fixtures/tiktok_profile_snapshots_2026-10-20.json` (offline test guard).

## English pool brands with a TikTok tag

| brand | handle | TikTok verified | official_evidence | followers (snapshot) |
|---|---|---|---|---|
| oxo | @oxo_us | True |  | 15100 |
| skinceuticals | @skinceuticals | True |  | 87600 |
| cerave | @cerave | True |  | 2100000 |
| vanicream | @officialvanicream | False | https://www.facebook.com/officialvanicream | 8539 |
| pureology | @pureology | True |  | 70400 |
| k18 | @k18hair | True |  | 289800 |
| bio ionic | @bioionic | True |  | 73500 |
| paula's choice | @paulaschoice | True |  | 190700 |
| essie | @essie | True |  | 232000 |
| rare beauty | @rarebeauty | True |  | 5100000 |
| gillette | @gillette | True |  | 91900 |
| colgate | @colgate | True |  | 1100000 |
| nars | @narscosmetics | True |  | 567300 |
| fenty beauty | @fentybeauty | True |  | 3600000 |
| benefit | @benefitcosmetics | True |  | 768300 |
| the doux | @ilovethedoux | False | https://thedoux.com/ | 121000 |
| ouai | @theouai | True |  | 246200 |
| hero | @herocosmetics | True |  | 422600 |
| milk makeup | @milkmakeup | True |  | 1300000 |
| westman atelier | @westmanatelier | True |  | 119400 |
| kiara sky | @kiaraskynails | False | https://www.kiarasky.com/ | 936900 |
| stila | @stilacosmetics | True |  | 121400 |
| neutrogena | @neutrogena_us | True |  | 306100 |
| salt & stone | @saltandstone | True |  | 69500 |
| rogaine | @rogaineofficial | True |  | 12800 |
| reebok | @reebok | True |  | 214900 |
| patagonia | @patagonia | True |  | 249200 |
| yeti | @yeti | True |  | 797300 |
| optimum nutrition | @optimumnutrition_us | True |  | 81300 |
| skratch labs | @skratchlabs | False | https://www.skratchlabs.com/ | 6828 |
| santa cruz organic | @santacruzorganic | False | https://www.santacruzorganic.com/ | 2608 |
| clif bar | @clifbar | True |  | 61500 |
| ninja | @ninjakitchen | True |  | 2100000 |
| kitchenaid | @kitchenaidusa | True |  | 146400 |
| vitamix | @vitamix | True |  | 17000 |
| natasha denona | @natashadenona | True |  | 665600 |
| summer fridays | @summerfridays | True |  | 868200 |
| origins | @origins | True |  | 43400 |
| vuori | @vuoriclothing | True |  | 647300 |
| spindrift | @drinkspindrift | True |  | 169400 |
| jeni's splendid ice creams | @jenisicecreams | True |  | 236800 |
| breville | @breville | True |  | 23400 |
| blues hog | @blueshognation | False | https://blueshog.com/ | 13400 |
| onyx coffee lab | @onyxcoffeelab | False | https://onyxcoffeelab.com/ | 26600 |

## Pool lines without a tag (7)

| input | verdict | why |
|---|---|---|
| wireless charger | anker maggo 3-in-1 wireless charging station | anker has no verified tiktok handle on the allowlist |
| electric toothbrush | oral-b io series 10 | oral-b has no verified tiktok handle on the allowlist |
| retinol cream | skinbetter science alpharet overnight cream | skinbetter science has no verified tiktok handle on the allowlist |
| tweezers for brows | tweezerman slant tweezer | tweezerman has no verified tiktok handle on the allowlist |
| frozen pizza | roberta’s famous original | verdict not on the tag allowlist |
| louisiana style hot sauce | crystal hot sauce | crystal hot sauce has no verified tiktok handle on the allowlist |
| running shorts | janji 5" afo middle short | janji has no verified tiktok handle on the allowlist |

## Corrections applied (2026-10-20)

- Removed bogus **@oralb** (squatted), **@ankerofficial** and **@tweezerman_us** (TikTok error 10221 / missing).
- Replaced **@narsissist** with **@narscosmetics** (verified NARS Cosmetics).
- Added **@rogaineofficial**, **@officialvanicream** (`official_evidence` for unverified badge).
- Removed unconfirmed **@crystal.hot.sauce**, **@runjanji**, **@skinbetterscience**.
- Moved `cosori turboblaze 6-quart` alias from ninja → cosori.

## Concept / Spanish pools

No change: concept verdicts are not taggable brands; Spanish pool not re-audited in this pass.
