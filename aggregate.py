"""Aggregate - VERIFIED / cross-sourced.
scores.jsonl = the screen (prevalence among candidates). flagged_detail.jsonl = per-flag evidence
(fleet volume-share, wallets, GeckoTerminal OHLCV). GeckoTerminal volume is UNRELIABLE for these
pools (it reports phantom wash volume, e.g. quq $440M/day that DexScreener shows as $0), so the
headline manufactured-$/day is recomputed on the INDEPENDENT DexScreener daily volume x the fleet's
volume-share, and any sustained flag that DexScreener will not corroborate (no listing / near-zero)
is EXCLUDED. A second gate uses eth_getCode (data/eoa_check.json): a fleet that is substantially
smart contracts (router / aggregator / v4 pool manager) cannot be confirmed as deliberate
self-trading, so shares are recomputed on EOA-only wallets and a pool is excluded if fewer than
two EOAs remain. Only sustained (>=7 active days) + volume-corroborated + EOA-confirmed (or
Solana mechanics, where eth_getCode does not apply) pools reach the headline."""
import json, os, subprocess, collections
HERE = os.path.dirname(os.path.abspath(__file__))
DS_CHAIN = {"base":"base","bsc":"bsc","solana":"solana","eth":"ethereum","arbitrum":"arbitrum","polygon_pos":"polygon"}

def load(n):
    p = os.path.join(HERE, "data", n); out = []
    if os.path.exists(p):
        for l in open(p):
            try: out.append(json.loads(l))
            except Exception: pass
    return out

def jget(u):
    try: return json.loads(subprocess.run(["curl","-sS","--max-time","15",u],capture_output=True,text=True,timeout=18).stdout or "{}")
    except Exception: return {}

sc = {}
for r in sorted(load("scores.jsonl"), key=lambda x: x.get("ts","")):
    sc[(r["net"],r["addr"])] = r
scored = len(sc); flagged_screen = sum(1 for r in sc.values() if r.get("flagged"))

dd = {}
for r in load("flagged_detail.jsonl"):
    k=(r["net"],r["addr"]); cur=dd.get(k)
    if cur is None or (r.get("ohlcv") or {}).get("active_days",0) > (cur.get("ohlcv") or {}).get("active_days",0):
        dd[k]=r
sustained = [r for r in dd.values() if (r.get("ohlcv") or {}).get("active_days",0) >= 7]

# eth_getCode gate: fleets that are substantially smart contracts (routers / aggregators /
# v4 pool managers) cannot be confirmed as deliberate self-trading, so they are recomputed on
# EOA-only wallets and excluded from the headline if fewer than two EOAs remain. eoa_check.json
# is keyed by pool name -> per-wallet EOA/CONTRACT (EVM chains only; Solana has no eth_getCode).
eoa_raw = {}
try: eoa_raw = json.load(open(os.path.join(HERE, "data", "eoa_check.json")))
except Exception: pass
eoa_code = {name: {w[0].lower(): w[1] for w in rec.get("wallets", [])} for name, rec in eoa_raw.items()}

verified = []
for r in sustained:
    net, addr, name = r["net"], r["addr"], r["name"]
    ds = jget(f"https://api.dexscreener.com/latest/dex/pairs/{DS_CHAIN.get(net,net)}/{addr}")
    dp = ds.get("pairs") or []
    ds_daily = float((dp[0].get("volume") or {}).get("h24") or 0) if dp else 0.0
    gt_daily = (r.get("ohlcv") or {}).get("median_daily", 0)
    corrob = ds_daily > 50000  # DexScreener independently shows meaningful volume

    wallets = r.get("wallets", []); base_share = r.get("fleet_vol_share", 0) or 0
    fleet_vol = sum(w[3] for w in wallets); sample_vol = (fleet_vol / base_share) if base_share else 0
    codes = eoa_code.get(name)
    if codes:  # EVM pool with an eth_getCode result: keep only EOA wallets
        eoa_wallets = [w for w in wallets if codes.get(w[0].lower()) == "EOA"]
        eoa_n = len(eoa_wallets)
        eoa_vol = sum(w[3] for w in eoa_wallets)
        share = (eoa_vol / sample_vol) if sample_vol else 0.0
        eoa_status = "confirmed" if eoa_n >= 2 else "contract_fleet"
        fleet_n = eoa_n
    else:      # Solana / no eth_getCode available -> mechanics only
        share = base_share; eoa_status = "n/a"; fleet_n = len(wallets)
    share = round(share, 3)                    # store and compute on the same rounded share
    manuf = int(share * ds_daily)
    cls = ("uncorroborated" if not corrob else ("contract_fleet" if eoa_status == "contract_fleet" else "confirmed"))
    verified.append(dict(r, ds_daily=int(ds_daily), gt_daily=int(gt_daily), fleet=fleet_n,
        fleet_vol_share=round(share, 3), orig_fleet=len(wallets), eoa_status=eoa_status,
        manuf_verified=manuf, corroborated=corrob, cls=cls))

confirmed = [r for r in verified if r["cls"] == "confirmed"]
contract_excl = [r for r in verified if r["cls"] == "contract_fleet"]
uncorrob = [r for r in verified if r["cls"] == "uncorroborated"]
total = sum(r["manuf_verified"] for r in confirmed)
bychain = collections.defaultdict(lambda: [0, 0])
for r in confirmed:
    c = bychain[r["net"]]; c[0] += 1; c[1] += r["manuf_verified"]

report = dict(candidates_screened=scored, flagged_by_mechanics=flagged_screen,
    sustained=len(sustained), corroborated_by_volume=len(confirmed) + len(contract_excl),
    confirmed=len(confirmed),
    excluded_contract_fleet=[dict(net=r["net"], name=r["name"], orig_fleet=r["orig_fleet"],
        eoa_wallets=sum(1 for w in r.get("wallets", []) if eoa_code.get(r["name"], {}).get(w[0].lower()) == "EOA"),
        ds_daily=r["ds_daily"], addr=r["addr"]) for r in contract_excl],
    excluded_uncorroborated=[dict(net=r["net"], name=r["name"], gt_daily=r["gt_daily"], ds_daily=r["ds_daily"]) for r in uncorrob],
    total_confirmed_manuf_per_day=total,
    by_chain={k: dict(pools=v[0], manuf_day=v[1]) for k, v in bychain.items()},
    worst=[dict(net=r["net"], name=r["name"], fleet=r["fleet"], orig_fleet=r["orig_fleet"],
               eoa_status=r["eoa_status"], fleet_vol_share=r["fleet_vol_share"],
               active_days=(r.get("ohlcv") or {}).get("active_days"), ds_daily=r["ds_daily"],
               manuf_verified=r["manuf_verified"], addr=r["addr"]) for r in sorted(confirmed, key=lambda x:-x["manuf_verified"])])
json.dump(report, open(os.path.join(HERE, "data", "screen.json"), "w"), indent=1)  # screen layer; finalize_report.py builds the on-chain report.json from this

print("=== Fabricated DEX volume - VERIFIED (cross-sourced + eth_getCode gated) ===")
print(f"candidates screened: {scored} | flagged by mechanics: {flagged_screen} | sustained (>=7d): {len(sustained)}")
print(f"corroborated by DexScreener volume: {len(confirmed)+len(contract_excl)}")
print(f"EXCLUDED - phantom volume (DexScreener won't corroborate): {len(uncorrob)}")
for r in uncorrob:
    print(f"    {r['net']} {r['name'][:24]} GT=${r['gt_daily']:,} DS=${r['ds_daily']:,}")
print(f"EXCLUDED - contract fleet (eth_getCode: <2 EOA wallets, router/aggregator ambiguity): {len(contract_excl)}")
for r in contract_excl:
    print(f"    {r['net']} {r['name'][:24]} orig_fleet={r['orig_fleet']} eoa={report['excluded_contract_fleet'][contract_excl.index(r)]['eoa_wallets']} DS=${r['ds_daily']:,}")
print(f"CONFIRMED (corroborated volume + EOA/mechanics): {len(confirmed)}")
print(f"TOTAL confirmed manufactured volume: ${total:,}/day  (EOA fleet vol-share x independent DexScreener daily volume)")
for r in sorted(confirmed, key=lambda x:-x["manuf_verified"]):
    print(f"  {r['net']:8} {r['name'][:22]:22} fleet={r['fleet']}({r['eoa_status']}) share={r['fleet_vol_share']} "
          f"active={(r.get('ohlcv') or {}).get('active_days')}d DS=${r['ds_daily']:,} manuf=${r['manuf_verified']:,}")
