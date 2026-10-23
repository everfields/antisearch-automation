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
