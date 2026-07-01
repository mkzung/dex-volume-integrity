"""verify.py - re-derive and assert every headline number in the post from the data
files. Default mode is offline and deterministic (safe for CI): it checks internal
consistency of data/report.json against data/scores.jsonl, data/flagged_detail.jsonl,
and data/eoa_check.json. `--live` additionally re-pulls DexScreener for the confirmed
pools to confirm they are still trading above the corroboration threshold.

Two gates reach the headline: (1) an independent DexScreener volume must corroborate the
flag; (2) an eth_getCode check must show the fleet is EOAs (>=2), not router/aggregator
contracts (EVM only; Solana pools rest on mechanics). Run:
    python3 verify.py          # offline, no network
    python3 verify.py --live   # + re-check DexScreener volumes
Exit code is non-zero if any assertion fails."""
import json, os, sys, subprocess, collections

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data")
CORROBORATION_MIN = 50000
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
eoa_raw = json.load(open(os.path.join(DATA, "eoa_check.json")))
eoa_code = {name: {w[0].lower(): w[1] for w in rec.get("wallets", [])} for name, rec in eoa_raw.items()}

print("== screen counts ==")
check(report["candidates_screened"] == len(scores),
      f'candidates_screened {report["candidates_screened"]} != scores rows {len(scores)}')
flagged_screen = sum(1 for r in scores if r.get("flagged"))
check(report["flagged_by_mechanics"] == flagged_screen,
      f'flagged_by_mechanics {report["flagged_by_mechanics"]} != {flagged_screen}')
sustained = [r for r in detail.values() if (r.get("ohlcv") or {}).get("active_days", 0) >= 7]
check(report["sustained"] == len(sustained), f'sustained {report["sustained"]} != {len(sustained)}')
check(report["confirmed"] == len(report["worst"]), "confirmed count != len(worst)")
n_vol = report["confirmed"] + len(report["excluded_contract_fleet"])
check(report["corroborated_by_volume"] == n_vol,
      f'corroborated_by_volume {report["corroborated_by_volume"]} != confirmed+contract_excl {n_vol}')
check(len(sustained) == report["confirmed"] + len(report["excluded_contract_fleet"]) + len(report["excluded_uncorroborated"]),
      "sustained != confirmed + contract-excluded + uncorroborated")
print(f"  screened={report['candidates_screened']} flagged={flagged_screen} sustained={len(sustained)} "
      f"vol-corroborated={n_vol} confirmed={report['confirmed']}")

print("== per-pool arithmetic + EOA gate (manuf = EOA fleet vol-share x ds_daily) ==")
for w in report["worst"]:
    expect = int(w["fleet_vol_share"] * w["ds_daily"])
    check(abs(expect - w["manuf_verified"]) <= 2, f'{w["name"]}: manuf {w["manuf_verified"]} != round(share*ds)={expect}')
    check(w["ds_daily"] >= CORROBORATION_MIN, f'{w["name"]}: ds_daily below corroboration min')
    check(w["active_days"] >= 7, f'{w["name"]}: active_days < 7')
    check(w["eoa_status"] in ("confirmed", "n/a"), f'{w["name"]}: eoa_status {w["eoa_status"]} not confirmed/n-a')
    if w["eoa_status"] == "confirmed":     # EVM: fleet must be >=2 EOAs per eth_getCode
        codes = eoa_code.get(w["name"], {})
        n_eoa = sum(1 for c in codes.values() if c == "EOA")
        check(n_eoa >= 2, f'{w["name"]}: only {n_eoa} EOA wallets, should not be confirmed')
        check(w["fleet"] == n_eoa, f'{w["name"]}: fleet {w["fleet"]} != EOA count {n_eoa}')
    print(f'  {w["name"][:22]:22} fleet={w["fleet"]:2} ({w["eoa_status"]}) share={w["fleet_vol_share"]:.3f} '
          f'ds=${w["ds_daily"]:,} manuf=${w["manuf_verified"]:,}')

print("== totals ==")
tot = sum(w["manuf_verified"] for w in report["worst"])
check(tot == report["total_confirmed_manuf_per_day"], f'sum(worst) {tot} != total {report["total_confirmed_manuf_per_day"]}')
bychain = collections.defaultdict(lambda: [0, 0])
for w in report["worst"]:
    c = bychain[w["net"]]; c[0] += 1; c[1] += w["manuf_verified"]
for net, v in report["by_chain"].items():
    check(v["pools"] == bychain[net][0] and v["manuf_day"] == bychain[net][1], f'by_chain[{net}] mismatch')
print(f'  total=${tot:,}/day across {report["confirmed"]} confirmed pools; by_chain OK')

print("== exclusion gate 1: phantom volume ==")
for e in report["excluded_uncorroborated"]:
    check(e["ds_daily"] < CORROBORATION_MIN, f'{e["name"]}: excluded_uncorroborated but ds >= min')
    check(e["gt_daily"] > e["ds_daily"], f'{e["name"]}: gt not > ds')
    print(f'  {e["name"][:22]:22} GT=${e["gt_daily"]:,} DS=${e["ds_daily"]:,}')
maxphantom = max((e["gt_daily"] for e in report["excluded_uncorroborated"]), default=0)
check(maxphantom > 100_000_000, f'largest phantom {maxphantom} not > $100M')

print("== exclusion gate 2: contract fleets (eth_getCode) ==")
for e in report["excluded_contract_fleet"]:
    codes = eoa_code.get(e["name"], {})
    n_eoa = sum(1 for c in codes.values() if c == "EOA")
    check(n_eoa < 2, f'{e["name"]}: excluded as contract fleet but has {n_eoa} EOAs')
    check(e["ds_daily"] >= CORROBORATION_MIN, f'{e["name"]}: contract-excluded should have passed volume gate')
    print(f'  {e["name"][:22]:22} orig_fleet={e["orig_fleet"]} eoa_wallets={e["eoa_wallets"]} DS=${e["ds_daily"]:,}')

print("== fleet mechanics (balanced two-sided flow) ==")
for w in report["worst"]:
    d = detail.get((w["net"], w["addr"]))
    if not d: check(False, f'{w["name"]}: no flagged_detail'); continue
    nb = sum(x[1] for x in d["wallets"]); ns = sum(x[2] for x in d["wallets"])
    bal = min(nb, ns) / max(nb, ns) if max(nb, ns) else 0
    check(bal >= 0.60, f'{w["name"]}: buy/sell balance {bal:.2f} < 0.60')
    if d.get("ng") is not None: check(abs(d["ng"]) <= 0.15, f'{w["name"]}: net/gross {d["ng"]} > 0.15')
    print(f'  {w["name"][:22]:22} buys={nb} sells={ns} balance={bal:.3f} net/gross={d.get("ng")}')

print("== attribution (optional) ==")
apath = os.path.join(DATA, "attribution.json")
if os.path.exists(apath):
    a = json.load(open(apath))
    check(a.get("cross", {}).get("IN_intersect_ULTIMA") == [], "IN and ULTIMA funding should not converge")
    inv = a.get("traces", {}).get("IN", {}).get("chain_up_verified", [])
    check("0x50560acf3bb31ceafa26eeb51ff279b59aaa8f99" in inv, "IN verified funding chain missing top wallet")
    print(f'  IN chain_up_verified={inv}; IN_intersect_ULTIMA empty')

print("== eoa evidence (confirmed EVM pools all EOA; excluded ones contract-heavy) ==")
for name, rec in eoa_raw.items():
    print(f'  {name[:22]:22} {rec.get("codes")}')

print("== post tie-out ==")
ppath = os.path.join(HERE, "post", "index.md")
if os.path.exists(ppath):
    txt = open(ppath).read()
    check(f'{report["total_confirmed_manuf_per_day"]:,}' in txt, "post missing confirmed total")
    check(str(report["candidates_screened"]) in txt, "post missing screened count")
    for w in report["worst"]:
        check(f'${w["manuf_verified"]:,}' in txt, f'post missing manuf for {w["name"]}')
    for e in report["excluded_contract_fleet"]:
        check(e["name"].split("/")[0].strip() in txt, f'post missing excluded-contract pool {e["name"]}')
    check(f'{maxphantom:,}' in txt, "post missing largest phantom figure")
    snappools = json.load(open(os.path.join(DATA, "dexscreener_snapshot.json")))["pools"]
    snapIN = snappools["IN"]
    check("481" in txt, "post missing IN turnover")
    check(f'{int(round(snapIN["liq_usd"])):,}' in txt, "post missing IN liquidity")
    check(f'{snapIN["txns_h24"]:,}' in txt, "post missing IN daily tx count")
    combined = sum(w["ds_daily"] for w in report["worst"])
    frac = report["total_confirmed_manuf_per_day"] / combined if combined else 0
    check(0.60 <= frac <= 0.72, f'fabricated fraction {frac:.2f} not ~two thirds')
    check("two thirds" in txt, "post missing 'two thirds' framing")
    check("eth_getCode" in txt or "smart contract" in txt, "post missing eth_getCode/contract gate")
    print(f'  post ties: total, counts, per-pool manuf, excluded pools, phantom, IN turnover, two-thirds ({frac:.2f})')

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
        check(v >= CORROBORATION_MIN, f'{w["name"]}: live ds ${v:,.0f} below min')
        print(f'  {w["name"][:22]:22} live ds=${v:,.0f}')

print(f"\n{CHECKS} checks, {len(FAILS)} failures")
sys.exit(1 if FAILS else 0)
