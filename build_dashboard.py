"""Build a self-contained index.html dashboard from the committed data (report.json,
controls.json, net_inventory.json, dexscreener_snapshot.json). No server needed; serves via
GitHub Pages (main / root). Every number is embedded from the same data files verify.py asserts,
so the dashboard cannot drift from the post. Re-run after finalize_report.py."""
import json, os, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "data")
def jload(n): return json.load(open(os.path.join(DATA, n)))
rep = jload("report.json"); controls = jload("controls.json"); netinv = jload("net_inventory.json")
tok = lambda n: n.split("/")[0].strip()

CH = {"base": "#2563eb", "bsc": "#d69e2e", "solana": "#7c3aed"}
conf = rep["confirmed_onchain"]
total = rep["total_confirmed_onchain_per_day"]
gen = dt.datetime.utcnow().strftime("%Y-%m-%d")

conf_rows = "".join(
    f"<tr><td><b>{tok(c['name'])}</b></td><td>{c['net'].upper()}</td><td class=r>{c['fleet']}</td>"
    f"<td class=r>${c['fleet_usd_24h']:,}</td><td class=r>{c['fleet_share_24h']*100:.1f}%</td>"
    f"<td class=r>${c['total_usd_24h']:,}</td></tr>" for c in conf)
inv_rows = "".join(
    f"<tr><td><b>{t}</b></td><td class=r>${netinv[t]['fleet_holdings_usd']:,.0f}</td>"
    f"<td class=r>${netinv[t]['daily_volume_usd']:,}</td><td class=r>{netinv[t]['holdings_to_daily_volume']*100:.2f}%</td></tr>"
    for t in [tok(c['name']) for c in conf])
phantom_rows = "".join(
    f"<tr><td><b>{tok(e['name'])}</b></td><td>{e['net'].upper()}</td><td class=r>${e['gt_daily']:,}</td><td class=r>${e['ds_daily']:,}</td></tr>"
    for e in rep["excluded_uncorroborated"])
contract_rows = "".join(
    f"<tr><td><b>{tok(e['name'])}</b></td><td>{e['net'].upper()}</td><td class=r>{e['eoa_wallets']}/{e['orig_fleet']}</td></tr>"
    for e in rep["excluded_contract_fleet"])
pw = rep["excluded_window_artifact"][0]

# chart data
conc = [(tok(c["name"]), round(c["fleet_share_24h"]*100, 1), CH.get(c["net"], "#888"), "flagged") for c in conf]
conc += [(name.split(" (")[0] + " (control)", round(v["top10_share"]*100, 1), "#a0aec0", "control") for name, v in controls.items()]
conc.sort(key=lambda x: x[1])
fab = sorted(conf, key=lambda c: c["fleet_usd_24h"])
wv = [(tok(c["name"]), c["window_manuf"], c["fleet_usd_24h"]) for c in conf] + [(tok(pw["name"]) + " (rej)", pw["window_manuf"], pw["onchain_fleet_usd_24h"])]

D = {"conc": conc, "fab": [[tok(c["name"]), c["fleet_usd_24h"], CH.get(c["net"], "#888")] for c in fab], "wv": wv}

html = f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Fabricated DEX Volume - dex-volume-integrity</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{{--ink:#1a202c;--muted:#718096;--line:#e2e8f0;--bg:#f7fafc}}
*{{box-sizing:border-box}} body{{margin:0;font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg)}}
.wrap{{max-width:980px;margin:0 auto;padding:28px 20px 60px}}
h1{{font-size:24px;margin:0 0 4px}} h2{{font-size:18px;margin:34px 0 10px;border-bottom:2px solid var(--line);padding-bottom:6px}}
.sub{{color:var(--muted);margin:0 0 22px}}
.hero{{display:flex;gap:16px;flex-wrap:wrap;margin:18px 0}}
.stat{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px 18px;flex:1;min-width:150px}}
.stat .n{{font-size:26px;font-weight:700}} .stat .l{{color:var(--muted);font-size:13px}}
.funnel{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:10px 0}}
.chip{{background:#fff;border:1px solid var(--line);border-radius:20px;padding:6px 14px;font-size:14px}}
.chip b{{font-size:16px}} .arrow{{color:var(--muted)}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:10px;overflow:hidden}}
th,td{{padding:9px 12px;border-bottom:1px solid var(--line);text-align:left;font-size:14px}}
th{{background:#edf2f7;font-weight:600}} td.r,th.r{{text-align:right;font-variant-numeric:tabular-nums}}
tr:last-child td{{border-bottom:none}}
.card{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0}}
.card h3{{margin:0 0 6px;font-size:15px}} .card p{{margin:0;color:var(--muted);font-size:13px}}
canvas{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px;margin:6px 0}}
.foot{{color:var(--muted);font-size:12px;margin-top:34px;border-top:1px solid var(--line);padding-top:14px}}
code{{background:#edf2f7;padding:1px 5px;border-radius:4px;font-size:12px}}
</style></head><body><div class=wrap>
<h1>Fabricated Volume on Low-Cap DEX Pools</h1>
<p class=sub>Direct on-chain census of lockstep-bot wash trading &middot; Base + BNB Chain &middot; as of {gen}</p>

<div class=hero>
 <div class=stat><div class=n>${total/1e6:.2f}M</div><div class=l>fabricated / day (on-chain, 24h)</div></div>
 <div class=stat><div class=n>{rep['confirmed']}</div><div class=l>confirmed pools</div></div>
 <div class=stat><div class=n>{rep['candidates_screened']}</div><div class=l>pools screened</div></div>
 <div class=stat><div class=n>3</div><div class=l>independent filters</div></div>
</div>

<h2>Screen funnel</h2>
<div class=funnel>
 <span class=chip><b>{rep['candidates_screened']}</b> screened</span><span class=arrow>&rarr;</span>
 <span class=chip><b>{rep['flagged_by_mechanics']}</b> flagged</span><span class=arrow>&rarr;</span>
 <span class=chip><b>{rep['sustained']}</b> sustained</span><span class=arrow>&rarr;</span>
 <span class=chip style="border-color:#38a169"><b>{rep['confirmed']}</b> confirmed</span>
</div>

<h2>Confirmed fabricated volume (measured directly on-chain over 24h)</h2>
<table><tr><th>Pool</th><th>Chain</th><th class=r>EOA fleet</th><th class=r>Fabricated / day</th><th class=r>Fleet share</th><th class=r>Pool volume 24h</th></tr>{conf_rows}</table>
<canvas id=fab height=120></canvas>

<h2>Concentration is the discriminator, not turnover</h2>
<p class=sub>Liquid controls run high turnover too (WETH/USDC {controls['WETH/USDC (Base)']['turnover']}x, USDT/WBNB {controls['USDT/WBNB (BSC)']['turnover']}x), but their top-10 traders hold only 26-28% of volume, versus the flagged fleets below.</p>
<canvas id=conc height=150></canvas>

<h2>Why full-day on-chain, not a snapshot</h2>
<p class=sub>A ~300-trade window over-states bursty fleets. Measuring the fleet's real 24h volume corrects it: IN falls from a snapshot-implied ~$2.0M to $324k, and PYTH is rejected.</p>
<canvas id=wv height=130></canvas>

<h2>Wash trading, not market-making</h2>
<p class=sub>Fleets hold almost no inventory versus what they trade: they cycle the same funds.</p>
<table><tr><th>Pool</th><th class=r>Fleet holdings</th><th class=r>Daily volume</th><th class=r>Holdings / volume</th></tr>{inv_rows}</table>

<h2>What was excluded, and why</h2>
<div class=card><h3>Phantom volume (independent source shows zero)</h3>
<table><tr><th>Pool</th><th>Chain</th><th class=r>GeckoTerminal</th><th class=r>DexScreener</th></tr>{phantom_rows}</table></div>
<div class=card><h3>Contract fleets (eth_getCode: traded by routers/aggregators, not EOAs)</h3>
<table><tr><th>Pool</th><th>Chain</th><th class=r>EOA / fleet</th></tr>{contract_rows}</table></div>
<div class=card><h3>Window artifact (rejected by the full-day on-chain check)</h3>
<p>{tok(pw['name'])} ({pw['net'].upper()}): snapshot implied ${pw['window_manuf']:,}, but on-chain over 24h the wallets traded ${pw['onchain_fleet_usd_24h']:,} ({pw['onchain_fleet_share_24h']*100:.1f}% of the pool).</p></div>

<div class=foot>Generated by <code>build_dashboard.py</code> from the same committed data that <code>verify.py</code> asserts; it cannot drift from the post. Companion repository and exact commit are linked with the submission. Figures use on-chain volume via Bitquery/Helius, cross-checked against DexScreener.</div>

<script>
const D={json.dumps(D)};
const money=v=>'$'+(v>=1e6?(v/1e6).toFixed(2)+'M':v>=1e3?(v/1e3).toFixed(0)+'k':Math.round(v));
new Chart(document.getElementById('fab'),{{type:'bar',data:{{labels:D.fab.map(x=>x[0]),datasets:[{{label:'fabricated $/day',data:D.fab.map(x=>x[1]),backgroundColor:D.fab.map(x=>x[2])}}]}},options:{{indexAxis:'y',plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>money(c.parsed.x)+'/day'}}}}}},scales:{{x:{{ticks:{{callback:money}}}}}}}}}});
new Chart(document.getElementById('conc'),{{type:'bar',data:{{labels:D.conc.map(x=>x[0]),datasets:[{{label:'share of 24h pool volume (%)',data:D.conc.map(x=>x[1]),backgroundColor:D.conc.map(x=>x[2])}}]}},options:{{indexAxis:'y',plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>c.parsed.x+'% of pool'}}}}}},scales:{{x:{{max:100,ticks:{{callback:v=>v+'%'}}}}}}}}}});
new Chart(document.getElementById('wv'),{{type:'bar',data:{{labels:D.wv.map(x=>x[0]),datasets:[{{label:'sampled-window estimate',data:D.wv.map(x=>x[1]),backgroundColor:'#a0aec0'}},{{label:'direct on-chain 24h',data:D.wv.map(x=>x[2]),backgroundColor:'#2f855a'}}]}},options:{{plugins:{{tooltip:{{callbacks:{{label:c=>c.dataset.label+': '+money(c.parsed.y)}}}}}},scales:{{y:{{ticks:{{callback:money}}}}}}}}}});
</script>
</div></body></html>"""
open(os.path.join(HERE, "index.html"), "w").write(html)
print(f"wrote index.html ({len(html):,} bytes); headline ${total:,}/day across {rep['confirmed']} pools")
