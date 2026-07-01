"""Capture a dated DexScreener snapshot (volume / liquidity / txns) for the six
corroborated pools, so the post and figures cite a frozen, reproducible number set.
Writes data/dexscreener_snapshot.json. Re-run to refresh."""
import json, os, subprocess, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data")
POOLS = [("base", "0x29183f918920a2aef0115a9c7374945589968aea", "SOSO"),
         ("bsc", "0xc4dc171d499b3f5340bffed8433bddcec8d33b04", "IN"),
         ("bsc", "0xdc85c2bb53d927006b2db488a0cb4605fca48032", "ULTIMA"),
         ("base", "0xdc5a40b5be693afb1864c558da73e7d51b70579e53689cb3a41f85e6cdd6a7f6", "DUAL"),
         ("bsc", "0x07b7556ede0f9a6a7d155a78bc0573f531001a57", "BASED"),
         ("solana", "8erNF5u3CHrqZJXtkfY8CjSxFYF1yqHmN8uDbAhk6tWM", "PYTH")]

def pull(ch, addr):
    u = f"https://api.dexscreener.com/latest/dex/pairs/{ch}/{addr}"
    d = json.loads(subprocess.run(["curl", "-sS", "--max-time", "15", u], capture_output=True, text=True).stdout or "{}")
    p = (d.get("pairs") or [{}])[0]
    if not p: return None
    txn = (p.get("txns") or {}).get("h24", {})
    return dict(symbol=p.get("baseToken", {}).get("symbol"), quote=p.get("quoteToken", {}).get("symbol"),
                dex=p.get("dexId"), vol_h24=float((p.get("volume") or {}).get("h24") or 0),
                liq_usd=float((p.get("liquidity") or {}).get("usd") or 0),
                txns_h24=(txn.get("buys", 0) or 0) + (txn.get("sells", 0) or 0))

snap = {"captured_utc": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "pools": {}}
for ch, addr, name in POOLS:
    r = pull(ch, addr)
    if r:
        r["turnover"] = round(r["vol_h24"] / r["liq_usd"], 1) if r["liq_usd"] else None
        snap["pools"][name] = dict(net=ch, addr=addr, **r)
        print(f'{name:7} {ch:7} vol=${r["vol_h24"]:,.0f} liq=${r["liq_usd"]:,.0f} turnover={r["turnover"]}x txns={r["txns_h24"]}')
json.dump(snap, open(os.path.join(DATA, "dexscreener_snapshot.json"), "w"), indent=1)
print("wrote data/dexscreener_snapshot.json @", snap["captured_utc"])
