import json, subprocess, time, collections, os
HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.path.join(HERE,"data")
def gt(net,addr):
    u=f"https://api.geckoterminal.com/api/v2/networks/{net}/pools/{addr}/trades"
    try: return json.loads(subprocess.run(["curl","-sS","--max-time","20",u],capture_output=True,text=True,timeout=25).stdout or "{}")
    except Exception: return {}
# captured fleets
det={}
for l in open(os.path.join(DATA,'flagged_detail.jsonl')):
    r=json.loads(l); k=(r['net'],r['addr'])
    o=(r.get('ohlcv') or {}).get('active_days',0)
    if k not in det or o>(det[k].get('ohlcv') or {}).get('active_days',0): det[k]=r
flag={('base','0x29183f918920a2aef0115a9c7374945589968aea'):'SOSO',
      ('bsc','0xc4dc171d499b3f5340bffed8433bddcec8d33b04'):'IN',
      ('bsc','0xdc85c2bb53d927006b2db488a0cb4605fca48032'):'ULTIMA'}
samples={}
for (net,addr),name in flag.items():
    fleet=set(w[0].lower() for w in det[(net,addr)]['wallets'])
    d=gt(net,addr); time.sleep(2.5)
    trs=d.get("data") or []
    bycnt=collections.Counter(); sides=collections.defaultdict(lambda:[0,0]); vol=collections.defaultdict(float); hashes=collections.defaultdict(list)
    for t in trs:
        a=t.get("attributes",{}); w=(a.get("tx_from_address") or "").lower()
        if not w: continue
        bycnt[w]+=1; vol[w]+=float(a.get("volume_in_usd") or 0)
        if a.get("kind")=="buy": sides[w][0]+=1
        else: sides[w][1]+=1
        if a.get("tx_hash"): hashes[w].append(a["tx_hash"])
    top=bycnt.most_common(15)
    fleet_in_top=[w for w,_ in top if w in fleet]
    tape_fleet_share=sum(c for w,c in bycnt.items() if w in fleet)/max(1,sum(bycnt.values()))
    print(f"\n== {name} {net} live tape ({len(trs)} trades) ==")
    print(f"  captured-fleet wallets STILL in live top-15: {len(fleet_in_top)}/{min(15,len(fleet))} | fleet share of live tape: {tape_fleet_share:.2f}")
    for w,c in top[:8]:
        b,s=sides[w]; tag="FLEET" if w in fleet else ""
        print(f"    {w} trades={c} b/s={b}/{s} vol=${vol[w]:,.0f} {tag}")
    # sample receipts from fleet wallets
    recs=[]
    for w in fleet:
        if hashes[w]: recs.append((w,hashes[w][0]))
    samples[name]={"net":net,"addr":addr,"live_trades":len(trs),"fleet_in_top":len(fleet_in_top),
                   "live_fleet_share":round(tape_fleet_share,3),"receipts":recs[:5]}
    print("  sample receipts (fleet wallet -> tx_hash):")
    for w,h in recs[:5]: print(f"    {w} {h}")
json.dump(samples, open(os.path.join(DATA,"live_recheck.json"),"w"), indent=1)
print("\nsaved live_recheck.json")
