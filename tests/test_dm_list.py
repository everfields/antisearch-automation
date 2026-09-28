"""The daily DM list: posted verdicts naming an entity with an official, verified account; nothing is sent."""

from datetime import date
from pathlib import Path

from antisearch_mill.publisher.dmlist import Posted, Wikidata, WikidataUnavailable, dm_list, lookup, posted_on
from antisearch_mill.publisher.guard import PostLog, PostRow

DAY = date(2026, 9, 27)


class FakeWikidata(Wikidata):
    """Search hits by name, entities by id, official sites by URL; no network, no pauses."""

    def __init__(self, search: dict, entities: dict, sites: dict | None = None):
        super().__init__(get=lambda *a, **k: None, pause=0, sleep=lambda s: None)
        self.search, self.entities, self.sites = search, entities, sites or {}

    def _json(self, params: dict) -> dict:
        if params["action"] == "wbsearchentities":
            return {"search": self.search.get(params["search"], [])}
        qid = params["ids"]
        return {"entities": {qid: self.entities.get(qid, {})}}

    def site(self, url: str) -> str:
        return self.sites.get(url, "")


def claim(value, rank="normal", ended=False):
    return {"rank": rank, "mainsnak": {"datavalue": {"value": value}}, **({"qualifiers": {"P582": [{}]}} if ended else {})}


def entity(ig=(), x=(), site=(), human=False, article=""):
    claims = {"P2003": [claim(h) for h in ig], "P2002": [claim(h) for h in x], "P856": [claim(u) for u in site]}
    if human:
        claims["P31"] = [claim({"id": "Q5"})]
    return {"claims": claims, "sitelinks": {"enwiki": {"title": article}} if article else {}}


def hit(qid, label, description):
    return [{"id": qid, "label": label, "description": description, "match": {"type": "label", "text": label}}]


WD = FakeWikidata(
    search={
        "rosewood hong kong": hit("Q1", "Rosewood Hong Kong", "Hotel in Tsim Sha Tsui, Hong Kong"),
        "cerave": hit("Q2", "CeraVe", "Dermatology and skin care company"),
        "september": hit("Q3", "September", "Swedish singer"),
        "plénitude": hit("Q4", "Plenitude Arena", "multi-use domed stadium near Paris"),
        "diverxo": hit("Q5", "DiverXO", "restaurant in Spain"),
        "amika": hit("Q6", "amika", "hair care brand"),
    },
    entities={
        "Q1": entity(ig=["rosewoodhongkong"], site=["https://rosewood.example/hk"], article="Rosewood Hong Kong"),
        "Q2": entity(x=["cerave"], site=["https://cerave.example"]),
        "Q3": entity(ig=["petra_marklund"], human=True, article="September (singer)"),
        "Q5": entity(),
        "Q6": entity(ig=["amika"]),
    },
    sites={"https://rosewood.example/hk": '<a href="https://www.instagram.com/rosewoodhongkong/">ig</a>',
           "https://cerave.example": '<a href="https://instagram.com/cerave">ig</a> <a href="https://x.com/cerave">x</a>'
                                     '<a href="https://www.instagram.com/p/abc123/">a post</a>'},
)


def test_an_exact_entity_with_its_official_handle_on_wikidata_and_its_site():
    f, _ = lookup(Posted("rosewood hong kong", "hotel"), WD, {}, {})
    assert (f.instagram, f.x, f.evidence) == ("@rosewoodhongkong", "", "instagram: Wikidata and the official site")


def test_a_product_falls_back_to_its_brand_and_only_the_brands_own_site_counts():
    f, _ = lookup(Posted("cerave moisturizing cream", "moisturizer for dry skin"), WD, {}, {})
    assert (f.instagram, f.x, f.via_brand) == ("@cerave", "@cerave", "CeraVe")  # never the /p/ post link


def test_a_name_that_belongs_to_something_else_is_skipped():
    assert lookup(Posted("september", "a month"), WD, {}, {}) == (None, "")  # the singer is not the month
    assert lookup(Posted("plénitude", "restaurant in paris"), WD, {}, {}) == (None, "")  # the arena is not the restaurant
    assert lookup(Posted("42", "a number"), WD, {}, {}) == (None, "")


def test_an_entity_without_a_checked_handle_is_flagged_not_guessed():
    assert lookup(Posted("diverxo", "restaurant in madrid"), WD, {}, {}) == (None, "DiverXO")


def test_the_human_checked_allowlist_comes_first_and_amika_never():
    allow = {"japan": {"kind": "destination", "instagram": {"handle": "@visitjapan.us", "verified": True,
                                                              "checked": "2026-09-27"}}}
    f, _ = lookup(Posted("japan", "travel"), WD, allow, {})
    assert (f.instagram, f.evidence) == ("@visitjapan.us", "allowlist, checked 2026-09-27")
    assert lookup(Posted("amika", "hair mask"), WD, {}, {}) == (None, "")
    assert lookup(Posted("amika", "hair mask"), WD, {"amika": {"instagram": {"handle": "@amika", "verified": True}}},
                  {}) == (None, "")


def _log(tmp_path) -> PostLog:
    log = PostLog(tmp_path / "state" / "posts.csv")
    rows = [
        ("p-hotel", "instagram", "published", "rosewood hong kong", "hotel", "2026-09-27T19:16:02+00:00", "b1", "", ""),
        ("p-cream", "tiktok", "published", "cerave moisturizing cream", "moisturizer", "2026-09-28T03:19:07+00:00",
         "b2", "", ""),
        ("p-month", "tiktok", "published", "september", "a month", "2026-09-28T00:15:21+00:00", "b3", "", ""),
        ("ig-makeup", "instagram", "scheduled", "diverxo", "restaurant in madrid", "2026-09-28T07:03:23+00:00", "b4",
         "", "2026-09-28T10:37:00+00:00"),
        ("p-gone", "instagram", "deleted", "cerave", "cleanser", "2026-09-27T15:00:00+00:00", "b5", "", ""),
        ("p-next", "instagram", "published", "cerave", "cleanser", "2026-09-28T14:10:00+00:00", "b6", "", ""),
        ("p-x", "x", "published", "rosewood hong kong", "hotel in hong kong", "2026-09-27T20:16:26+00:00", "b7",
         "https://twitter.com/antisearch_ai/status/1", ""),
    ]
    for job, net, status, verdict, cat, at, rid, url, due in rows:
        log.append(PostRow(job, net, "pending", verdict=verdict, category=cat, at=at, due_at=due))
        log.append(PostRow(job, net, status, verdict=verdict, category=cat, at=at, remote_id=rid, url=url, due_at=due))
    return log


def test_the_day_is_the_posting_day_and_a_verdict_is_listed_once(tmp_path):
    posted = {p.verdict: p for p in posted_on(_log(tmp_path), DAY, {"b1": "https://www.instagram.com/reel/R1/"})}
    assert set(posted) == {"rosewood hong kong", "cerave moisturizing cream", "september", "diverxo"}  # not deleted,
    assert posted["rosewood hong kong"].networks == ["instagram", "x"]                                 # not tomorrow
    assert posted["rosewood hong kong"].links == ["instagram: https://www.instagram.com/reel/R1/",
                                                  "x: https://twitter.com/antisearch_ai/status/1"]
    assert posted["diverxo"].links == ["instagram: Buffer b4 (no link yet)"]  # the 06:37 ET schedule is the 27th's


def test_the_list_holds_handles_and_links_and_no_message_text(tmp_path):
    text = dm_list(_log(tmp_path), DAY, WD, {}, {})
    assert "| rosewood hong kong | instagram, x | @rosewoodhongkong | – |" in text
    assert "| cerave moisturizing cream (brand: CeraVe) | tiktok | @cerave | @cerave |" in text
    assert "- diverxo (instagram): DiverXO" in text
    assert "Skipped, not a mentionable entity: september" in text
    assert "congrat" not in text.lower()


def test_wikidata_down_says_so_instead_of_dropping_a_verdict(tmp_path):
    class Down(FakeWikidata):
        def _json(self, params):
            raise WikidataUnavailable("down")

    text = dm_list(_log(tmp_path), DAY, Down({}, {}), {}, {})
    assert "- september (tiktok): not checked: Wikidata unavailable" in text


def test_the_cli_writes_the_day_file_into_publisher_state(tmp_path, monkeypatch):
    from antisearch_mill.cli import main
    import antisearch_mill.publisher.dmlist as dmlist

    log = _log(tmp_path)
    monkeypatch.setattr(dmlist, "Wikidata", lambda: WD)
    assert main(["--env-file", str(tmp_path / "none"), "dm-list", "--state", str(log.path), "--day", "2026-09-27",
                 "--allowlist", str(tmp_path / "none.json"), "--handles", str(tmp_path / "none.json")]) == 0
    out = Path(log.path.parent / "manual" / "dm-list-2026-09-27.md")
    assert out.is_file() and "@rosewoodhongkong" in out.read_text()
