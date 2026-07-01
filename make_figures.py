"""Generate publication figures for the post from committed data files (offline).
Reads data/report.json, data/dexscreener_snapshot.json, data/flagged_detail.jsonl,
data/live_recheck.json. Writes figures/*.png."""
import json, os, collections, shutil
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data"); FIG = os.path.join(HERE, "figures")
POST = os.path.join(HERE, "post")
os.makedirs(FIG, exist_ok=True); os.makedirs(POST, exist_ok=True)
report = json.load(open(os.path.join(DATA, "report.json")))
snap = json.load(open(os.path.join(DATA, "dexscreener_snapshot.json")))["pools"]
live = json.load(open(os.path.join(DATA, "live_recheck.json")))
det = {}
for l in open(os.path.join(DATA, "flagged_detail.jsonl")):
    r = json.loads(l); k = r["name"].split("/")[0].strip(); o = (r.get("ohlcv") or {}).get("active_days", 0)
    if k not in det or o > (det[k].get("ohlcv") or {}).get("active_days", 0): det[k] = r

CH = {"base": "#2563eb", "bsc": "#d69e2e", "solana": "#7c3aed"}
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
def tok(n): return n.split("/")[0].strip()

# ---- Fig 1: fabricated $/day by pool ----
w = sorted(report["worst"], key=lambda x: x["manuf_verified"])
names = [tok(x["name"]) for x in w]; vals = [x["manuf_verified"]/1e6 for x in w]; cols = [CH.get(x["net"], "#888") for x in w]
fig, ax = plt.subplots(figsize=(9, 5))
bars = ax.barh(names, vals, color=cols)
for b, x in zip(bars, w):
    ax.text(b.get_width()+0.03, b.get_y()+b.get_height()/2,
            f'${x["manuf_verified"]/1e6:.2f}M  ({x["net"]}, {x["fleet"]} wallets)', va="center", fontsize=9)
ax.set_xlabel("Fabricated volume, $M / day  (fleet volume-share x independent DexScreener daily volume)")
ax.set_title(f'Confirmed fabricated DEX volume: ${report["total_confirmed_manuf_per_day"]/1e6:.2f}M/day across {len(w)} pools',
             fontweight="bold")
ax.set_xlim(0, max(vals)*1.35)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color=CH["base"], label="Base"), Patch(color=CH["bsc"], label="BSC"), Patch(color=CH["solana"], label="Solana")],
          loc="lower right", frameon=False)
plt.tight_layout(); plt.savefig(os.path.join(FIG, "fig1_fabricated_by_pool.png"), dpi=150); plt.close()

# ---- Fig 2: the biggest reported number was the fakest (GeckoTerminal vs DexScreener) ----
ex = report["excluded_uncorroborated"]
labels = [f'{tok(e["name"])}\n(phantom {i+1})' for i, e in enumerate(ex)]
gt = [e["gt_daily"]/1e6 for e in ex]; ds = [max(e["ds_daily"], 1)/1e6 for e in ex]
x = range(len(ex)); wd = 0.38
fig, ax = plt.subplots(figsize=(9, 5))
ax.bar([i-wd/2 for i in x], gt, wd, label="GeckoTerminal reported", color="#e53e3e")
ax.bar([i+wd/2 for i in x], ds, wd, label="DexScreener (independent)", color="#38a169")
ax.set_yscale("log")
ax.set_xticks(list(x)); ax.set_xticklabels(labels)
ax.set_ylabel("Reported daily volume, $M (log scale)")
ax.set_title("The biggest reported numbers were the fakest: excluded phantom volume", fontweight="bold")
for i, e in enumerate(ex):
    ax.text(i-wd/2, e["gt_daily"]/1e6*1.15, f'${e["gt_daily"]/1e6:.0f}M', ha="center", fontsize=9, color="#e53e3e")
    ax.text(i+wd/2, 1.2, "$0", ha="center", fontsize=9, color="#38a169")
ax.legend(frameon=False)
plt.tight_layout(); plt.savefig(os.path.join(FIG, "fig2_phantom_vs_real.png"), dpi=150); plt.close()

# ---- Fig 3: turnover (volume / liquidity) impossibility (confirmed pools only) ----
confirmed_names = {tok(x["name"]) for x in report["worst"]}
order = sorted(((k, v) for k, v in snap.items() if k in confirmed_names), key=lambda kv: kv[1]["turnover"])
names = [k for k, _ in order]; turns = [v["turnover"] for _, v in order]; cols = [CH.get(v["net"], "#888") for _, v in order]
fig, ax = plt.subplots(figsize=(9, 5))
bars = ax.barh(names, turns, color=cols)
ax.set_xscale("log")
ax.axvline(3, color="#444", ls="--", lw=1)
ax.text(3.2, 0.1, "typical organic ceiling ~2-3x", rotation=90, va="bottom", fontsize=8, color="#444")
for b, (k, v) in zip(bars, order):
    ax.text(b.get_width()*1.1, b.get_y()+b.get_height()/2,
            f'{v["turnover"]:.0f}x  (\\${v["vol_h24"]/1e6:.2f}M on \\${v["liq_usd"]:,.0f} liq)', va="center", fontsize=9)
ax.set_xlabel("Daily volume / liquidity (turnover), log scale")
ax.set_title("Turnover far beyond organic limits; IN reports \\$3.5M/day on \\$7.3k liquidity (481x)", fontweight="bold")
ax.set_xlim(1, max(turns)*6)
plt.tight_layout(); plt.savefig(os.path.join(FIG, "fig3_turnover.png"), dpi=150); plt.close()

# ---- Fig 4: balanced two-sided flow (buys vs sells per fleet) ----
pools = [tok(x["name"]) for x in report["worst"]]
buys = []; sells = []
for x in report["worst"]:
    d = det[tok(x["name"])]; buys.append(sum(a[1] for a in d["wallets"])); sells.append(sum(a[2] for a in d["wallets"]))
x = range(len(pools)); wd = 0.4
fig, ax = plt.subplots(figsize=(9, 5))
ax.bar([i-wd/2 for i in x], buys, wd, label="fleet buys", color="#3182ce")
ax.bar([i+wd/2 for i in x], sells, wd, label="fleet sells", color="#dd6b20")
ax.set_xticks(list(x)); ax.set_xticklabels(pools)
ax.set_ylabel("trades in sampled tape (last ~300)")
ax.set_title("Fleet flow is balanced buy vs sell (net accumulation ~ 0): the wash signature", fontweight="bold")
ax.legend(frameon=False)
plt.tight_layout(); plt.savefig(os.path.join(FIG, "fig4_fleet_balance.png"), dpi=150); plt.close()

# ---- Fig 5: ULTIMA automated funding relay chain (schematic) ----
fig, ax = plt.subplots(figsize=(10, 3.6)); ax.axis("off")
ax.set_xlim(0, 10); ax.set_ylim(0, 3)
nodes = ["origin\n(off-native)", "relay", "relay", "relay", "...", "fleet\nwallet"]
xs = [0.6, 2.2, 3.8, 5.4, 7.0, 8.6]
for i, (nx, lab) in enumerate(zip(xs, nodes)):
    color = "#7c3aed" if i == 0 else ("#d69e2e" if lab.startswith("fleet") else "#f0e6c8")
    tc = "white" if i == 0 else "black"
    box = FancyBboxPatch((nx-0.55, 1.25), 1.1, 0.7, boxstyle="round,pad=0.05", fc=color, ec="#555")
    ax.add_patch(box); ax.text(nx, 1.6, lab, ha="center", va="center", fontsize=8.5, color=tc)
    if i < len(xs)-1:
        ax.add_patch(FancyArrowPatch((nx+0.58, 1.6), (xs[i+1]-0.58, 1.6), arrowstyle="-|>", mutation_scale=13, color="#444"))
ax.text(5.0, 2.55, "ULTIMA (BSC): 11 wallets, one automated funding relay chain", ha="center", fontweight="bold", fontsize=11)
ax.text(5.0, 0.65, "each hop forwards ~0.052 BNB to exactly one next wallet, on a fixed ~8-minute cadence,\n"
                   "with a small fixed per-hop decrement (the forwarding-transaction fee)",
        ha="center", va="center", fontsize=9, color="#333")
plt.tight_layout(); plt.savefig(os.path.join(FIG, "fig5_ultima_funding_chain.png"), dpi=150); plt.close()

# mirror figures into the post page bundle so post/index.md renders standalone
# (on GitHub) and drops straight into the DN wiki as a Hugo page bundle.
for f in os.listdir(FIG):
    if f.endswith(".png"): shutil.copy(os.path.join(FIG, f), os.path.join(POST, f))
print("wrote 5 figures to figures/ and mirrored into post/:", sorted(x for x in os.listdir(FIG) if x.endswith(".png")))
