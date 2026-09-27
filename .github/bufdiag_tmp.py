import os, json, requests
H={"Authorization":f"Bearer {os.environ['BUFFER_API_KEY']}","Content-Type":"application/json"}
def q(query, variables=None):
    r=requests.post("https://api.buffer.com",json={"query":query,"variables":variables or {}},headers=H,timeout=30)
    b=r.json(); 
    if b.get("errors"): print("  error:", b["errors"][0].get("message")); return None
    return b["data"]
orgs=q("query { account { organizations { id } } }")["account"]["organizations"]
print("orgs:", len(orgs))
for i,o in enumerate(orgs):
    ch=q("query C($org: OrganizationId!) { channels(input: { organizationId: $org }) { id service } }",{"org":o["id"]})["channels"]
    print(f"org[{i}] channels:", sorted(c["service"] for c in ch))
    for label,flt in (("no filter",{}),("status sent",{"status":["sent"]}),("channelIds",{"channelIds":[c["id"] for c in ch]})):
        d=q("""query P($input: PostsInput!) { posts(input: $input, first: 50) { edges { node { status channelService metricsUpdatedAt metrics { type value } externalLink } } pageInfo { hasNextPage } } }""",{"input":{"organizationId":o["id"],"filter":flt}})
        if d is None: continue
        nodes=[e["node"] for e in d["posts"]["edges"] or []]
        by={}
        for n in nodes: by[(n["channelService"],n["status"])]=by.get((n["channelService"],n["status"]),0)+1
        withm=sum(1 for n in nodes if n.get("metricsUpdatedAt")); links=sum(1 for n in nodes if n.get("externalLink"))
        types=sorted({m["type"] for n in nodes for m in (n.get("metrics") or [])})
        print(f"  {label}: {len(nodes)} posts {by} metricsUpdatedAt={withm} externalLink={links} metric types={types}")
