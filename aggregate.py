"""Aggregate - VERIFIED / cross-sourced.
scores.jsonl = the screen (prevalence among candidates). flagged_detail.jsonl = per-flag evidence
(fleet volume-share, wallets, GeckoTerminal OHLCV). GeckoTerminal volume is UNRELIABLE for these
pools (it reports phantom wash volume, e.g. quq $440M/day that DexScreener shows as $0), so the
headline manufactured-$/day is recomputed on the INDEPENDENT DexScreener daily volume x the fleet's
volume-share, and any sustained flag that DexScreener will not corroborate (no listing / near-zero)
is EXCLUDED. Only sustained (>=7 active OHLCV days) AND corroborated pools reach the headline."""
import json, os, subprocess, collections
HERE = os.path.dirname(os.path.abspath(__file__))
DS_CHAIN = {"base":"base","bsc":"bsc","solana":"solana","eth":"ethereum","arbitrum":"arbitrum","polygon_pos":"polygon"}

def load(n):
    p = os.path.join(HERE, "data", n); out = []
    if os.path.exists(p):
        for l in open(p):
            try: out.append(json.loads(l))
            except Exception: pass
    return out

def jget(u):
    try: return json.loads(subprocess.run(["curl","-sS","--max-time","15",u],capture_output=True,text=True,timeout=18).stdout or "{}")
    except Exception: return {}

sc = {}
for r in sorted(load("scores.jsonl"), key=lambda x: x.get("ts","")):
    sc[(r["net"],r["addr"])] = r
scored = len(sc); flagged_screen = sum(1 for r in sc.values() if r.get("flagged"))

dd = {}
for r in load("flagged_detail.jsonl"):
    k=(r["net"],r["addr"]); cur=dd.get(k)
    if cur is None or (r.get("ohlcv") or {}).get("active_days",0) > (cur.get("ohlcv") or {}).get("active_days",0):
        dd[k]=r
sustained = [r for r in dd.values() if (r.get("ohlcv") or {}).get("active_days",0) >= 7]

verified = []
for r in sustained:
    net,addr = r["net"],r["addr"]
    ds = jget(f"https://api.dexscreener.com/latest/dex/pairs/{DS_CHAIN.get(net,net)}/{addr}")
    dp = ds.get("pairs") or []
    ds_daily = float((dp[0].get("volume") or {}).get("h24") or 0) if dp else 0.0
    gt_daily = (r.get("ohlcv") or {}).get("median_daily",0)
    corrob = ds_daily > 50000  # DexScreener independently shows meaningful volume
    manuf_verified = int(r.get("fleet_vol_share",0) * ds_daily)
    r2 = dict(r, ds_daily=int(ds_daily), gt_daily=int(gt_daily), manuf_verified=manuf_verified, corroborated=corrob)
    verified.append(r2)

corr = [r for r in verified if r["corroborated"]]
total = sum(r["manuf_verified"] for r in corr)
bychain = collections.defaultdict(lambda:[0,0])
for r in corr:
    c=bychain[r["net"]]; c[0]+=1; c[1]+=r["manuf_verified"]

report = dict(candidates_screened=scored, flagged_by_mechanics=flagged_screen,
    sustained=len(sustained), corroborated=len(corr),
    excluded_uncorroborated=[dict(net=r["net"],name=r["name"],gt_daily=r["gt_daily"],ds_daily=r["ds_daily"]) for r in verified if not r["corroborated"]],
    total_corroborated_manuf_per_day=total,
    by_chain={k:dict(pools=v[0],manuf_day=v[1]) for k,v in bychain.items()},
    worst=[dict(net=r["net"],name=r["name"],fleet=r.get("fleet"),fleet_vol_share=r.get("fleet_vol_share"),
               active_days=(r.get("ohlcv") or {}).get("active_days"),ds_daily=r["ds_daily"],
               manuf_verified=r["manuf_verified"],addr=r["addr"]) for r in sorted(corr,key=lambda x:-x["manuf_verified"])])
json.dump(report, open(os.path.join(HERE,"data","report.json"),"w"), indent=1)

print("=== Fabricated DEX volume - VERIFIED (cross-sourced) findings ===")
print(f"candidates screened: {scored} | flagged by mechanics: {flagged_screen}")
print(f"sustained (>=7d): {len(sustained)} | CORROBORATED by DexScreener: {len(corr)}")
print(f"EXCLUDED (GeckoTerminal phantom volume, DexScreener won't corroborate): {len(sustained)-len(corr)}")
for r in verified:
    if not r["corroborated"]:
        print(f"    excluded: {r['net']} {r['name'][:24]} GT_daily=${r['gt_daily']:,} DS_daily=${r['ds_daily']:,}")
print(f"TOTAL corroborated manufactured volume: ${total:,}/day  (fleet vol-share x independent DexScreener daily volume)")
print("worst CORROBORATED offenders:")
for r in sorted(corr, key=lambda x:-x["manuf_verified"]):
    print(f"  {r['net']:8} {r['name'][:22]:22} fleet={r.get('fleet')} vol_share={r.get('fleet_vol_share')} "
          f"active={(r.get('ohlcv') or {}).get('active_days')}d DS_daily=${r['ds_daily']:,} manuf=${r['manuf_verified']:,}  {r['addr']}")
