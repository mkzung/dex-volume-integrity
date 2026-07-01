"""verify.py - re-derive and assert every headline number in the post from the data
files. Default mode is offline and deterministic (safe for CI): it checks internal
consistency of data/report.json against data/scores.jsonl and data/flagged_detail.jsonl.
`--live` additionally re-pulls DexScreener for the six corroborated pools to confirm
they are still trading above the corroboration threshold.

Run:  python3 verify.py        # offline, no network
      python3 verify.py --live # + re-check DexScreener volumes
Exit code is non-zero if any assertion fails."""
import json, os, sys, subprocess, collections

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data")
CORROBORATION_MIN = 50000        # DexScreener daily USD volume required to corroborate a flag
FAILS = []; CHECKS = 0

def check(cond, msg):
    global CHECKS
    CHECKS += 1
    if not cond: FAILS.append(msg); print(f"  FAIL: {msg}")

def load(n):
    out = []
    with open(os.path.join(DATA, n)) as f:
        for l in f:
            try: out.append(json.loads(l))
            except Exception: pass
    return out

def latest_detail():
    dd = {}
    for r in load("flagged_detail.jsonl"):
        k = (r["net"], r["addr"]); o = (r.get("ohlcv") or {}).get("active_days", 0)
        if k not in dd or o > (dd[k].get("ohlcv") or {}).get("active_days", 0): dd[k] = r
    return dd

report = json.load(open(os.path.join(DATA, "report.json")))
scores = load("scores.jsonl")
detail = latest_detail()

print("== screen counts ==")
check(report["candidates_screened"] == len(scores),
      f'candidates_screened {report["candidates_screened"]} != scores.jsonl rows {len(scores)}')
flagged_screen = sum(1 for r in scores if r.get("flagged"))
check(report["flagged_by_mechanics"] == flagged_screen,
      f'flagged_by_mechanics {report["flagged_by_mechanics"]} != flagged in scores {flagged_screen}')
sustained = [r for r in detail.values() if (r.get("ohlcv") or {}).get("active_days", 0) >= 7]
check(report["sustained"] == len(sustained), f'sustained {report["sustained"]} != {len(sustained)}')
check(report["corroborated"] == len(report["worst"]), "corroborated count != len(worst)")
print(f"  screened={report['candidates_screened']} flagged={flagged_screen} sustained={len(sustained)} corroborated={report['corroborated']}")

print("== per-pool arithmetic (manuf = fleet_vol_share x ds_daily) ==")
tol = 2  # allow +-2 USD rounding
for w in report["worst"]:
    expect = int(w["fleet_vol_share"] * w["ds_daily"])
    check(abs(expect - w["manuf_verified"]) <= tol,
          f'{w["name"]}: manuf {w["manuf_verified"]} != round(share*ds)={expect}')
    check(w["ds_daily"] >= CORROBORATION_MIN, f'{w["name"]}: ds_daily {w["ds_daily"]} below corroboration min')
    check(w["active_days"] >= 7, f'{w["name"]}: active_days {w["active_days"]} < 7 (not sustained)')
    d = detail.get((w["net"], w["addr"]))
    check(d is not None, f'{w["name"]}: no flagged_detail record')
    if d:
        check(len(d["wallets"]) == w["fleet"], f'{w["name"]}: fleet {w["fleet"]} != wallets {len(d["wallets"])}')
    print(f'  {w["name"][:22]:22} fleet={w["fleet"]:2} share={w["fleet_vol_share"]:.3f} ds=${w["ds_daily"]:,} manuf=${w["manuf_verified"]:,}')

print("== totals ==")
tot = sum(w["manuf_verified"] for w in report["worst"])
check(tot == report["total_corroborated_manuf_per_day"],
      f'sum(worst) {tot} != total {report["total_corroborated_manuf_per_day"]}')
bychain = collections.defaultdict(lambda: [0, 0])
for w in report["worst"]:
    c = bychain[w["net"]]; c[0] += 1; c[1] += w["manuf_verified"]
for net, v in report["by_chain"].items():
    check(v["pools"] == bychain[net][0] and v["manuf_day"] == bychain[net][1],
          f'by_chain[{net}] {v} != recomputed {{pools:{bychain[net][0]},manuf_day:{bychain[net][1]}}}')
print(f'  total=${tot:,}/day across {report["corroborated"]} pools; by_chain checks passed')

print("== phantom exclusions (cross-source rigor) ==")
for e in report["excluded_uncorroborated"]:
    check(e["ds_daily"] < CORROBORATION_MIN, f'{e["name"]}: excluded but ds_daily {e["ds_daily"]} >= min')
    check(e["gt_daily"] > e["ds_daily"], f'{e["name"]}: gt_daily not greater than ds_daily')
    print(f'  excluded {e["name"][:22]:22} GT=${e["gt_daily"]:,} DS=${e["ds_daily"]:,}')
maxphantom = max((e["gt_daily"] for e in report["excluded_uncorroborated"]), default=0)
check(maxphantom > 100_000_000, f'largest phantom {maxphantom} not > $100M (headline claim)')

print("== fleet mechanics (balanced two-sided flow) ==")
for w in report["worst"]:
    d = detail.get((w["net"], w["addr"]))
    if not d: continue
    nb = sum(x[1] for x in d["wallets"]); ns = sum(x[2] for x in d["wallets"])
    bal = min(nb, ns) / max(nb, ns) if max(nb, ns) else 0
    check(d["fleet"] >= 2, f'{w["name"]}: fleet < 2')
    check(bal >= 0.60, f'{w["name"]}: buy/sell balance {bal:.2f} < 0.60')
    # net/gross is only stored by runner.py (not backfill_detail.py); assert it where present.
    if d.get("ng") is not None:
        check(abs(d["ng"]) <= 0.15, f'{w["name"]}: net/gross {d["ng"]} > 0.15')
    print(f'  {w["name"][:22]:22} buys={nb} sells={ns} balance={bal:.3f} net/gross={d.get("ng")}')

# optional: attribution facts, only if attribution.json present (needs Bitquery to regenerate)
apath = os.path.join(DATA, "attribution.json")
if os.path.exists(apath):
    print("== attribution (optional) ==")
    a = json.load(open(apath))
    reuse = a.get("cross", {}).get("wallet_reuse", {})
    check(any(set(t) >= {"BASED", "ARX"} for t in reuse.values()),
          "expected a wallet reused across BASED and ARX")
    print(f'  cross-token wallet reuse: {reuse}')

# post tie-out: the published post must cite numbers consistent with the data
ppath = os.path.join(HERE, "post", "fabricated-dex-volume.md")
if os.path.exists(ppath):
    print("== post tie-out ==")
    txt = open(ppath).read()
    check(f'{report["total_corroborated_manuf_per_day"]:,}' in txt, "post missing corroborated total")
    check(str(report["candidates_screened"]) in txt, "post missing screened count")
    for w in report["worst"]:
        check(f'${w["manuf_verified"]:,}' in txt, f'post missing manuf figure for {w["name"]}')
    maxph = max(e["gt_daily"] for e in report["excluded_uncorroborated"])
    check(f'{maxph:,}' in txt, "post missing largest phantom figure")
    snap = json.load(open(os.path.join(DATA, "dexscreener_snapshot.json")))["pools"]["IN"]
    check("481" in txt, "post missing IN turnover (481x)")
    check(f'{int(round(snap["liq_usd"])):,}' in txt, "post missing IN liquidity")
    check(f'{snap["txns_h24"]:,}' in txt, "post missing IN daily transaction count")
    print("  post cites total, screen counts, all per-pool manuf, phantom, IN turnover/liq/txns")

if "--live" in sys.argv:
    print("== live DexScreener re-check ==")
    DSC = {"base": "base", "bsc": "bsc", "solana": "solana"}
    for w in report["worst"]:
        u = f'https://api.dexscreener.com/latest/dex/pairs/{DSC.get(w["net"], w["net"])}/{w["addr"]}'
        try:
            d = json.loads(subprocess.run(["curl", "-sS", "--max-time", "15", u], capture_output=True, text=True, timeout=18).stdout or "{}")
            v = float(((d.get("pairs") or [{}])[0].get("volume") or {}).get("h24") or 0)
        except Exception:
            v = 0.0
        check(v >= CORROBORATION_MIN, f'{w["name"]}: live ds_daily ${v:,.0f} below corroboration min (pool stopped?)')
        print(f'  {w["name"][:22]:22} live ds_daily=${v:,.0f}')

print(f"\n{CHECKS} checks, {len(FAILS)} failures")
sys.exit(1 if FAILS else 0)
