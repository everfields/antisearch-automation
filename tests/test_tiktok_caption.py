from antisearch_mill.publisher.tags import (_entry, caption_variant_of, load_allowlist, tiktok_caption,
                                            tiktok_variant)

ALLOW = load_allowlist("queue/tags/allowlist.json")


def test_format_a_b_and_non_brand():
    assert tiktok_caption("Gentle Face Wash", "Vanicream gentle facial cleanser", "@officialvanicream") == \
        "gentle face wash → vanicream gentle facial cleanser @officialvanicream"
    assert tiktok_caption("gentle face wash", "vanicream", "@officialvanicream", "B") == \
        "gentle face wash @officialvanicream"
    assert tiktok_caption("city to live in at 25", "New York City") == "city to live in at 25 → new york city"
    assert tiktok_caption("city", "nyc", "", "B") == "city → nyc"


def test_variant_alternates_by_brand_post_parity():
    rows = []
    assert tiktok_variant(rows) == "A"
    rows.append({"network": "tiktok", "status": "published", "caption": "x → y @a"})
    rows.append({"network": "tiktok", "status": "published", "caption": "z → w"})
    assert tiktok_variant(rows) == "B"
    rows.append({"network": "tiktok", "status": "published", "caption": "x @b"})
    assert tiktok_variant(rows) == "A"
    assert caption_variant_of("tiktok", "x @b") == "B"
    assert caption_variant_of("tiktok", "x → y @b") == "A"
    assert caption_variant_of("tiktok", "x → y") == ""


def test_fuzzy_brand_matching_on_real_verdicts():
    for verdict, name in [("vanicream gentle facial cleanser", "vanicream"),
                          ("pureology hydrate conditioner", "pureology"),
                          ("skinceuticals retinol 0.3", "skinceuticals"),
                          ("oxo good grips cold brew coffee maker", "oxo")]:
        found = _entry(verdict, ALLOW)
        assert found and found[0] == name, verdict
    assert _entry("new york city", ALLOW) is None or _entry("new york city", ALLOW)[0] != "oxo"
    assert _entry("oxonian tea", {"oxo": {}}) is None


# --- 2026-10-25: Spanish-lane brand verdicts, accents, and no cooldown/cap on the TikTok @ ---
from datetime import datetime, timezone  # noqa: E402

from antisearch_mill.publisher.tags import TagLog, allowlisted, choose_tag  # noqa: E402

ENV = {"PUBLISHER_TAG_NETWORKS": "tiktok"}


def _log(tmp_path, rows):
    log = TagLog(tmp_path / "tags.csv")
    for at, handle in rows:
        log.append(datetime.fromisoformat(at), "tiktok", handle, "j")
    return log


def test_the_three_missed_spanish_brand_posts_now_carry_the_handle(tmp_path):
    # the real tags.csv history: @skinceuticals went out 2026-10-20, inside the old 7-day cooldown
    log = _log(tmp_path, [("2026-10-20T18:39:21-04:00", "@skinceuticals"),
                          ("2026-10-23T10:57:33-04:00", "@gillette"),
                          ("2026-10-23T18:21:50-04:00", "@ilovethedoux")])
    cases = [
        ("videojuego para jugar con amigos", "minecraft", "2026-10-25T20:20:30+00:00", "@minecraft"),
        ("sérum para la cara", "skinceuticals c e ferulic", "2026-10-25T11:24:29+00:00", "@skinceuticals"),
        ("champú para pelo rizado", "kérastase curl manifesto bain hydratation douceur",
         "2026-10-25T19:52:58+00:00", "@kerastase.official"),
    ]
    for category, verdict, at, handle in cases:
        tag = choose_tag(verdict, "tiktok", ENV, ALLOW, log, datetime.fromisoformat(at), 1)
        assert tag.handle == handle, (verdict, tag.reason)
        assert tiktok_caption(category, verdict, tag.handle, "A") == f"{category} → {verdict} {handle}"
        assert tiktok_caption(category, verdict, tag.handle, "B") == f"{category} {handle}"


def test_accent_insensitive_brand_match_both_ways():
    assert _entry("kerastase curl manifesto", ALLOW)[0] == "kérastase"
    assert _entry("kérastase elixir ultime", ALLOW)[0] == "kérastase"
    assert _entry("KÉRASTASE", ALLOW)[0] == "kérastase"
    assert _entry("serum de skincéuticals", ALLOW)[0] == "skinceuticals"


def test_bare_kerastase_handle_is_never_used():
    tag = allowlisted("kérastase", "tiktok", ALLOW, datetime(2026, 10, 25).date())
    assert tag.handle == "@kerastase.official"


def test_tiktok_brand_tag_ignores_cooldown_and_daily_cap(tmp_path):
    now = datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc)
    log = _log(tmp_path, [("2026-10-25T09:00:00+00:00", "@gillette"), ("2026-10-25T10:00:00+00:00", "@cerave")])
    assert choose_tag("gillette sensor3 sensitive", "tiktok", ENV, ALLOW, log, now, 1).handle == "@gillette"
    assert choose_tag("cerave moisturizing cream", "tiktok", ENV, ALLOW, log, now, 0).handle == "@cerave"
    # non-brand verdicts still get no tag
    assert choose_tag("house cat", "tiktok", ENV, ALLOW, log, now, 4).handle == ""
