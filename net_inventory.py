"""Wash vs market-making: a wash fleet cycles the same small stack of funds and ends near
flat, so its token holdings are tiny relative to the volume it trades. A directional market
maker would hold meaningful inventory. For each EVM flagship, this reads the fleet wallets'
current token balance (eth_call balanceOf) and compares total holdings to the pool's daily
volume. Tiny holdings against large volume is the cycling (wash) signature. data/net_inventory.json."""
import json, os, subprocess, time
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data")
RPC = {"bsc": "https://bsc-dataseed.binance.org/", "base": "https://mainnet.base.org"}

def gt(net, addr):
    u = f"https://api.geckoterminal.com/api/v2/networks/{net}/pools/{addr}"
    try: return json.loads(subprocess.run(["curl","-sS","--max-time","20",u],capture_output=True,text=True,timeout=25).stdout or "{}")
    except Exception: return {}

def rpc(net, to, data):
    body = json.dumps({"jsonrpc":"2.0","method":"eth_call","params":[{"to":to,"data":data},"latest"],"id":1})
    try:
        out = subprocess.run(["curl","-sS","--max-time","12","-X","POST",RPC[net],"-H","Content-Type: application/json","-d",body],
                             capture_output=True,text=True,timeout=15).stdout
        return json.loads(out).get("result","0x")
    except Exception: return "0x"

def hexint(h):
    try: return int(h, 16)
    except Exception: return 0

report = json.load(open(os.path.join(DATA, "report.json")))
eoa_raw = json.load(open(os.path.join(DATA, "eoa_check.json")))
eoa_set = {name: [w[0] for w in rec.get("wallets", []) if w[1] == "EOA"] for name, rec in eoa_raw.items()}

out = {}
for w in report["worst"]:
    net = w["net"]
    if net not in RPC: continue                      # EVM only
    info = gt(net, w["addr"]); time.sleep(2.0)
    at = (info.get("data") or {}).get("attributes", {}); rel = (info.get("data") or {}).get("relationships", {})
    bt = ((rel.get("base_token") or {}).get("data") or {}).get("id", "")   # e.g. "bsc_0xabc..."
    token = bt.split("_")[-1] if "_" in bt else ""
    price = float(at.get("base_token_price_usd") or 0)
    if not token: continue
    dec = hexint(rpc(net, token, "0x313ce567")) or 18; time.sleep(0.2)
    fleet = eoa_set.get(w["name"], [])
    holdings_usd = 0.0; rows = []
    for wl in fleet:
        bal = hexint(rpc(net, token, "0x70a08231" + "0"*24 + wl[2:].lower())); time.sleep(0.2)
        usd = (bal / (10**dec)) * price
        holdings_usd += usd; rows.append([wl, round(usd, 2)])
    tok = w["name"].split("/")[0].strip()
    ratio = holdings_usd / w["ds_daily"] if w["ds_daily"] else 0
    out[tok] = {"net": net, "token": token, "price_usd": price, "fleet_size": len(fleet),
                "fleet_holdings_usd": round(holdings_usd, 2), "daily_volume_usd": w["ds_daily"],
                "holdings_to_daily_volume": round(ratio, 5), "wallets": rows}
    print(f"{tok:7} {net:5} fleet={len(fleet)} holdings=${holdings_usd:,.0f} vs daily vol ${w['ds_daily']:,} -> {ratio*100:.3f}% (holdings/volume)")
json.dump(out, open(os.path.join(DATA, "net_inventory.json"), "w"), indent=1)
print("\nwrote data/net_inventory.json")
