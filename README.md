# dex-volume-integrity

A direct on-chain census of fabricated (wash-traded) volume on low-cap DEX pools across
Base and BNB Chain. Companion code and data for the market-health post
*"Fabricated Volume on Low-Cap DEX Pools."*

## Headline finding

Of 73 screened high-turnover, low-cap pools, 10 flag on wash-trading mechanics and 9 are
sustained. Three clear all three filters, and their fabricated volume, **measured directly
on-chain over 24 hours**, totals **2,845,587 dollars per day** (as of 2026-07-01).

| Pool | Chain | EOA fleet | On-chain fabricated / day | Fleet share of pool (24h) |
|------|-------|:---:|--:|:---:|
| SOSO / USDC | Base | 11 | $2,014,730 | 98.9% |
| ULTIMA / USDT | BNB Chain | 11 | $506,707 | 42.0% |
| IN / WBNB | BNB Chain | 3 | $324,150 | 9.3% |

Three filters do the work, and each one removed something:

- **Phantom volume:** three pools (two quq, one ARX) reported up to ~396M dollars/day on
  GeckoTerminal and **zero** on an independent source.
- **Contract fleets:** two pools (DUAL, BASED) are traded by smart contracts (routers /
  a Uniswap v4 pool), not externally-owned wallets, so self-trading cannot be confirmed.
- **Snapshot artifacts:** the screen's ~300-trade window over-states bursty fleets. The
  full-day on-chain measurement cut IN six-fold ($2.0M → $0.32M) and **rejected PYTH**
  entirely (window $0.22M → on-chain $206, 0.1% of the pool).

Supporting evidence: the fleets hold almost no inventory versus what they trade (IN $0,
SOSO $2,546 = 0.12%, ULTIMA $376 = 0.03% of daily volume): they cycle funds, not make
markets. IN/WBNB reports 3.5M dollars/day on 7,346 dollars of liquidity (481x turnover);
ULTIMA's fleet is one automated funding relay chain.

## Method

1. **Screen** (`runner.py`): established pool feeds on six chains; keep pools >=2 days old,
   liquidity 10k-3M, >=300 daily trades, volume >=5x liquidity.
2. **Detect**: flag when a set of wallets each has >=3 buys and >=3 sells with balanced counts,
   they are >=50% of sampled trades, and pool net/gross is within 0.15 of zero.
3. **Filter 1 - volume** (`aggregate.py`): drop flags DexScreener will not corroborate (<50k/day).
4. **Filter 2 - contracts** (`eoa_check.py` + `aggregate.py`): `eth_getCode` each EVM fleet
   wallet; keep only EOAs, require >=2.
5. **Filter 3 - direct on-chain full-day** (`onchain_fullday.py` via Bitquery, `helius_pyth.py`
   via Helius; `finalize_report.py` assembles): measure the fleet's actual 24h USD volume on-chain.
   That figure is the reported fabricated volume; the pool total measured this way agrees with
   DexScreener. `sample_windows.py` and `net_inventory.py` add window-robustness and the
   wash-vs-market-making inventory check.
6. **Attribute** (`attribution.py`): trace native-token funding to characterize the operator.

## Reproduce

```bash
pip install -r requirements.txt
python3 verify.py          # re-derive and assert every number, offline
python3 verify.py --live   # + re-check DexScreener volumes are still live
python3 make_figures.py    # regenerate figures/ (and mirror into the post bundle)
```

Live data collection (public APIs; `onchain_fullday.py` needs a Bitquery token and
`helius_pyth.py` a Helius key in `.secrets.env`; run `eoa_check.py` before `aggregate.py`,
then `onchain_fullday.py`/`helius_pyth.py`, then `finalize_report.py`):

```bash
python3 runner.py; python3 eoa_check.py; python3 aggregate.py
python3 snapshot.py; python3 recheck_live.py; python3 net_inventory.py; python3 sample_windows.py
python3 onchain_fullday.py; python3 helius_pyth.py; python3 finalize_report.py
python3 attribution.py
```

## Layout

```
runner.py            screen + lockstep-bot detector (crawl/score, resumable)
eoa_check.py         eth_getCode: per-wallet EOA vs contract
aggregate.py         volume + contract filters (screen funnel, exclusions)
onchain_fullday.py   Bitquery: direct full-day on-chain fabricated volume (EVM)
helius_pyth.py       Helius: same on-chain check for the Solana candidate
net_inventory.py     fleet token holdings vs daily volume (wash vs market-making)
sample_windows.py    multi-window fleet-share robustness
finalize_report.py   assemble report.json from the on-chain measurements
attribution.py       funding-graph tracer (relay/peel chains, hubs, reuse)
verify.py            re-derive and assert every published number (CI entry point)
data/                pools/scores/flagged_detail jsonl; report.json; eoa_check,
                     onchain_fullday, pyth_onchain, net_inventory, window_robustness,
                     dexscreener_snapshot, live_recheck, attribution json
figures/             published figures
post/                the market-health post as a page bundle (index.md + figures)
.github/workflows/   CI running verify.py on every push
```

## Data provenance

`data/report.json` (built by `finalize_report.py`) holds the on-chain headline plus the screen
funnel and the phantom / contract / window-artifact exclusions. `data/onchain_fullday.json` and
`data/pyth_onchain.json` are the direct on-chain measurements; `data/net_inventory.json` and
`data/window_robustness.json` the supporting checks. DexScreener/trade-tape snapshots are dated;
small run-to-run differences reflect the rolling 24-hour window and do not change conclusions.

## Limitations

The on-chain figure counts only the identified fleet, so IN's $0.32M is a floor for that
(clearly manipulated) pool, not a ceiling. On-chain checks are EVM-native; the Solana candidate
was checked with Helius and rejected. Prevalence is conditional on the screen. The analysis shows
self-trading and single-operator funding, not intent or off-chain identity. No secrets are
committed; `.secrets.env` is gitignored.
