import datetime, json, time, requests
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
HANDLES = ["amannewyork", "dysonhair", "skinceuticals", "visitjapan.us", "visitjapanus", "nycgo", "yosemitenps", "metmuseum",
           "lebernardinny", "disneyland", "innout", "bluebottle", "lamer", "chanelofficial", "nike", "porsche", "rolex",
           "kingjames", "taylorswift"]
now = datetime.datetime.now(datetime.timezone.utc)
for h in HANDLES:
    r = requests.get("https://www.instagram.com/api/v1/users/web_profile_info/", params={"username": h},
                     headers={"User-Agent": UA, "x-ig-app-id": "936619743392459"}, timeout=20)
    row = {"handle": h, "status": r.status_code}
    try:
        u = r.json()["data"]["user"]
        ts = sorted((e["node"]["taken_at_timestamp"] for e in u["edge_owner_to_timeline_media"]["edges"]), reverse=True)
        last = datetime.datetime.fromtimestamp(ts[0], datetime.timezone.utc) if ts else None
        row.update(full_name=u.get("full_name"), verified=u.get("is_verified"), private=u.get("is_private"),
                   followers=u.get("edge_followed_by", {}).get("count"), last_post=last.isoformat() if last else None,
                   recent_7d=bool(last and now - last <= datetime.timedelta(days=7)),
                   bio=(u.get("biography") or "")[:100].replace("\n", " "), url=u.get("external_url"))
    except Exception:
        row["error"] = r.text[:80]
    print("HANDLE " + json.dumps(row, ensure_ascii=False), flush=True)
    time.sleep(6)
