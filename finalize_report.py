"""Rebuild report.json around the DIRECT on-chain full-day measurement (onchain_fullday.json,
pyth_onchain.json), keeping the screen funnel + the phantom and contract-fleet exclusions from
the window-based aggregate. The window estimate is retained per pool for the self-correction
comparison. PYTH is moved to a window-artifact exclusion (on-chain full-day fleet share ~0.1%).
Deterministic, offline, from committed data."""
import json, os, collections
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data")
rep = json.load(open(os.path.join(DATA, "report.json")))
oc = json.load(open(os.path.join(DATA, "onchain_fullday.json")))
pyth = json.load(open(os.path.join(DATA, "pyth_onchain.json")))
worst = {w["name"].split("/")[0].strip(): w for w in rep["worst"]}

conf = []
for tok, o in oc.items():
    w = worst[tok]
    conf.append(dict(name=w["name"], net=o["net"], addr=w["addr"], fleet=w["fleet"],
                     total_usd_24h=o["total_usd_24h"], fleet_usd_24h=o["fleet_usd_24h"],
                     fleet_share_24h=o["fleet_share_24h"], window_manuf=w["manuf_verified"]))
conf.sort(key=lambda x: -x["fleet_usd_24h"])
total = sum(c["fleet_usd_24h"] for c in conf)
bychain = collections.defaultdict(lambda: [0, 0])
for c in conf:
    b = bychain[c["net"]]; b[0] += 1; b[1] += c["fleet_usd_24h"]

pw = worst["PYTH"]
newrep = dict(
    candidates_screened=rep["candidates_screened"], flagged_by_mechanics=rep["flagged_by_mechanics"],
    sustained=rep["sustained"], confirmed=len(conf),
    excluded_uncorroborated=rep["excluded_uncorroborated"],
    excluded_contract_fleet=rep["excluded_contract_fleet"],
    excluded_window_artifact=[dict(name=pw["name"], net="solana", addr=pw["addr"],
        onchain_fleet_usd_24h=pyth["fleet_pyth_usd_24h"], onchain_fleet_share_24h=pyth["fleet_share_24h"],
        window_manuf=pw["manuf_verified"])],
    total_confirmed_onchain_per_day=total,
    by_chain={k: dict(pools=v[0], fabricated_day=v[1]) for k, v in bychain.items()},
    confirmed_onchain=conf)
json.dump(newrep, open(os.path.join(DATA, "report.json"), "w"), indent=1)
print(f"confirmed on-chain pools: {len(conf)}  total fabricated ${total:,}/day")
for c in conf:
    print(f"  {c['name'][:20]:20} on-chain ${c['fleet_usd_24h']:,} ({c['fleet_share_24h']*100:.1f}%) vs window ${c['window_manuf']:,}")
print(f"window-artifact excluded: PYTH on-chain ${pyth['fleet_pyth_usd_24h']} ({pyth['fleet_share_24h']*100:.1f}%) vs window ${pw['manuf_verified']:,}")
print("wrote data/report.json")
