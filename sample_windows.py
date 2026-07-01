"""Multi-window fleet-share robustness: the dollar figures multiply a fleet's share of
a sampled trade window by the pool's daily volume, so the key question is whether that
share is stable across windows. This pulls a fresh GeckoTerminal trade tape for each
confirmed pool, computes the EOA-fleet's share of trade count and of volume, and reports
it next to the earlier captured and live-recheck windows. Writes data/window_robustness.json."""
import json, os, subprocess, time, collections
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data")

def gt(net, addr):
    u = f"https://api.geckoterminal.com/api/v2/networks/{net}/pools/{addr}/trades"
    try: return json.loads(subprocess.run(["curl","-sS","--max-time","20",u],capture_output=True,text=True,timeout=25).stdout or "{}")
    except Exception: return {}

report = json.load(open(os.path.join(DATA, "report.json")))
eoa_raw = json.load(open(os.path.join(DATA, "eoa_check.json")))
eoa_set = {name: {w[0].lower() for w in rec.get("wallets", []) if w[1] == "EOA"} for name, rec in eoa_raw.items()}
det = {}
for l in open(os.path.join(DATA, "flagged_detail.jsonl")):
    r = json.loads(l); k = (r["net"], r["addr"]); o = (r.get("ohlcv") or {}).get("active_days", 0)
    if k not in det or o > (det[k].get("ohlcv") or {}).get("active_days", 0): det[k] = r
live = json.load(open(os.path.join(DATA, "live_recheck.json")))

out = {}
for w in report["worst"]:
    net, addr, name = w["net"], w["addr"], w["name"]
    d = det[(net, addr)]
    fleet = eoa_set.get(name) or {x[0].lower() for x in d["wallets"]}   # EOA fleet (Solana: all)
    d_now = gt(net, addr); time.sleep(2.5)
    trs = d_now.get("data") or []
    cnt = collections.Counter(); vol = collections.defaultdict(float); tot_v = 0.0
    for t in trs:
        a = t.get("attributes", {}); wal = (a.get("tx_from_address") or "").lower()
        v = float(a.get("volume_in_usd") or 0)
        cnt[wal] += 1; vol[wal] += v; tot_v += v
    n = sum(cnt.values())
    now_cnt_share = sum(c for wl, c in cnt.items() if wl in fleet) / n if n else 0
    now_vol_share = sum(vv for wl, vv in vol.items() if wl in fleet) / tot_v if tot_v else 0
    tok = name.split("/")[0].strip()
    lv = live.get(tok, {}).get("live_fleet_share")
    out[tok] = {"net": net, "captured_vol_share": d.get("fleet_vol_share"),
                "captured_cnt_share": d.get("fshare"), "live_cnt_share": lv,
                "now_cnt_share": round(now_cnt_share, 3), "now_vol_share": round(now_vol_share, 3),
                "now_trades": n}
    shares = [s for s in [d.get("fshare"), lv, round(now_cnt_share, 3)] if s is not None]
    out[tok]["cnt_share_min"] = round(min(shares), 3); out[tok]["cnt_share_max"] = round(max(shares), 3)
    print(f"{tok:7} {net:7} count-share  captured={d.get('fshare')} live={lv} now={now_cnt_share:.3f} "
          f"| vol-share captured={d.get('fleet_vol_share')} now={now_vol_share:.3f}  (n={n})")

# conservative floor: lowest observed volume-share per pool x its independent daily volume,
# vs the point estimate in report.json. This bounds the estimate against window variance.
worst = {w["name"].split("/")[0].strip(): w for w in report["worst"]}
floor = 0
for tok, o in out.items():
    vshares = [s for s in [o["captured_vol_share"], o["now_vol_share"]] if s is not None]
    o["vol_share_min"] = round(min(vshares), 3); o["vol_share_max"] = round(max(vshares), 3)
    floor += int(min(vshares) * worst[tok]["ds_daily"])
out["_summary"] = {"point_estimate_per_day": report["total_confirmed_manuf_per_day"],
                   "conservative_floor_per_day": floor,
                   "note": "floor uses each pool's lowest observed volume-share across sampled windows"}
json.dump(out, open(os.path.join(DATA, "window_robustness.json"), "w"), indent=1)
print(f"\nconservative floor ${floor:,}/day  |  point estimate ${report['total_confirmed_manuf_per_day']:,}/day")
print("wrote data/window_robustness.json")
