"""Capture authoritative evidence for pools flagged in scores.jsonl into flagged_detail.jsonl.
Matches runner.py: OHLCV-anchored manuf_day (fleet volume-share x median measured daily volume),
sustained flag (>=7 active OHLCV days), fleet wallets + per-wallet b/s/vol, sample tx hashes,
60-day OHLCV. Dedupe by (net,addr); safe to re-run."""
import json, subprocess, time, os, collections
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SCORES = os.path.join(DATA, "scores.jsonl")
FLAGDET = os.path.join(DATA, "flagged_detail.jsonl")

def jget(url):
    out = subprocess.run(["curl","-sS","--max-time","15",url], capture_output=True, text=True, timeout=18).stdout
    try: return json.loads(out)
    except Exception: return {}

def detail(net, addr):
    tr = jget(f"https://api.geckoterminal.com/api/v2/networks/{net}/pools/{addr}/trades").get("data", [])
    if not tr: return None
    w = collections.defaultdict(lambda:[0,0,0.0]); tx1={}; bv=sv=0.0
    for t in tr:
        a=t["attributes"]; wal=(a.get("tx_from_address") or "?"); k=a.get("kind"); v=float(a.get("volume_in_usd") or 0)
        if k=="buy": w[wal][0]+=1; bv+=v
        else: w[wal][1]+=1; sv+=v
        w[wal][2]+=v
        if wal not in tx1 and a.get("tx_hash"): tx1[wal]=a["tx_hash"]
    n=len(tr); sample_vol=bv+sv
    flt=[wl for wl,(b,s,vv) in w.items() if min(b,s)>=3 and abs(b-s)<=max(2,0.25*(b+s))]
    fshare=sum((w[wl][0]+w[wl][1]) for wl in flt)/n
    fleet_vol=sum(w[wl][2] for wl in flt)
    fleet_vol_share=fleet_vol/sample_vol if sample_vol else 0.0
    wallets=sorted([[wl,w[wl][0],w[wl][1],int(w[wl][2])] for wl in flt], key=lambda x:-(x[1]+x[2]))[:20]
    txs=[tx1[wl] for wl,_,_,_ in wallets if wl in tx1][:6]
    oh=jget(f"https://api.geckoterminal.com/api/v2/networks/{net}/pools/{addr}/ohlcv/day?aggregate=1&limit=60&currency=usd")
    ol=(((oh.get("data") or {}).get("attributes") or {}).get("ohlcv_list") or [])
    vols=sorted(row[5] for row in ol if len(row)>5 and row[5])
    active=len(vols); median_daily=vols[active//2] if active else 0
    manuf_day=int(fleet_vol_share*median_daily)
    ohlcv=dict(days=len(ol),active_days=active,vol_total=int(sum(vols)),vol_max_day=int(vols[-1]) if vols else 0,median_daily=int(median_daily))
    return dict(fleet=len(flt),fshare=round(fshare,3),fleet_vol_share=round(fleet_vol_share,3),n=n,
                manuf_day=manuf_day,sustained=bool(active>=7),wallets=wallets,sample_txs=txs,ohlcv=ohlcv)

if __name__ == "__main__":
    flagged=[r for r in (json.loads(l) for l in open(SCORES))] if os.path.exists(SCORES) else []
    flagged=[r for r in flagged if r.get("flagged")]
    done=set()
    if os.path.exists(FLAGDET):
        for l in open(FLAGDET):
            try:
                d=json.loads(l)
                if (d.get("ohlcv") or {}).get("active_days",0)>0: done.add((d["net"],d["addr"]))  # retry zero-OHLCV ones
            except Exception: pass
    print(f"flagged: {len(flagged)}; already detailed: {len(done)}")
    seen=set()
    with open(FLAGDET,"a") as g:
        for r in flagged:
            key=(r["net"],r["addr"])
            if key in done or key in seen: continue
            seen.add(key)
            d=detail(r["net"],r["addr"])
            if not d: print(f"  (empty) {r['net']} {r['name'][:18]}"); time.sleep(1.5); continue
            if (d.get("ohlcv") or {}).get("active_days",0)==0:
                print(f"  (no ohlcv yet) {r['net']} {r['name'][:18]}"); time.sleep(1.5); continue
            g.write(json.dumps(dict(net=r["net"],addr=r["addr"],name=r["name"],ts="backfill",**d))+"\n")
            oh=d["ohlcv"]
            print(f"  {r['net']:8} {r['name'][:20]:20} manuf_day=${d['manuf_day']:>11,} active={oh['active_days']}d sustained={d['sustained']} wallets={len(d['wallets'])}")
            time.sleep(2.0)
    print("done")
