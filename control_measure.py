"""Controls: measure liquid, legitimately-traded pools the SAME on-chain way (Bitquery, 24h) to
show the method does not false-positive on organic volume. Key point: high turnover is common on
liquid pools (WETH/USDC, cbBTC/USDC run 7-12x), so turnover is NOT the discriminator; the
discriminator is that a small wallet set holds a large share of volume. For each control we report
24h volume and the share held by its top-10 traders, to contrast with the flagged fleets. Writes
data/controls.json."""
import json, os, subprocess, time, datetime as dt
from lib_secrets import BITQUERY_TOKEN
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data")
SINCE = (dt.datetime.utcnow() - dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
CONTROLS = {"WETH/USDC (Base)": ("base", "0x72ab388e2e2f6facef59e3c3fa2c4e29011c2d38"),
            "USDT/WBNB (BSC)": ("bsc", "0x172fcd41e0913e95784454622d1c3724f546f849")}

def bq(q):
    for a in range(5):
        out = subprocess.run(["curl","-sS","--max-time","25","-X","POST","https://streaming.bitquery.io/graphql",
            "-H","Content-Type: application/json","-H",f"Authorization: Bearer {BITQUERY_TOKEN}",
            "-d",json.dumps({"query":q})],capture_output=True,text=True,timeout=30).stdout
        try:
            d = json.loads(out)
            if d.get("data") is not None: return d
        except Exception: pass
        time.sleep(1.5*(a+1))
    return {}

def gt_liq_turnover(net, addr):
    u = f"https://api.geckoterminal.com/api/v2/networks/{net}/pools/{addr}"
    try:
        d = json.loads(subprocess.run(["curl","-sS","--max-time","15",u],capture_output=True,text=True,timeout=18).stdout or "{}")
        a = (d.get("data") or {}).get("attributes", {})
        liq = float(a.get("reserve_in_usd") or 0); vol = float((a.get("volume_usd") or {}).get("h24") or 0)
        return round(liq), round(vol/liq, 1) if liq else None
    except Exception:
        return None, None

def total_usd(net, pool):
    q = '{ EVM(network: %s){ DEXTrades(where:{Trade:{Dex:{SmartContract:{is:"%s"}}},Block:{Time:{since:"%s"}}}){ sum(of: Trade_Buy_AmountInUSD) } } }' % (net, pool, SINCE)
    d = bq(q); time.sleep(0.5)
    try: return float((((d.get("data") or {}).get("EVM") or {}).get("DEXTrades") or [{}])[0].get("sum") or 0)
    except Exception: return 0.0

def top_traders(net, pool, n=10):
    q = ('{ EVM(network: %s){ DEXTrades(where:{Trade:{Dex:{SmartContract:{is:"%s"}}},Block:{Time:{since:"%s"}}},'
         'orderBy:{descendingByField:"vol"},limit:{count:%d}){ Transaction{From} vol: sum(of: Trade_Buy_AmountInUSD) } } }') % (net, pool, SINCE, n)
    d = bq(q); time.sleep(0.5)
    tr = (((d.get("data") or {}).get("EVM") or {}).get("DEXTrades") or [])
    return [(t["Transaction"]["From"].lower(), float(t.get("vol") or 0)) for t in tr]

out = {}
for name, (net, pool) in CONTROLS.items():
    tot = 0
    for _try in range(5):                 # base DEXTrades is intermittently empty; retry on zero
        tot = total_usd(net, pool)
        if tot > 0: break
        time.sleep(2)
    top = top_traders(net, pool, 10) if tot > 0 else []
    top1 = top[0][1] if top else 0
    top10 = sum(v for _, v in top)
    liq, turnover = gt_liq_turnover(net, pool); time.sleep(1.0)
    out[name] = {"net": net, "addr": pool, "total_usd_24h": round(tot), "liq_usd": liq, "turnover": turnover,
                 "top1_share": round(top1/tot, 3) if tot else None,
                 "top10_share": round(top10/tot, 3) if tot else None,
                 "top10": [[w, round(v)] for w, v in top]}
    print(f"{name:18} total24h=${tot:,.0f} liq=${liq:,} turnover={turnover}x top1={top1/tot*100:.1f}% top10={top10/tot*100:.1f}%" if tot else f"{name}: no data")
json.dump(out, open(os.path.join(DATA, "controls.json"), "w"), indent=1)
print("\nwrote data/controls.json  (contrast: flagged fleets hold 9-99% of pool volume)")
