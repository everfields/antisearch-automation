"""TikTok brand guard (2026-10-26): a brand verdict with no allowlisted handle is skipped, never posted untagged."""

from datetime import datetime
from zoneinfo import ZoneInfo

from antisearch_mill.ledger import Job
from antisearch_mill.publisher.brand_guard import brand_reason, load_brands
from antisearch_mill.publisher.tags import allowlisted, load_allowlist
from conftest import ROOT
from test_tags import BUFFER_ENV, ON, _live

ET = ZoneInfo("America/New_York")
ALLOW = load_allowlist(ROOT / "queue" / "tags" / "allowlist.json")
BRANDS = load_brands(ROOT / "queue" / "tags" / "brands.txt")

# Real TikTok verdicts (posts.csv, publisher-state, to 2026-10-25) that are not brands: they must post.
NON_BRAND = [
    "almendras", "house cat", "new york city", "coast redwood", "1990s", "your current age", "omnipotence",
    "bocadillo de jamón ibérico de bellota", "shorts, camiseta y zapatillas cómodas", "conjunto negro monocromático",
    "escapada a la montaña", "cena con amigos", "mallorca", "sips, barcelona", "bar néstor", "warm summer rain",
    "mediterranean sea", "mount everest from gokyo ri", "eggs benedict", "sushi omakase", "deep sleep", "campfire",
    "quevedo: bzrp music sessions, vol. 52", "la tortura — shakira y alejandro sanz", "álbum de fotos familiar personalizado",
    "road trip por los parques nacionales", "a kept promise", "why?", "e", "september", "columbia", "japan", "bali",
]
# Real brand verdicts that went out (or would go out) with no handle.
UNTAGGED_BRANDS = [
    "la roche-posay uvmune 400 invisible fluid spf50+", "medik8 intelligent retinol 10tr", "lancôme lash idôle",
    "oribe gold lust repair & restore conditioner", "ghd chronos", "3m aura 9210+ n95", "bioderma sensibio h2o",
    "henson al13", "mason pearson popular mixture", "latisse", "sk-ii facial treatment mask",
    "st. tropez self tan express bronzing mousse", "mountain valley spring water", "oral-b io series 10",
    "tweezerman slant tweezer", "janji 5\" afo middle short", "roberta’s famous original",
    "anker maggo 3-in-1 wireless charging station",
]


def test_non_brand_verdicts_are_never_flagged():
    for v in NON_BRAND:
        assert brand_reason(v, BRANDS, ALLOW) is None, (v, brand_reason(v, BRANDS, ALLOW))


def test_brand_verdicts_are_flagged_even_off_the_lexicon():
    for v in UNTAGGED_BRANDS:
        assert brand_reason(v, BRANDS, ALLOW), v
    # heuristics alone (no lexicon, no allowlist): model tokens and product nouns
    assert brand_reason("acme ultra glow 2x serum") and brand_reason("glowco spf50+")
    assert brand_reason("marca crema hidratante intensa")
    assert brand_reason("severance") is None and brand_reason("deep focus") is None


def test_the_la_roche_posay_miss_now_tags():
    day = datetime(2026, 10, 26).date()
    tag = allowlisted("la roche-posay anthelios uvmune 400 spf50+", "tiktok", ALLOW, day)
    assert tag.handle == "@larocheposay", tag.reason
    for verdict, handle in [("aquaphor lip repair", "@aquaphor"), ("armani luminous silk foundation", "@armanibeauty"),
                            ("bleu de chanel parfum", "@chanelofficial"), ("laneige cream skin cerapeptide toner", "@laneige_us"),
                            ("l’occitane shea butter hand cream", "@loccitane"), ("dove advanced care", "@dove"),
                            ("clarins lip comfort oil", "@clarinsusa"), ("oribe gold lust repair & restore conditioner", "@oribe")]:
        assert allowlisted(verdict, "tiktok", ALLOW, day).handle == handle, verdict
    assert allowlisted("a white dove", "tiktok", ALLOW, day).handle == ""


def test_live_run_skips_untagged_brand_and_posts_the_next_input(tmp_path):
    now = datetime(2026, 9, 28, 13, 10, tzinfo=ET)
    jobs = [Job("p-mascara", "mascara", ("tiktok",), notes="pool:vertical"),
            Job("p-animal", "animal to be", ("tiktok",), notes="pool:concept")]
    verdicts = {"p-mascara": "lancôme lash idôle", "p-animal": "house cat"}
    out, creates, _log = _live(tmp_path, jobs, {**BUFFER_ENV, **ON}, now, verdicts)
    assert [(o.job_id, o.status) for o in out] == [("p-mascara", "skipped_brand_untagged"), ("p-animal", "published")]
    assert [c["text"] for c in creates] == ["animal to be → house cat"]


def test_live_run_brand_with_handle_still_posts_and_breaker_turns_guard_off(tmp_path):
    now = datetime(2026, 9, 28, 13, 10, tzinfo=ET)
    jobs = [Job("p-mascara", "mascara", ("tiktok",), notes="pool:vertical")]
    out, creates, _ = _live(tmp_path / "a", jobs, {**BUFFER_ENV, **ON, "PUBLISHER_TIKTOK_BRAND_GUARD": "off"}, now,
                            {"p-mascara": "lancôme lash idôle"})
    assert out[0].status == "published" and creates[0]["text"] == "mascara → lancôme lash idôle"
