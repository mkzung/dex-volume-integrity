"""Direct full-day on-chain fabricated volume: for each EVM flagship, sum the USD volume of
ALL pool trades over the last 24h and the USD volume of trades INITIATED BY the fleet wallets,
from Bitquery (independent of GeckoTerminal/DexScreener, and not a sampled window). The fleet's
24h USD volume IS the fabricated volume, measured directly; its share is fleet/total. This
replaces the sampled-window extrapolation. Writes data/onchain_fullday.json."""
import json, os, subprocess, time, datetime as dt
from lib_secrets import BITQUERY_TOKEN
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data")
SINCE = (dt.datetime.utcnow() - dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
POOLS = {"IN": ("bsc", "0xc4dc171d499b3f5340bffed8433bddcec8d33b04"),
         "ULTIMA": ("bsc", "0xdc85c2bb53d927006b2db488a0cb4605fca48032"),
         "SOSO": ("base", "0x29183f918920a2aef0115a9c7374945589968aea")}

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

def usd(net, where):
    q = '{ EVM(network: %s){ DEXTrades(where:{%s Block:{Time:{since:"%s"}}}){ sum(of: Trade_Buy_AmountInUSD) } } }' % (net, where, SINCE)
    d = bq(q); time.sleep(0.6)
    try: return float((((d.get("data") or {}).get("EVM") or {}).get("DEXTrades") or [{}])[0].get("sum") or 0)
    except Exception: return None

eoa_raw = json.load(open(os.path.join(DATA, "eoa_check.json")))
out = {}
for tok, (net, pool) in POOLS.items():
    fleet = [x[0] for x in next(v for k, v in eoa_raw.items() if k.split("/")[0].strip() == tok)["wallets"] if x[1] == "EOA"]
    inlist = "[" + ",".join(f'"{w}"' for w in fleet) + "]"
    total = usd(net, 'Trade:{Dex:{SmartContract:{is:"%s"}}},' % pool)
    fleet_usd = usd(net, 'Transaction:{From:{in:%s}}, Trade:{Dex:{SmartContract:{is:"%s"}}},' % (inlist, pool))
    share = (fleet_usd / total) if total else None
    out[tok] = {"net": net, "total_usd_24h": round(total or 0), "fleet_usd_24h": round(fleet_usd or 0),
                "fleet_share_24h": round(share, 3) if share is not None else None, "fleet_size": len(fleet), "since": SINCE}
    print(f"{tok:7} {net:5} total24h=${(total or 0):,.0f} fleet24h=${(fleet_usd or 0):,.0f} share={share if share is None else round(share,3)}")
json.dump(out, open(os.path.join(DATA, "onchain_fullday.json"), "w"), indent=1)
tot_fab = sum(v["fleet_usd_24h"] for v in out.values())
print(f"\nDirect on-chain fabricated volume (3 EVM pools, 24h): ${tot_fab:,}")
print("wrote data/onchain_fullday.json")
