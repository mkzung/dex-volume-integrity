"""verify.py - re-derive and assert every published number from the committed data. Offline
and deterministic (safe for CI). The headline is the DIRECT on-chain full-day fabricated volume
(data/onchain_fullday.json, via Bitquery), cross-checked against the DexScreener snapshot; the
screen funnel and the phantom / contract-fleet / window-artifact exclusions come from the
window-based aggregate. `--live` re-pulls DexScreener for the confirmed pools.

Run:  python3 verify.py   |   python3 verify.py --live      (non-zero exit on any failure)"""
import json, os, sys, subprocess, collections

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data")
CORROBORATION_MIN = 50000
FAILS = []; CHECKS = 0

def check(cond, msg):
    global CHECKS
    CHECKS += 1
    if not cond: FAILS.append(msg); print(f"  FAIL: {msg}")

def load(n):
    out = []
    with open(os.path.join(DATA, n)) as f:
        for l in f:
            try: out.append(json.loads(l))
            except Exception: pass
    return out

def jload(n): return json.load(open(os.path.join(DATA, n)))

report = jload("report.json")
scores = load("scores.jsonl")
eoa_raw = jload("eoa_check.json")
eoa_code = {name: {w[0].lower(): w[1] for w in rec.get("wallets", [])} for name, rec in eoa_raw.items()}
snap = jload("dexscreener_snapshot.json")["pools"]
netinv = jload("net_inventory.json")
oc = jload("onchain_fullday.json")

def latest_detail():
    dd = {}
    for r in load("flagged_detail.jsonl"):
        k = (r["net"], r["addr"]); o = (r.get("ohlcv") or {}).get("active_days", 0)
        if k not in dd or o > (dd[k].get("ohlcv") or {}).get("active_days", 0): dd[k] = r
    return dd
detail = latest_detail()

print("== screen funnel ==")
check(report["candidates_screened"] == len(scores), f'screened {report["candidates_screened"]} != scores {len(scores)}')
flagged = sum(1 for r in scores if r.get("flagged"))
check(report["flagged_by_mechanics"] == flagged, f'flagged {report["flagged_by_mechanics"]} != {flagged}')
sustained = [r for r in detail.values() if (r.get("ohlcv") or {}).get("active_days", 0) >= 7]
check(report["sustained"] == len(sustained), f'sustained {report["sustained"]} != {len(sustained)}')
check(report["confirmed"] == len(report["confirmed_onchain"]), "confirmed != len(confirmed_onchain)")
print(f"  screened={report['candidates_screened']} flagged={flagged} sustained={len(sustained)} confirmed(on-chain)={report['confirmed']}")

print("== confirmed on-chain full-day fabricated volume ==")
tok = lambda n: n.split("/")[0].strip()
for c in report["confirmed_onchain"]:
    t = tok(c["name"])
    check(0 < c["fleet_usd_24h"] <= c["total_usd_24h"], f'{t}: fleet_usd not in (0,total]')
    check(abs(c["fleet_share_24h"] - c["fleet_usd_24h"]/c["total_usd_24h"]) < 0.01, f'{t}: share != fleet/total')
    # on-chain total must agree with the independent DexScreener snapshot (within 30%)
    sv = snap[t]["vol_h24"]
    check(abs(c["total_usd_24h"] - sv)/sv < 0.30, f'{t}: on-chain total {c["total_usd_24h"]:,} vs DexScreener {sv:,.0f} >30% apart')
    # on-chain value must match onchain_fullday.json (source of truth)
    check(oc[t]["fleet_usd_24h"] == c["fleet_usd_24h"], f'{t}: report fleet_usd != onchain_fullday')
    print(f'  {t:7} on-chain ${c["fleet_usd_24h"]:,} ({c["fleet_share_24h"]*100:.1f}%) | window said ${c["window_manuf"]:,} | DexScreener total ${sv:,.0f}')
tot = sum(c["fleet_usd_24h"] for c in report["confirmed_onchain"])
check(tot == report["total_confirmed_onchain_per_day"], f'sum {tot} != total {report["total_confirmed_onchain_per_day"]}')
bychain = collections.defaultdict(lambda: [0, 0])
for c in report["confirmed_onchain"]:
    b = bychain[c["net"]]; b[0] += 1; b[1] += c["fleet_usd_24h"]
for net, v in report["by_chain"].items():
    check(v["pools"] == bychain[net][0] and v["fabricated_day"] == bychain[net][1], f'by_chain[{net}] mismatch')
print(f'  total on-chain fabricated ${tot:,}/day across {report["confirmed"]} pools')

print("== net inventory (wash vs market-making: holdings << daily volume) ==")
for c in report["confirmed_onchain"]:
    t = tok(c["name"])
    r = netinv[t]
    check(r["holdings_to_daily_volume"] < 0.02, f'{t}: holdings/volume {r["holdings_to_daily_volume"]} not << 1')
    print(f'  {t:7} holdings ${r["fleet_holdings_usd"]:,.0f} = {r["holdings_to_daily_volume"]*100:.2f}% of daily volume')

print("== exclusion gate 1: phantom volume ==")
for e in report["excluded_uncorroborated"]:
    check(e["ds_daily"] < CORROBORATION_MIN and e["gt_daily"] > e["ds_daily"], f'{e["name"]}: phantom check')
    print(f'  {e["name"][:20]:20} GT ${e["gt_daily"]:,} DS ${e["ds_daily"]:,}')
check(max(e["gt_daily"] for e in report["excluded_uncorroborated"]) > 100_000_000, "largest phantom not > $100M")

print("== exclusion gate 2: contract fleets (eth_getCode) ==")
for e in report["excluded_contract_fleet"]:
    n_eoa = sum(1 for cx in eoa_code.get(e["name"], {}).values() if cx == "EOA")
    check(n_eoa < 2, f'{e["name"]}: excluded as contract but {n_eoa} EOAs')
    print(f'  {e["name"][:20]:20} orig_fleet={e["orig_fleet"]} eoa={e["eoa_wallets"]}')

print("== exclusion gate 3: window artifact (on-chain full-day disproves) ==")
for e in report["excluded_window_artifact"]:
    check(e["onchain_fleet_share_24h"] < 0.05, f'{e["name"]}: window-artifact but on-chain share >= 5%')
    check(e["window_manuf"] > e["onchain_fleet_usd_24h"], f'{e["name"]}: window not greater than on-chain')
    print(f'  {e["name"][:20]:20} window ${e["window_manuf"]:,} -> on-chain ${e["onchain_fleet_usd_24h"]:,} ({e["onchain_fleet_share_24h"]*100:.1f}%)')

print("== fleet mechanics (balanced two-sided flow, from flagged_detail) ==")
for c in report["confirmed_onchain"]:
    d = detail.get((c["net"], c["addr"]))
    if not d: check(False, f'{tok(c["name"])}: no flagged_detail'); continue
    nb = sum(x[1] for x in d["wallets"]); ns = sum(x[2] for x in d["wallets"])
    bal = min(nb, ns)/max(nb, ns) if max(nb, ns) else 0
    check(bal >= 0.60, f'{tok(c["name"])}: balance {bal:.2f} < 0.60')
    print(f'  {tok(c["name"]):7} buys={nb} sells={ns} balance={bal:.3f}')

print("== attribution (optional) ==")
if os.path.exists(os.path.join(DATA, "attribution.json")):
    a = jload("attribution.json")
    check(a.get("cross", {}).get("IN_intersect_ULTIMA") == [], "IN/ULTIMA funding should not converge")
    print(f'  IN_intersect_ULTIMA empty; IN chain top {a["traces"]["IN"]["chain_up_verified"][-1][:14]}...')

print("== post tie-out ==")
ppath = os.path.join(HERE, "post", "index.md")
if os.path.exists(ppath):
    txt = open(ppath).read()
    check(f'{report["total_confirmed_onchain_per_day"]:,}' in txt, "post missing on-chain total")
    check(str(report["candidates_screened"]) in txt, "post missing screened count")
    for c in report["confirmed_onchain"]:
        check(f'${c["fleet_usd_24h"]:,}' in txt, f'post missing on-chain $ for {tok(c["name"])}')
    for e in report["excluded_contract_fleet"] + report["excluded_window_artifact"]:
        check(tok(e["name"]) in txt, f'post missing excluded pool {tok(e["name"])}')
    check(f'{max(e["gt_daily"] for e in report["excluded_uncorroborated"]):,}' in txt, "post missing largest phantom")
    check("481" in txt, "post missing IN turnover")
    check("eth_getCode" in txt or "smart contract" in txt, "post missing contract gate")
    check(("market-making" in txt) or ("market making" in txt), "post missing wash-vs-MM framing")
    print("  post ties: on-chain total, screen counts, per-pool on-chain $, exclusions, phantom, turnover, MM framing")

if "--live" in sys.argv:
    print("== live DexScreener re-check ==")
    DSC = {"base": "base", "bsc": "bsc", "solana": "solana"}
    for c in report["confirmed_onchain"]:
        u = f'https://api.dexscreener.com/latest/dex/pairs/{DSC.get(c["net"], c["net"])}/{c["addr"]}'
        try:
            d = json.loads(subprocess.run(["curl","-sS","--max-time","15",u],capture_output=True,text=True,timeout=18).stdout or "{}")
            v = float(((d.get("pairs") or [{}])[0].get("volume") or {}).get("h24") or 0)
        except Exception: v = 0.0
        check(v >= CORROBORATION_MIN, f'{tok(c["name"])}: live ds ${v:,.0f} below min')
        print(f'  {tok(c["name"]):7} live ds ${v:,.0f}')

print(f"\n{CHECKS} checks, {len(FAILS)} failures")
sys.exit(1 if FAILS else 0)
