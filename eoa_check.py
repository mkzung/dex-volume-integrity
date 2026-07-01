"""On-chain sanity check: are the flagged fleet wallets externally-owned accounts
(EOAs) or contracts? A coordinated wash fleet should be EOAs. If a "fleet" wallet
were a router / market-maker / aggregator contract, the balanced two-sided flow
could be an artifact of contract routing rather than deliberate self-trading, so we
verify with eth_getCode against a public RPC per chain (keyless, read-only)."""
import json, os, subprocess, collections
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RPC = {"bsc": "https://bsc-dataseed.binance.org/", "base": "https://mainnet.base.org",
       "eth": "https://eth.llamarpc.com", "arbitrum": "https://arb1.arbitrum.io/rpc"}

def getcode(net, addr):
    if net not in RPC: return "n/a"
    body = json.dumps({"jsonrpc": "2.0", "method": "eth_getCode", "params": [addr, "latest"], "id": 1})
    try:
        out = subprocess.run(["curl", "-sS", "--max-time", "12", "-X", "POST", RPC[net],
                              "-H", "Content-Type: application/json", "-d", body],
                             capture_output=True, text=True, timeout=15).stdout
        r = json.loads(out).get("result", "0x")
    except Exception:
        return "?"
    return "CONTRACT" if (r and r != "0x" and len(r) > 2) else "EOA"

def latest_detail():
    det = {}
    for l in open(os.path.join(DATA, "flagged_detail.jsonl")):
        r = json.loads(l); k = (r["net"], r["addr"]); o = (r.get("ohlcv") or {}).get("active_days", 0)
        if k not in det or o > (det[k].get("ohlcv") or {}).get("active_days", 0): det[k] = r
    return det

if __name__ == "__main__":
    result = {}
    for r in latest_detail().values():
        if r["net"] not in RPC: continue                 # skip Solana (no eth_getCode)
        codes = collections.Counter()
        rows = []
        for wl, b, s, v in r["wallets"][:12]:
            c = getcode(r["net"], wl); codes[c] += 1; rows.append([wl, c])
        result[r["name"]] = {"net": r["net"], "codes": dict(codes), "wallets": rows}
        print(f"{r['name'][:22]:22} {r['net']:5} {dict(codes)}")
    json.dump(result, open(os.path.join(DATA, "eoa_check.json"), "w"), indent=1)
    print("wrote data/eoa_check.json")
