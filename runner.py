"""Scheduled incremental batch (every 30 min). Alternates each run between CRAWL (widen the
multichain pool universe) and SCORE (lockstep-bot wash detection) so a single run never trips
GeckoTerminal's rate limit. Resumable; logs to run.log. Manufactured volume is computed from the
actual trade tape (not GeckoTerminal's unreliable vol_h24). No API keys needed for the screen."""
import json, subprocess, time, os, collections, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)
POOLS = os.path.join(DATA, "pools.jsonl")
SCORES = os.path.join(DATA, "scores.jsonl")
CURSOR = os.path.join(DATA, "run_cursor.json")
LOG = os.path.join(HERE, "run.log")
FLAGDET = os.path.join(DATA, "flagged_detail.jsonl")
CHAINS = ["base", "bsc", "eth", "arbitrum", "solana", "polygon_pos"]
MAXPAGE = 10
SLEEP = 2.5
SCORE_CAP = 10
MAJORS = ("WETH","USDC","USDT","WBNB","CBBTC","CBETH","SOL","DAI","WBTC","VIRTUAL","EURC",
          "BNB","USDE","WEETH","AERO","USDS","USD1","WSOL","JLP","RAY","USDC.E","TBTC","RETH")

def jget(url):
    out = subprocess.run(["curl","-sS","--max-time","12",url], capture_output=True, text=True, timeout=15).stdout
    try: return json.loads(out)
    except Exception: return {}

def log(m):
    line=f"{dt.datetime.utcnow():%Y-%m-%d %H:%M:%S} {m}"; open(LOG,"a").write(line+"\n"); print(line)

def analyze(tr):
    w=collections.defaultdict(lambda:[0,0,0.0]); tx1={}; bv=sv=0.0; times=[]
    for t in tr:
        a=t["attributes"]; wal=(a.get("tx_from_address") or "?"); k=a.get("kind"); v=float(a.get("volume_in_usd") or 0)
        if k=="buy": w[wal][0]+=1; bv+=v
        else: w[wal][1]+=1; sv+=v
        w[wal][2]+=v
        if wal not in tx1 and a.get("tx_hash"): tx1[wal]=a["tx_hash"]
        ts=a.get("block_timestamp")
        if ts: times.append(ts)
    n=len(tr)
    if not n: return None,[],[]
    flt=[wl for wl,(b,s,vv) in w.items() if min(b,s)>=3 and abs(b-s)<=max(2,0.25*(b+s))]
    fshare=sum((w[wl][0]+w[wl][1]) for wl in flt)/n
    fleet_vol=sum(w[wl][2] for wl in flt)
    sample_vol=bv+sv
    fleet_vol_share=fleet_vol/sample_vol if sample_vol else 0.0   # fraction of sampled trade VOLUME that is fleet
    ng=(bv-sv)/sample_vol if sample_vol else 1.0
    top1=(max((w[wl][0]+w[wl][1]) for wl in w))/n
    span_h=0.0
    if len(times)>=2:
        T=sorted(dt.datetime.fromisoformat(x.replace("Z","+00:00")) for x in times)
        span_h=(T[-1]-T[0]).total_seconds()/3600.0
    # NOTE: no /day extrapolation here (the sample window is often seconds-minutes -> meaningless).
    # The authoritative manufactured-$/day is computed in the flag branch as fleet_vol_share * median daily OHLCV.
    core=dict(fleet=len(flt),fshare=round(fshare,3),ng=round(ng,3),n=n,nw=len(w),
              fleet_vol=int(fleet_vol),sample_vol=int(sample_vol),
              fleet_vol_share=round(fleet_vol_share,3),span_h=round(span_h,3),top1=round(top1,3))
    wallets=sorted([[wl,w[wl][0],w[wl][1],int(w[wl][2])] for wl in flt], key=lambda x:-(x[1]+x[2]))[:20]
    txs=[tx1[wl] for wl,_,_,_ in wallets if wl in tx1][:6]
    return core,wallets,txs

cur={"page":1,"mode":"crawl"}
if os.path.exists(CURSOR):
    try: cur=json.load(open(CURSOR))
    except Exception: pass

if cur.get("mode","crawl")=="crawl":
    seen=set()
    if os.path.exists(POOLS):
        for ln in open(POOLS):
            try: r=json.loads(ln); seen.add((r["net"],r["addr"]))
            except Exception: pass
    pg=cur.get("page",1); added=0
    with open(POOLS,"a") as f:
        for net in CHAINS:
            for p in jget(f"https://api.geckoterminal.com/api/v2/networks/{net}/pools?page={pg}").get("data",[]):
                at=p["attributes"]; addr=at.get("address")
                if not addr or (net,addr) in seen: continue
                seen.add((net,addr)); tx=at.get("transactions",{}).get("h24",{})
                f.write(json.dumps(dict(net=net,addr=addr,name=at.get("name","?"),
                    reserve=float(at.get("reserve_in_usd") or 0),vol=float((at.get("volume_usd") or {}).get("h24") or 0),
                    buys=tx.get("buys",0) or 0,sells=tx.get("sells",0) or 0,created=at.get("pool_created_at")))+"\n")
                added+=1
            time.sleep(SLEEP)
    cur={"page":(pg+1 if pg<MAXPAGE else 1),"mode":"score"}
    json.dump(cur,open(CURSOR,"w"))
    log(f"CRAWL p{pg}: +{added} (universe {len(seen)}); next=score")
else:
    done=set()
    if os.path.exists(SCORES):
        for ln in open(SCORES):
            try: d=json.loads(ln); done.add((d["net"],d["addr"]))
            except Exception: pass
    cands=[]
    for ln in open(POOLS):
        r=json.loads(ln)
        if (r["net"],r["addr"]) in done: continue
        res,vol=r["reserve"],r["vol"]; ntx=r["buys"]+r["sells"]; bs=r["name"].split("/")[0].strip().upper()
        turn=vol/res if res>0 else 0
        if bs in MAJORS: continue
        cr=r.get("created")  # require sustained: skip pools < 2 days old (excludes launch-frenzy)
        if cr:
            try:
                if (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(cr.replace("Z","+00:00"))).total_seconds()<2*86400: continue
            except Exception: pass
        if 10000<res<3000000 and turn>=5 and ntx>=300: cands.append((r,turn))
    cands.sort(key=lambda x:-x[1])
    scored=flagged=0
    with open(SCORES,"a") as f:
        for r,turn in cands[:SCORE_CAP]:
            tr=jget(f"https://api.geckoterminal.com/api/v2/networks/{r['net']}/pools/{r['addr']}/trades").get("data",[])
            if not tr: time.sleep(SLEEP); continue
            a,wallets,txs=analyze(tr)
            if not a: time.sleep(SLEEP); continue
            fl=bool(a["fleet"]>=2 and a["fshare"]>=0.5 and abs(a["ng"])<=0.15 and a["n"]>=50)
            f.write(json.dumps(dict(net=r["net"],addr=r["addr"],name=r["name"],reserve=int(r["reserve"]),
                vol_gt=int(r["vol"]),turn=round(turn,1),flagged=fl,
                ts=dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),**a))+"\n")
            scored+=1; flagged+=int(fl)
            if fl:
                ol=[]
                for _try in range(2):  # retry once if OHLCV throttled
                    oh=jget(f"https://api.geckoterminal.com/api/v2/networks/{r['net']}/pools/{r['addr']}/ohlcv/day?aggregate=1&limit=60&currency=usd")
                    ol=(((oh.get("data") or {}).get("attributes") or {}).get("ohlcv_list") or [])
                    if ol: break
                    time.sleep(SLEEP)
                vols=sorted(row[5] for row in ol if len(row)>5 and row[5])
                active=len(vols)
                if active>0:   # only record a flag backed by real OHLCV (else leave it for backfill retry)
                    median_daily=vols[active//2]
                    manuf_day=int(a["fleet_vol_share"]*median_daily)   # authoritative: vol-share x measured median daily volume
                    ohlcv=dict(days=len(ol),active_days=active,vol_total=int(sum(vols)),
                               vol_max_day=int(vols[-1]),median_daily=int(median_daily))
                    with open(FLAGDET,"a") as g:
                        g.write(json.dumps(dict(net=r["net"],addr=r["addr"],name=r["name"],
                            ts=dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),manuf_day=manuf_day,
                            sustained=bool(active>=7),fleet=a["fleet"],fshare=a["fshare"],
                            fleet_vol_share=a["fleet_vol_share"],ng=a["ng"],n=a["n"],span_h=a["span_h"],
                            wallets=wallets,sample_txs=txs,ohlcv=ohlcv))+"\n")
                time.sleep(SLEEP)
            time.sleep(SLEEP)
    cur={"page":cur.get("page",1),"mode":"crawl"}
    json.dump(cur,open(CURSOR,"w"))
    log(f"SCORE: {scored} pools (+{flagged} flagged), {len(cands)} in queue; next=crawl")
