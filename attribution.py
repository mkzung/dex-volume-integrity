"""Funding attribution for the flagged wash fleets (BSC).

The screen (runner.py) proves *mechanics* (balanced lockstep buy/sell fleets that
dominate a pool's tape). This module answers the operator question: who funds the
fleet wallets, and does the funding structure indicate a single coordinated actor?

Method: for each fleet wallet we pull its earliest inbound native (BNB) transfer
(the funder) from Bitquery, then walk that funding edge upward. Two structures are
diagnostic of a single automated operator:
  * PEEL / RELAY CHAIN - wallet A funds B funds C ..., each hop forwarding a fixed
    amount minus a fixed decrement (the forwarding-tx gas) on a fixed time cadence.
    A linear chain (every node sends to exactly one receiver) with a regular cadence
    is an automated gas-distribution pipeline, not organic activity.
  * FAN-OUT HUB - one wallet seeds many fleet wallets directly (a distributor).

We also flag cross-token wallet reuse (the same wallet trading two flagged tokens)
and test whether independent fleets share any funding ancestor (a shared operator).

Requires a Bitquery OAuth token in BITQUERY_TOKEN (see lib_secrets / .secrets.env).
Etherscan does not offer free BSC access, and Bitquery covers native BSC transfers.
Outputs data/attribution.json. Read-only against public chain data."""
import json, os, subprocess, time, collections
from lib_secrets import BITQUERY_TOKEN

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RPC_BSC = "https://bsc-dataseed.binance.org/"

def bq(query):
    """POST a GraphQL query to Bitquery; return parsed JSON ({} on failure)."""
    out = subprocess.run(
        ["curl", "-sS", "--max-time", "20", "-X", "POST", "https://streaming.bitquery.io/graphql",
         "-H", "Content-Type: application/json", "-H", f"Authorization: Bearer {BITQUERY_TOKEN}",
         "-d", json.dumps({"query": query})],
        capture_output=True, text=True, timeout=25).stdout
    try: return json.loads(out)
    except Exception: return {}

def _transfers(where, order="", limit=5):
    q = ('{ EVM(network: bsc){ Transfers(where:{Transfer:{%s Currency:{Native:true},Amount:{gt:"0"}}}%s,limit:{count:%d})'
         '{Block{Time}Transfer{Sender Receiver Amount}} } }') % (where, order, limit)
    return (((bq(q).get("data") or {}).get("EVM") or {}).get("Transfers") or [])

def earliest_funder(addr):
    """The sender of the earliest inbound native transfer to addr (its funder)."""
    tr = _transfers('Receiver:{is:"%s"},' % addr, order=",orderBy:{ascending:Block_Time}", limit=1)
    return tr[0]["Transfer"]["Sender"].lower() if tr else None

def outbound(addr, limit=200):
    """Distinct receivers and tx count of native transfers sent by addr.
    breadth==1 -> relay; breadth>=4 -> fan-out hub."""
    tr = _transfers('Sender:{is:"%s"},' % addr, limit=limit)
    recv = collections.Counter(t["Transfer"]["Receiver"].lower() for t in tr)
    return recv, len(tr)

def getcode(addr):
    """eth_getCode via a public RPC: EOA (no code) vs CONTRACT (router/MM/token)."""
    body = json.dumps({"jsonrpc": "2.0", "method": "eth_getCode", "params": [addr, "latest"], "id": 1})
    out = subprocess.run(["curl", "-sS", "--max-time", "12", "-X", "POST", RPC_BSC,
                          "-H", "Content-Type: application/json", "-d", body],
                         capture_output=True, text=True, timeout=15).stdout
    try: r = json.loads(out).get("result", "0x")
    except Exception: r = "0x"
    return "CONTRACT" if (r and r != "0x" and len(r) > 2) else "EOA"

def follow_chain(start, max_hops=12):
    """Walk the funding edge upward from `start` until a fan-out hub (breadth>=4)
    or the top of the chain. Returns the ordered path of (addr, out_tx, breadth)."""
    path, cur, seen = [], start, set()
    for _ in range(max_hops):
        if not cur or cur in seen: break
        seen.add(cur)
        recv, ntx = outbound(cur); time.sleep(0.4)
        path.append((cur, ntx, len(recv)))
        if len(recv) >= 4: break            # distributor / hub
        cur = earliest_funder(cur); time.sleep(0.4)
    return path

def load_bsc_fleets():
    """token -> set(fleet wallets) for every BSC pool in flagged_detail.jsonl."""
    det = {}
    for l in open(os.path.join(DATA, "flagged_detail.jsonl")):
        r = json.loads(l)
        if r["net"] != "bsc": continue
        k = (r["net"], r["addr"]); o = (r.get("ohlcv") or {}).get("active_days", 0)
        if k not in det or o > (det[k].get("ohlcv") or {}).get("active_days", 0): det[k] = r
    fleets = collections.defaultdict(set)
    for r in det.values():
        tok = r["name"].split("/")[0].strip()
        for w in r["wallets"]: fleets[tok].add(w[0].lower())
    return fleets

def main():
    fleets = load_bsc_fleets()
    out = {"fleets": {k: sorted(v) for k, v in fleets.items()}, "traces": {}, "cross": {}}

    # 1) cross-token wallet reuse (same wallet in >1 flagged token fleet) - offline
    w2t = collections.defaultdict(set)
    for tok, ws in fleets.items():
        for w in ws: w2t[w].add(tok)
    out["cross"]["wallet_reuse"] = {w: sorted(t) for w, t in w2t.items() if len(t) > 1}

    # 2) ULTIMA - trace the fleet's internal funding chain
    ultima = sorted(fleets.get("ULTIMA", []))
    if ultima:
        w0 = ultima[0]
        out["traces"]["ULTIMA"] = {
            "fleet_size": len(ultima),
            "sample_funder": earliest_funder(w0),
            "chain_from_last_relay": follow_chain(ultima[-1])}
        time.sleep(0.4)

    # 3) IN - trace each fleet wallet's funder + follow up
    infleet = sorted(fleets.get("IN", []))
    if infleet:
        funders = {}
        for w in infleet:
            funders[w] = earliest_funder(w); time.sleep(0.4)
        chain = []
        for f in set(v for v in funders.values() if v):
            chain += [x[0] for x in follow_chain(f)]
        out["traces"]["IN"] = {"funders": funders, "chain_up": chain}

    # 4) cross-fleet funding convergence (shared operator across tokens?).
    # Cheap test: do the IN funding chain and the ULTIMA wallet+chain set intersect?
    # (The full ancestor-set convergence was run during analysis and was empty; this
    # keeps the committed script fast and rate-limit-safe.)
    U = set(ultima) | ({out["traces"]["ULTIMA"]["sample_funder"]} if ultima else set())
    for hop in out["traces"].get("ULTIMA", {}).get("chain_from_last_relay", []): U.add(hop[0])
    I = set(out["traces"].get("IN", {}).get("chain_up", [])) | set(v for v in out["traces"].get("IN", {}).get("funders", {}).values() if v)
    out["cross"]["IN_intersect_ULTIMA"] = sorted(U & I)

    json.dump(out, open(os.path.join(DATA, "attribution.json"), "w"), indent=1)
    print("wallet reuse across tokens:", out["cross"]["wallet_reuse"])
    print("ULTIMA sample funder:", out["traces"].get("ULTIMA", {}).get("sample_funder"))
    print("IN funders:", out["traces"].get("IN", {}).get("funders"))
    print("IN cap ULTIMA funding ancestors:", out["cross"]["IN_intersect_ULTIMA"])
    print("wrote data/attribution.json")

if __name__ == "__main__":
    main()
