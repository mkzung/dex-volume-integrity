"""Capture the ULTIMA funding-relay cadence as committed evidence, so the post's claim
(each hop ~0.052 BNB to one next wallet, ~8-minute cadence, small fixed decrement) is backed
by a data file. Pulls the earliest inbound native transfers to one relay wallet and records the
amounts, timestamps, gaps, and the single funder. Writes data/ultima_relay.json."""
import json, os, subprocess, time, datetime as dt
from lib_secrets import BITQUERY_TOKEN
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data")
WALLET = "0x0efcd1f41d44fe68f7f83355cf041e705d4fa99d"   # a relay node in the ULTIMA fleet chain

def bq(q):
    for a in range(4):
        out = subprocess.run(["curl","-sS","--max-time","25","-X","POST","https://streaming.bitquery.io/graphql",
            "-H","Content-Type: application/json","-H",f"Authorization: Bearer {BITQUERY_TOKEN}",
            "-d",json.dumps({"query":q})],capture_output=True,text=True,timeout=30).stdout
        try:
            d = json.loads(out)
            if d.get("data") is not None: return d
        except Exception: pass
        time.sleep(1.5*(a+1))
    return {}

q = ('{ EVM(network: bsc){ Transfers(where:{Transfer:{Receiver:{is:"%s"},Currency:{Native:true},Amount:{gt:"0"}}},'
     'orderBy:{ascending:Block_Time},limit:{count:8}){ Block{Time} Transfer{Sender Amount} } } }') % WALLET
trs = (((bq(q).get("data") or {}).get("EVM") or {}).get("Transfers") or [])
hops = [{"time": t["Block"]["Time"], "amount": float(t["Transfer"]["Amount"]), "sender": t["Transfer"]["Sender"].lower()} for t in trs]
amts = [h["amount"] for h in hops]
times = [dt.datetime.fromisoformat(h["time"].replace("Z", "+00:00")) for h in hops]
gaps = [round((times[i+1]-times[i]).total_seconds()/60, 1) for i in range(len(times)-1)] if len(times) > 1 else []
senders = sorted(set(h["sender"] for h in hops))
out = {"wallet": WALLET, "funder": senders[0] if len(senders) == 1 else senders,
       "n_hops": len(hops), "amount_min": round(min(amts), 5) if amts else None,
       "amount_max": round(max(amts), 5) if amts else None,
       "median_gap_min": round(sorted(gaps)[len(gaps)//2], 1) if gaps else None,
       "monotonic_decreasing": all(amts[i] >= amts[i+1] for i in range(len(amts)-1)) if len(amts) > 1 else None,
       "hops": hops}
json.dump(out, open(os.path.join(DATA, "ultima_relay.json"), "w"), indent=1)
print(f"relay {WALLET}: {len(hops)} inbound from {out['funder']}")
print(f"  amounts {out['amount_min']}-{out['amount_max']} BNB, median gap {out['median_gap_min']} min, decreasing={out['monotonic_decreasing']}")
print("wrote data/ultima_relay.json")
