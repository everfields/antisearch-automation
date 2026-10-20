# TikTok handle audit (English vertical pool)

Audit date: **2026-10-20**. Oracle verdicts frozen in `tests/fixtures/tiktok_en_oracle_verdicts_2026-10-20.json` (live `antisearch.ai/verdict`).

**Tagged coverage:** 56/60 pool posts have an allowlisted TikTok `@handle` for the frozen oracle verdict.

Method: for each brand, try obvious handles (`@brand`, `@brandofficial`, `@brand_us`, …), read the public TikTok profile page JSON (`"verified": true`, `followerCount`), and confirm against the brand site footer/social links when present.

## English pool (`queue/pools/tiktok.txt`)

| brand | handle | evidence (verified flag / site link URL) | followers |
|---|---|---|---|
| belkin | @belkin | tiktok.com/@belkin page JSON `verified: true`, followerCount 205400; belkin.com footer links tiktok.com/@belkin | 205400 |
| anker | @ankerofficial | anker.com footer links tiktok.com/@ankerofficial (Anker Innovations US official) |  |
| oral-b | @oralb | tiktok.com/@oralb: Oral-B official account, verified badge; oralb.com links TikTok |  |
| oxo | @oxo_us | tiktok.com/@oxo_us page JSON verified:true, followerCount 15100, nickname OXO (official US; @oxo is squatted, 29 followers, unverified) | 15100 |
| skinbetter science | @skinbetterscience | tiktok.com/@skinbetterscience nickname skinbetter science, 7968 followers; skinbetter.com has no TikTok footer link; @skinbetter_sci 404. No TikTok verified badge on page. | 7968 |
| skinceuticals | @skinceuticals | tiktok.com/@skinceuticals: SkinCeuticals official L'Oréal brand account, verified badge |  |
| cerave | @cerave | tiktok.com/@cerave is CeraVe's official L'Oréal US skincare account (verified badge); cerave.com social footer links TikTok |  |
| pureology | @pureology | tiktok.com/@pureology verified:true, 70400 followers | 70400 |
| k18 | @k18hair | tiktok.com/@k18hair profile data: uniqueId k18hair, nickname K18 Hair, verified true (fetched 2026-09-27); k18hair.com TikTok contest rules name @k18hair as the brand account |  |
| bio ionic | @bioionic | tiktok.com/@bioionic verified:true, 73500 followers | 73500 |
| paula's choice | @paulaschoice | tiktok.com/@paulaschoice verified:true, 190700 followers | 190700 |
| essie | @essie | tiktok.com/@essie verified:true, 231900 followers | 231900 |
| rare beauty | @rarebeauty | tiktok.com/@rarebeauty: Rare Beauty official account, verified badge, linked from rarebeauty.com |  |
| gillette | @gillette | tiktok.com/@gillette verified:true, 91900 followers | 91900 |
| colgate | @colgate | colgate.com footer links tiktok.com/@colgate (Colgate-Palmolive US official) |  |
| nars | @narsissist | tiktok.com/@narsissist: NARS Cosmetics official account (narsissist), verified badge; narscosmetics.com social links |  |
| fenty beauty | @fentybeauty | fentybeauty.com footer links tiktok.com/@fentybeauty as the official Fenty Beauty account |  |
| benefit | @benefitcosmetics | benefitcosmetics.com links tiktok.com/@benefitcosmetics (Benefit Cosmetics official) |  |
| the doux | @ilovethedoux | thedoux.com footer links tiktok.com/@ilovethedoux (The Doux US official) |  |
| ouai | @theouai | tiktok.com/@theouai: OUAI Haircare official account, verified badge; theouai.com links TikTok |  |
| hero | @herocosmetics | herocosmetics.us footer links tiktok.com/@herocosmetics (Hero Cosmetics official) |  |
| tweezerman | @tweezerman_us | tweezerman.com links tiktok.com/@tweezerman_us (Tweezerman US official) |  |
| milk makeup | @milkmakeup | milkmakeup.com footer links tiktok.com/@milkmakeup |  |
| westman atelier | @westmanatelier | tiktok.com/@westmanatelier verified:true, 119500 followers | 119500 |
| kiara sky | @kiaraskynails | kiarasky.com links tiktok.com/@kiaraskynails; page JSON verified:false but 936900 followers, nickname Kiara Sky Professional Nails (official per brand site) | 936900 |
| stila | @stilacosmetics | tiktok.com/@stilacosmetics verified:true, 121400 followers | 121400 |
| neutrogena | @neutrogena_us | tiktok.com/@neutrogena_us verified:true, 306100 followers, nickname Neutrogena (@neutrogena squatted) | 306100 |
| salt & stone | @saltandstone | tiktok.com/@saltandstone verified:true, 69400 followers | 69400 |
| reebok | @reebok | tiktok.com/@reebok verified:true, 214900 followers | 214900 |
| patagonia | @patagonia | tiktok.com/@patagonia verified:true, 249100 followers | 249100 |
| yeti | @yeti | tiktok.com/@yeti verified:true, 797300 followers | 797300 |
| optimum nutrition | @optimumnutrition_us | tiktok.com/@optimumnutrition_us verified:true, 81300 followers (US; optimumnutrition.com lists @optimumnutrition_ie for IE only) | 81300 |
| skratch labs | @skratchlabs | skratchlabs.com links tiktok.com/@skratchlabs; page JSON verified:false, 6828 followers, nickname Skratch Labs | 6828 |
| santa cruz organic | @santacruzorganic | santacruzorganic.com links tiktok.com/@santacruzorganic; page JSON verified:false, 2608 followers | 2608 |
| clif bar | @clifbar | clifbar.com social links include tiktok.com/@clifbar (Clif Bar & Company US official) |  |
| ninja | @ninjakitchen | tiktok.com/@ninjakitchen verified:true, 2.1M followers; cosori.com links @cosori_official (verified, 227900) — pool air fryer verdict is Ninja Foodi, tagged via SharkNinja @ninjakitchen |  |
| kitchenaid | @kitchenaidusa | tiktok.com/@kitchenaidusa verified:true, 146400 followers (@kitchenaid squatted) | 146400 |
| vitamix | @vitamix | tiktok.com/@vitamix verified:true, 17000 followers | 17000 |
| natasha denona | @natashadenona | tiktok.com/@natashadenona verified:true, 665600 followers | 665600 |
| summer fridays | @summerfridays | tiktok.com/@summerfridays verified:true, 868600 followers | 868600 |
| origins | @origins | tiktok.com/@origins verified:true, 43400 followers, nickname Origins Skincare | 43400 |
| vuori | @vuoriclothing | vuoriclothing.com links tiktok.com/@vuoriclothing; verified:true, 647300 followers | 647300 |
| spindrift | @drinkspindrift | drinkspindrift.com links tiktok.com/@drinkspindrift; verified:true, 169400 followers | 169400 |
| crystal hot sauce | @crystal.hot.sauce | tiktok.com/@crystal.hot.sauce nickname Crystal Hot Sauce, 1329 followers (matches brand; crystalhotsauce.com lists FB/IG/YT only, no TikTok link; @crystalhotsauce squatted) | 1329 |
| jeni's splendid ice creams | @jenisicecreams | jenis.com links tiktok.com/@jenisicecreams; verified:true, 236700 followers | 236700 |
| breville | @breville | tiktok.com/@breville verified:true, 23400 followers | 23400 |
| janji | @runjanji | janji.com footer links instagram.com/runjanji; tiktok.com/@runjanji nickname Janji, 786 followers (no TikTok link on site; matched IG handle pattern) | 786 |
| blues hog | @blueshognation | blueshog.com links tiktok.com/@blueshognation; verified:false, 13400 followers, nickname Blues Hog | 13400 |
| onyx coffee lab | @onyxcoffeelab | onyxcoffeelab.com links tiktok.com/@onyxcoffeelab; verified:false, 26600 followers | 26600 |

## Brands without a TikTok handle

### Vanicream
Pool lines: `gentle face wash`, `body wash sensitive skin`.

Checked:
- `tiktok.com/@vanicream` — page JSON `verified: false`, ~4 followers.
- `tiktok.com/@vanicreamskincare` — no user block (404).
- `pharmaceuticalspecialties.com`, `vanicream.org` — no TikTok URL in homepage HTML.

**No official handle added.**

### Rogaine
Pool line: `scalp serum hair growth`.

Checked:
- `tiktok.com/@rogaine` — `verified: false`, ~3 followers.
- `tiktok.com/@rogainehair` — 404.
- `rogaine.com` — no TikTok link in homepage HTML.

**No official handle added.**

### Roberta's Pizza
Pool line: `frozen pizza`.

Checked:
- `tiktok.com/@robertaspizza` — `verified: false`, ~540 followers, nickname "Brandon Hoy" (not clearly corporate).
- `tiktok.com/@robertasbklyn`, `@robertasrestaurant`, `@robertaspizzabrooklyn` — 404.
- `robertaspizza.com`, `shop.robertaspizza.com` — Instagram `@robertaspizza` only; no TikTok.

**No official handle added.**

## Concept pool (`queue/pools/tiktok_concept.txt`)

Verdicts are abstract (places, eras, ideas) — not consumer brands. No handle pass.

## Spanish pool (`queue/pools/tiktok_es.txt`)

Most verdicts are artists/songs/venues. Handle pass deferred except where a future verdict is a taggable US brand.
