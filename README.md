# dex-volume-integrity

A cross-sourced census of fabricated (wash-traded) volume on low-cap DEX pools across
Base, BNB Chain, and Solana. Companion code and data for the market-health post
*"Fabricated Volume on Low-Cap DEX Pools."*

## Headline finding

Of 73 screened high-turnover, low-cap pools, 10 flag on wash-trading mechanics, 9 are
sustained, and **6 are corroborated by an independent volume source**, totaling
**about 5.6 million dollars per day of fabricated volume** (as of 2026-07-01). The
three largest *reported* pools in the raw data (up to ~396M dollars/day on GeckoTerminal)
show **zero** volume on the independent source and are excluded as phantom.

| Pool | Chain | Fleet | Fabricated / day |
|------|-------|:---:|--:|
| IN / WBNB | BNB Chain | 3 | $2.01M |
| SOSO / USDC | Base | 12 | $2.01M |
| ULTIMA / USDT | BNB Chain | 11 | $0.67M |
| DUAL / ETH | Base | 10 | $0.37M |
| BASED / USDT | BNB Chain | 2 | $0.37M |
| PYTH / SOL | Solana | 4 | $0.21M |

IN/WBNB reports 3.5M dollars/day on 7,346 dollars of liquidity, a turnover of 481x.

## Method

1. **Screen** (`runner.py`): from the established pool feeds on six chains, keep pools
   at least two days old, liquidity 10k-3M, at least 300 daily trades, and daily volume
   at least 5x liquidity.
2. **Detect**: flag a pool when a set of wallets each records >=3 buys and >=3 sells with
   balanced counts, those wallets are >=50% of sampled trades, and pool net/gross is within
   0.15 of zero (balanced two-sided flow, near-zero net accumulation = the wash signature).
3. **Corroborate** (`aggregate.py`): recompute manufactured volume as the fleet's volume
   share times the pool's daily volume **as reported independently by DexScreener**, and
   exclude any flag DexScreener will not corroborate (daily volume < 50k or not indexed).
   Aggregator volume on a manipulated pool is often itself fabricated, so no single
   provider's volume field is trusted.
4. **Attribute** (`attribution.py`, `eoa_check.py`): trace native-token funding upward from
   the fleet wallets and confirm they are externally-owned accounts.

## Reproduce

```bash
pip install -r requirements.txt
python3 verify.py          # re-derive and assert every number from committed data (offline)
python3 verify.py --live   # additionally re-check DexScreener volumes are still live
python3 make_figures.py    # regenerate figures/ from committed data
```

Live data collection (hits public APIs; needs a Bitquery token in `.secrets.env` for the
funding trace only):

```bash
python3 runner.py          # screen (alternates crawl / score per run; rate-limited)
python3 aggregate.py       # cross-source corroboration -> data/report.json
python3 snapshot.py        # dated DexScreener volume/liquidity snapshot
python3 recheck_live.py    # live trade-tape re-check for the flagship pools
python3 attribution.py     # BNB-Chain funding-chain trace (requires BITQUERY_TOKEN)
```

## Layout

```
runner.py              screen + lockstep-bot detector (crawl/score, resumable)
aggregate.py           cross-source corroboration and headline computation
attribution.py         funding-graph tracer (peel/relay chains, hubs, wallet reuse)
eoa_check.py           eth_getCode: fleet wallets are EOAs, not contracts
backfill_detail.py     capture per-flag evidence (wallets, tx hashes, OHLCV)
recheck_live.py        live trade-tape re-check for the flagship pools
snapshot.py            dated DexScreener volume/liquidity snapshot
make_figures.py        regenerate figures from committed data
verify.py              re-derive and assert every published number (CI entry point)
data/                  pools.jsonl, scores.jsonl, flagged_detail.jsonl, report.json,
                       dexscreener_snapshot.json, live_recheck.json, attribution files
figures/               published figures
post/                  the market-health post
```

## Data provenance

`data/report.json` is produced by `aggregate.py` and holds the corroborated headline.
`data/flagged_detail.jsonl` holds per-pool evidence (fleet wallets with per-wallet
buy/sell counts and volume, sample transaction hashes, and 60-day daily-volume history).
`data/dexscreener_snapshot.json` and `data/live_recheck.json` are dated snapshots so the
post cites frozen numbers. Small differences between runs reflect DexScreener's rolling
24-hour window and do not change the conclusions.

## Limitations

Fleet volume-share is measured from a sampled trade window and varies between windows
(most notably for ULTIMA, whose figure is a floor). Prevalence is conditional on the
screen (high-turnover, low-cap pools), not an estimate over all DEX pools. The analysis
establishes self-trading and single-operator funding structures, not intent or off-chain
identity; manufactured volume of this kind can serve manipulation or a volume-incentive
program. No private keys or credentials are committed; `.secrets.env` is gitignored.
