"""Generate publication figures from committed data (offline). Headline is the direct on-chain
full-day fabricated volume. Reads data/report.json, dexscreener_snapshot.json, flagged_detail.jsonl,
net_inventory.json. Writes figures/*.png and mirrors them into the post page bundle."""
import json, os, collections, shutil
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Patch

HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data")
FIG = os.path.join(HERE, "figures"); POST = os.path.join(HERE, "post")
os.makedirs(FIG, exist_ok=True); os.makedirs(POST, exist_ok=True)
report = json.load(open(os.path.join(DATA, "report.json")))
snap = json.load(open(os.path.join(DATA, "dexscreener_snapshot.json")))["pools"]
det = {}
for l in open(os.path.join(DATA, "flagged_detail.jsonl")):
    r = json.loads(l); k = r["name"].split("/")[0].strip(); o = (r.get("ohlcv") or {}).get("active_days", 0)
    if k not in det or o > (det[k].get("ohlcv") or {}).get("active_days", 0): det[k] = r
CH = {"base": "#2563eb", "bsc": "#d69e2e", "solana": "#7c3aed"}
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
def tok(n): return n.split("/")[0].strip()
conf = report["confirmed_onchain"]

# Fig 1: on-chain fabricated $/day by pool
w = sorted(conf, key=lambda x: x["fleet_usd_24h"])
fig, ax = plt.subplots(figsize=(9, 4.6))
bars = ax.barh([tok(x["name"]) for x in w], [x["fleet_usd_24h"]/1e6 for x in w], color=[CH.get(x["net"], "#888") for x in w])
for b, x in zip(bars, w):
    ax.text(b.get_width()+0.03, b.get_y()+b.get_height()/2,
            f'${x["fleet_usd_24h"]/1e6:.2f}M  ({x["net"]}, {x["fleet_share_24h"]*100:.0f}% of pool)', va="center", fontsize=9)
ax.set_xlabel("Fabricated volume, $M / day  (fleet's actual 24h on-chain USD volume, via Bitquery)")
ax.set_title(f'Confirmed fabricated DEX volume (direct on-chain, 24h): ${report["total_confirmed_onchain_per_day"]/1e6:.2f}M/day across {len(conf)} pools',
             fontweight="bold", fontsize=11.5)
ax.set_xlim(0, max(x["fleet_usd_24h"]/1e6 for x in w)*1.4)
ax.legend(handles=[Patch(color=CH["base"], label="Base"), Patch(color=CH["bsc"], label="BSC")], loc="lower right", frameon=False)
plt.tight_layout(); plt.savefig(os.path.join(FIG, "fig1_fabricated_by_pool.png"), dpi=150); plt.close()

# Fig 2: phantom volume (GeckoTerminal vs DexScreener)
ex = report["excluded_uncorroborated"]
x = range(len(ex)); wd = 0.38
fig, ax = plt.subplots(figsize=(9, 5))
ax.bar([i-wd/2 for i in x], [e["gt_daily"]/1e6 for e in ex], wd, label="GeckoTerminal reported", color="#e53e3e")
ax.bar([i+wd/2 for i in x], [max(e["ds_daily"], 1)/1e6 for e in ex], wd, label="DexScreener (independent)", color="#38a169")
ax.set_yscale("log"); ax.set_xticks(list(x))
ax.set_xticklabels([f'{tok(e["name"])}\n(phantom {i+1})' for i, e in enumerate(ex)])
ax.set_ylabel("Reported daily volume, $M (log scale)")
ax.set_title("Exclusion gate 1: phantom volume (reported vs independent)", fontweight="bold")
for i, e in enumerate(ex):
    ax.text(i-wd/2, e["gt_daily"]/1e6*1.15, f'${e["gt_daily"]/1e6:.0f}M', ha="center", fontsize=9, color="#e53e3e")
    ax.text(i+wd/2, 1.2, "$0", ha="center", fontsize=9, color="#38a169")
ax.legend(frameon=False)
plt.tight_layout(); plt.savefig(os.path.join(FIG, "fig2_phantom_vs_real.png"), dpi=150); plt.close()

# Fig 3: volume concentration (flagged fleet share vs liquid control top-10 share)
controls = json.load(open(os.path.join(DATA, "controls.json")))
items = [(tok(c["name"]), c["fleet_share_24h"], CH.get(c["net"], "#888")) for c in conf]
citems = [(name.split(" (")[0] + " (control)", v["top10_share"], "#a0aec0") for name, v in controls.items()]
allit = sorted(items + citems, key=lambda x: x[1])
fig, ax = plt.subplots(figsize=(9.5, 4.8))
bars = ax.barh([a[0] for a in allit], [a[1]*100 for a in allit], color=[a[2] for a in allit])
for b, a in zip(bars, allit):
    ax.text(b.get_width()+1, b.get_y()+b.get_height()/2, f"{a[1]*100:.0f}%", va="center", fontsize=9)
ax.set_xlabel("share of 24h pool volume held by the flagging wallet set  (controls: top-10 traders)")
ax.set_title("Concentration is the discriminator: flagged fleets vs liquid controls", fontweight="bold")
ax.set_xlim(0, 108)
ax.legend(handles=[Patch(color=CH["base"], label="flagged (Base)"), Patch(color=CH["bsc"], label="flagged (BSC)"),
                   Patch(color="#a0aec0", label="liquid control (top-10 traders)")], loc="lower right", frameon=False)
plt.tight_layout(); plt.savefig(os.path.join(FIG, "fig3_concentration.png"), dpi=150); plt.close()

# Fig 4: balanced two-sided flow (confirmed pools)
pools = [tok(c["name"]) for c in conf]
buys = [sum(a[1] for a in det[tok(c["name"])]["wallets"]) for c in conf]
sells = [sum(a[2] for a in det[tok(c["name"])]["wallets"]) for c in conf]
x = range(len(pools)); wd = 0.4
fig, ax = plt.subplots(figsize=(10, 4.6))
ax.bar([i-wd/2 for i in x], buys, wd, label="fleet buys", color="#3182ce")
ax.bar([i+wd/2 for i in x], sells, wd, label="fleet sells", color="#dd6b20")
ax.set_xticks(list(x)); ax.set_xticklabels(pools)
ax.set_ylabel("trades in sampled tape (last ~300)")
ax.set_title("Fleet flow is balanced buy vs sell (net accumulation ~ 0): the wash signature", fontweight="bold", fontsize=11)
ax.legend(frameon=False)
plt.tight_layout(); plt.savefig(os.path.join(FIG, "fig4_fleet_balance.png"), dpi=150); plt.close()

# Fig 5: ULTIMA funding relay chain schematic
fig, ax = plt.subplots(figsize=(10, 3.6)); ax.axis("off"); ax.set_xlim(0, 10); ax.set_ylim(0, 3)
nodes = ["origin\n(off-native)", "relay", "relay", "relay", "...", "fleet\nwallet"]; xs = [0.6, 2.2, 3.8, 5.4, 7.0, 8.6]
for i, (nx, lab) in enumerate(zip(xs, nodes)):
    color = "#7c3aed" if i == 0 else ("#d69e2e" if lab.startswith("fleet") else "#f0e6c8")
    ax.add_patch(FancyBboxPatch((nx-0.55, 1.25), 1.1, 0.7, boxstyle="round,pad=0.05", fc=color, ec="#555"))
    ax.text(nx, 1.6, lab, ha="center", va="center", fontsize=8.5, color=("white" if i == 0 else "black"))
    if i < len(xs)-1:
        ax.add_patch(FancyArrowPatch((nx+0.58, 1.6), (xs[i+1]-0.58, 1.6), arrowstyle="-|>", mutation_scale=13, color="#444"))
ax.text(5.0, 2.55, "ULTIMA (BSC): 11 wallets, one automated funding relay chain", ha="center", fontweight="bold", fontsize=11)
ax.text(5.0, 0.62, "each hop forwards ~0.052 BNB to exactly one next wallet, on a fixed ~8-minute cadence,\n"
                   "with a small fixed per-hop decrement (the forwarding-transaction fee)", ha="center", va="center", fontsize=9, color="#333")
plt.tight_layout(); plt.savefig(os.path.join(FIG, "fig5_ultima_funding_chain.png"), dpi=150); plt.close()

# Fig 6: sampled-window estimate vs direct on-chain measurement (self-correction)
comp = [(tok(c["name"]), c["window_manuf"], c["fleet_usd_24h"]) for c in conf]
for e in report["excluded_window_artifact"]:
    comp.append((tok(e["name"]) + "\n(rejected)", e["window_manuf"], e["onchain_fleet_usd_24h"]))
labels = [c[0] for c in comp]; x = range(len(comp)); wd = 0.4
fig, ax = plt.subplots(figsize=(9, 4.8))
ax.bar([i-wd/2 for i in x], [c[1]/1e6 for c in comp], wd, label="sampled-window estimate", color="#a0aec0")
ax.bar([i+wd/2 for i in x], [c[2]/1e6 for c in comp], wd, label="direct on-chain 24h", color="#2f855a")
ax.set_xticks(list(x)); ax.set_xticklabels(labels)
ax.set_ylabel("fabricated volume, $M / day")
ax.set_title("Why full-day on-chain matters: a trade snapshot over-states bursty fleets", fontweight="bold")
ax.legend(frameon=False)
plt.tight_layout(); plt.savefig(os.path.join(FIG, "fig6_window_vs_onchain.png"), dpi=150); plt.close()

for f in os.listdir(FIG):
    if f.endswith(".png"): shutil.copy(os.path.join(FIG, f), os.path.join(POST, f))
print("wrote figures:", sorted(x for x in os.listdir(FIG) if x.endswith(".png")))
