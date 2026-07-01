# dex-volume-integrity

A cross-sourced census of fabricated (wash-traded) volume on low-cap DEX pools across
Base, BNB Chain, and Solana. Companion code and data for the market-health post
*"Fabricated Volume on Low-Cap DEX Pools."*

## Headline finding

Of 73 screened high-turnover, low-cap pools, 10 flag on wash-trading mechanics and 9 are
sustained. Six clear an independent-volume filter, and **four also clear an `eth_getCode`
contract-fleet filter**, totaling **about 4.9 million dollars per day of fabricated volume**
(as of 2026-07-01), roughly two thirds of those pools' measured volume.

Two gates do the work. Three pools reported up to ~396M dollars/day on GeckoTerminal but show
**zero** on the independent source (phantom volume). Two more clear the volume gate but are
traded by smart contracts (routers/aggregators, including a Uniswap v4 pool) rather than
externally-owned wallets, so they cannot be confirmed as deliberate self-trading.

| Pool | Chain | EOA fleet | Fabricated / day |
|------|-------|:---:|--:|
| IN / WBNB | BNB Chain | 3 | $2.01M |
| SOSO / USDC | Base | 11 of 12 | $1.99M |
| ULTIMA / USDT | BNB Chain | 11 | $0.66M |
| PYTH / SOL | Solana | 4 | $0.22M |

IN/WBNB reports 3.5M dollars/day on 7,346 dollars of liquidity, a turnover of 481x.
Excluded by the contract-fleet gate: DUAL/ETH (9 of 10 fleet wallets are contracts) and
BASED/USDT (1 of 2). Excluded as phantom: two quq pools and an ARX pool.

## Method

1. **Screen** (`runner.py`): from the established pool feeds on six chains, keep pools
   at least two days old, liquidity 10k-3M, at least 300 daily trades, and daily volume
   at least 5x liquidity.
2. **Detect**: flag a pool when a set of wallets each records >=3 buys and >=3 sells with
   balanced counts, those wallets are >=50% of sampled trades, and pool net/gross is within
   0.15 of zero (balanced two-sided flow, near-zero net accumulation = the wash signature).
3. **Corroborate volume** (`aggregate.py`): recompute manufactured volume as the fleet's volume
   share times the pool's daily volume **as reported independently by DexScreener**, and
   exclude any flag DexScreener will not corroborate (daily volume < 50k or not indexed).
   Aggregator volume on a manipulated pool is often itself fabricated, so no single
   provider's volume field is trusted.
4. **Contract-fleet gate** (`eoa_check.py` + `aggregate.py`): run `eth_getCode` on each EVM
   fleet wallet, keep only externally-owned accounts, require at least two, and recompute the
   volume share on those EOAs. Pools whose fleets are mostly contracts (routers, aggregators,
   v4 pool managers) are excluded because balanced flow through shared contracts cannot be
   distinguished from organic trading. Solana has no bytecode check, so its pool rests on 2-3.
5. **Attribute** (`attribution.py`): trace native-token funding upward from the fleet wallets
   to characterize the operator (peel/relay chains, fan-out hubs, cross-token reuse).

## Reproduce

```bash
pip install -r requirements.txt
python3 verify.py          # re-derive and assert every number from committed data (offline)
python3 verify.py --live   # additionally re-check DexScreener volumes are still live
python3 make_figures.py    # regenerate figures/ (and mirror into the post bundle)
```

Live data collection (hits public APIs; `attribution.py` needs a Bitquery token in
`.secrets.env`; run `eoa_check.py` before `aggregate.py`, which reads its output):

```bash
python3 runner.py          # screen (alternates crawl / score per run; rate-limited)
python3 eoa_check.py       # eth_getCode classification -> data/eoa_check.json
python3 aggregate.py       # volume corroboration + EOA gate -> data/report.json
python3 snapshot.py        # dated DexScreener volume/liquidity snapshot
python3 recheck_live.py    # live trade-tape re-check for the flagship pools
python3 attribution.py     # BNB-Chain funding-chain trace (requires BITQUERY_TOKEN)
```

## Layout

```
runner.py              screen + lockstep-bot detector (crawl/score, resumable)
eoa_check.py           eth_getCode: per-wallet EOA vs contract classification
aggregate.py           volume corroboration + eth_getCode gate + headline computation
attribution.py         funding-graph tracer (peel/relay chains, hubs, wallet reuse)
backfill_detail.py     capture per-flag evidence (wallets, tx hashes, OHLCV)
recheck_live.py        live trade-tape re-check for the flagship pools
snapshot.py            dated DexScreener volume/liquidity snapshot
make_figures.py        regenerate figures from committed data
verify.py              re-derive and assert every published number (CI entry point)
data/                  pools.jsonl, scores.jsonl, flagged_detail.jsonl, report.json,
                       eoa_check.json, dexscreener_snapshot.json, live_recheck.json,
                       attribution.json
figures/               published figures
post/                  the market-health post as a page bundle (index.md + figures)
.github/workflows/     CI running verify.py on every push
```

## Data provenance

`data/report.json` is produced by `aggregate.py` and holds the confirmed headline.
`data/flagged_detail.jsonl` holds per-pool evidence (fleet wallets with per-wallet
buy/sell counts and volume, sample transaction hashes, and 60-day daily-volume history).
`data/eoa_check.json` holds the per-wallet `eth_getCode` result behind the contract gate.
`data/dexscreener_snapshot.json` and `data/live_recheck.json` are dated snapshots so the
post cites frozen numbers. Small differences between runs reflect DexScreener's rolling
24-hour window and do not change the conclusions.

## Limitations

Fleet volume-share is measured from a sampled trade window and varies between windows
(most notably for ULTIMA, whose figure is a floor). Prevalence is conditional on the
screen (high-turnover, low-cap pools), not an estimate over all DEX pools. The `eth_getCode`
gate is EVM-only, so the Solana pool (PYTH) rests on mechanics and volume corroboration.
The analysis establishes self-trading and single-operator funding structures, not intent or
off-chain identity; manufactured volume of this kind can serve manipulation or a
volume-incentive program. No private keys or credentials are committed; `.secrets.env` is
gitignored.
