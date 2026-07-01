---
title: "Fabricated Volume on Low-Cap DEX Pools: A Cross-Sourced Census of Lockstep-Bot Wash Trading"
date: 2026-07-01
draft: false
authors:
  - mkzung
tags:
  - market-manipulation
  - wash-trading
  - dex
  - on-chain-forensics
---

## Summary

This study screens high-turnover, low-cap DEX pools for wash trading and puts every flag through two independent filters before counting it. Four pools survive both: across Base, BNB Chain, and Solana they carry about 7.2 million dollars a day of independently measured volume, of which roughly 4.9 million, about two thirds, is fabricated by small fleets of wallets trading against themselves. One of them, IN/WBNB on PancakeSwap, shows 3.5 million dollars of daily volume against 7,346 dollars of liquidity, a turnover of 481 times per day.

The two filters are the point. The loudest reported numbers in the raw data are fictional: one pool showed 395,507,943 dollars of daily volume on GeckoTerminal and zero on an independent source. And some pools that clear the volume check turn out to be traded by smart contracts (routers and aggregators), not the coordinated externally-owned wallets that define deliberate self-trading, so they are dropped too. What remains is measurable, attributable, and reproducible: every number below is re-derived from the committed data by a `verify.py` script in the companion repository.

## Data and scope

The screen uses three public sources, none of which requires a paid tier:

- **GeckoTerminal** (`api.geckoterminal.com`) for the pool universe and the per-trade tape (trader address, side, USD size, transaction hash, timestamp).
- **DexScreener** (`api.dexscreener.com`) as an independent second measurement of each pool's daily volume and liquidity.
- **Public JSON-RPC and Bitquery** for on-chain funding attribution (native-token transfers and `eth_getCode`).

Starting from the established (non-launch) pool feeds on six chains, the screen keeps pools that are at least two days old with 10,000 to 3,000,000 dollars of liquidity, at least 300 daily trades, and daily volume of at least five times liquidity. That filter yields the candidate set analysed here: **73 pools screened**. This is a targeted census of high-turnover, low-cap pools, not an estimate across all DEX activity, and the prevalence figures should be read as conditional on that screen.

## Detection method

A wash-trading fleet is a group of wallets that buy and sell the same token in near-equal amounts, so that gross volume is large while net position change is near zero. The detector flags a pool when a set of wallets each records at least three buys and three sells with balanced counts (the difference no greater than a quarter of their total), those wallets account for at least half of the sampled trades, and the pool-wide net-to-gross ratio is within 0.15 of zero. A pool must also show sustained activity: at least seven active days in its 60-day daily-volume history. Balanced two-sided flow at scale, with no accumulation, is the wash signature (Figure 4).

The single most important methodological choice is to **not trust any one provider's volume field**. Aggregator volume on a manipulated pool is often itself fabricated. Manufactured volume is therefore computed as the fleet's share of measured trade volume multiplied by the pool's daily volume **as reported independently by DexScreener**, and any flagged pool that DexScreener will not corroborate (daily volume under 50,000 dollars, or not indexed at all) is excluded from the headline entirely.

A second filter addresses a subtler false positive. The trader recorded for a swap can be a smart contract (a router, an aggregator, or a Uniswap v4 pool manager) rather than a person's wallet, and balanced two-way flow through a shared router is frequently just organic trading, not self-dealing. For every flagged pool on an EVM chain the detector therefore runs `eth_getCode` on each fleet wallet and keeps only externally-owned accounts; a pool needs at least two EOA fleet wallets to be confirmed, and its manufactured-volume estimate is recomputed on those EOAs alone. Solana has no equivalent bytecode check, so its one pool rests on the mechanics and volume corroboration.

## Findings

### The census

Of 73 screened pools, 10 flagged on mechanics and 9 were sustained (at least seven active days). Six cleared the independent-volume filter; four of those also cleared the contract-fleet filter. The confirmed fabricated volume across those four totals **4,864,886 dollars per day** (as of 2026-07-01), roughly two thirds of their 7.2 million dollars of measured volume.

![Confirmed fabricated volume by pool](fig1_fabricated_by_pool.png)

| Pool | Chain | EOA fleet | Fleet volume share | Independent daily volume | Fabricated / day |
|------|-------|:---:|:---:|--:|--:|
| IN / WBNB | BNB Chain | 3 | 0.569 | $3,518,004 | $2,001,744 |
| SOSO / USDC | Base | 11 of 12 | 0.972 | $2,049,436 | $1,992,052 |
| ULTIMA / USDT | BNB Chain | 11 | 0.523 | $1,252,324 | $654,965 |
| PYTH / SOL | Solana | 4 | 0.565 | $382,523 | $216,125 |

(SOSO shows 11 of 12 sampled fleet wallets, the twelfth being a contract that is dropped; PYTH is on Solana, where `eth_getCode` does not apply.)

### The biggest reported numbers were the fakest

Three pools flagged on mechanics were thrown out because the independent source shows no volume at all. The clearest case is a BNB Chain pool for the token quq: GeckoTerminal reported **395,507,943 dollars** of daily volume, while DexScreener does not index the pool and shows zero. A second quq pool (20 million reported) and an ARX pool (14 million reported) show the same pattern. These three excluded pools alone would have added roughly 430 million dollars per day of fictional volume, dwarfing the entire confirmed total, had the study taken aggregator volume at face value (Figure 2).

![Excluded phantom volume: reported versus independent](fig2_phantom_vs_real.png)

This is the reason the corroboration step exists. The most eye-catching numbers in the raw data were the least real.

### Real volume, but not real traders

Two further pools cleared the volume filter but failed the contract check. DUAL/ETH on Base is a Uniswap v4 pool whose flagged fleet is nine smart contracts and a single externally-owned wallet; BASED/USDT on BNB Chain has one externally-owned wallet and one contract. Balanced flow routed through shared contracts cannot be separated from organic trading aggregated by a router, so both are dropped from the confirmed total even though they flag on mechanics. This also corrects a tempting but wrong inference: the wallet that appears in both the BASED and ARX fleets is itself a contract, which is exactly why it shows up across pools. It is shared infrastructure, not a shared operator.

### Turnover beyond physical limits

Every confirmed pool trades far faster than its liquidity can organically support. A pool's daily volume divided by its liquidity (its turnover) rarely exceeds two or three for a normally traded asset. All four exceed five. IN/WBNB is the extreme: 3.5 million dollars of daily volume on 7,346 dollars of liquidity, a turnover of **481 times per day**, across 78,233 transactions (Figure 3). No organic market moves a 7,000-dollar pool three and a half million dollars a day; the volume is manufactured by a handful of wallets cycling the same funds.

![Turnover (daily volume / liquidity)](fig3_turnover.png)

### Three flagship pools

**SOSO / USDC (Base, Uniswap).** Eleven externally-owned wallets (a twelfth sampled trader is a contract and is dropped) form a balanced fleet that accounts for **97.2 percent** of sampled trade volume. This is not a stale snapshot: a fresh pull of the live tape shows the same wallets making up **98.7 percent** of the last 300 trades, each buying and selling in near-equal counts. Example fleet transaction: `0x64b49d3eae370472a16b94ef3569d15c7a078b95a83425cf3f4675836edcc65c` (wallet `0x3d42f45c91279337d6a0fe76a16889288fc767b6`).

**IN / WBNB (BNB Chain, PancakeSwap).** Just three wallets (`0xc86dc628...`, `0xc3f5edd0...`, `0x7afab429...`) produce the 481-times turnover, ping-ponging tens of thousands of micro-trades a day between them (78,233 transactions across the pool). On the live tape they are **83 percent** of the last 300 trades. Example transaction: `0x6467f6c800200ed7b39b604db273186fd48cdd5bc7ae4ea7d966a70f6b70a812`.

**ULTIMA / USDT (BNB Chain, Uniswap).** Eleven wallets executing a mechanical pattern of matched buys and sells; in one live sample each visible fleet wallet had executed an identical three buys and three sells. ULTIMA's fleet share varies by window (0.52 in the captured window, 0.20 in a later one), so its dollar figure is the most conservative in the table and is best read as a floor. What makes ULTIMA the clearest case is not its size but its funding (below).

### Operator attribution

The mechanics prove self-trading; the funding graph identifies coordination. Tracing native-token (BNB) transfers upward from the fleet wallets on BNB Chain gives two clear pictures:

**ULTIMA is a single automated operator.** The eleven wallets are linked by one automated funding chain. Each wallet receives roughly 0.052 BNB and forwards to exactly one next wallet, on a fixed cadence of about eight minutes, with a small fixed per-hop decrement consistent with the forwarding-transaction fee. This is a purpose-built gas-distribution pipeline whose only function is to keep a chain of trading wallets funded while obscuring the source (Figure 5). A chain in which every node has exactly one downstream recipient, on a regular timer, is not organic behaviour.

![ULTIMA automated funding relay chain](fig5_ultima_funding_chain.png)

**IN is a separate, smaller operator.** Its wallets trace to a short chain of throwaway externally-owned accounts (`0x50560acf...` funding `0x40068df75...` funding the fleet), each with only a couple of transactions. Same idea, different hand.

Critically, the two BNB-Chain operators do **not** share a funding ancestor, and neither connects to the Base pool. This is a decentralised pattern: many independent operators, each fabricating volume on its own token, not one actor behind all of them. The confirmed fleets are externally-owned accounts, which is precisely how the contract-fleet filter separated them from router traffic, so the balanced flow is deliberate self-trading rather than an artifact of contract routing.

## Limitations

The fleet's share of volume is measured from a sampled window of the trade tape and varies between windows, most notably for ULTIMA; the reported dollar figures are therefore estimates anchored to the median measured daily volume, and ULTIMA's should be treated as a floor. The screen is a targeted census of high-turnover, low-cap pools, so the prevalence (4 confirmed of 73 screened) is conditional on that filter and is not an estimate over all DEX pools. The contract-fleet filter uses `eth_getCode`, which exists only on EVM chains; the one Solana pool (PYTH) therefore rests on mechanics and volume corroboration without that check. The evidence establishes self-trading and single-operator funding structures; it does not establish intent or identity beyond the on-chain wallets, and manufactured volume of this kind can serve either deliberate manipulation or an exchange or launchpad incentive program that rewards reported volume. The top of each funding chain terminates where funds arrive off-native (for example from a bridge or a centralized exchange), which on-chain data alone cannot pierce.

## Reproducibility

Everything here regenerates from the companion repository. `runner.py` performs the screen, `aggregate.py` applies the cross-source corroboration and the `eth_getCode` gate, `eoa_check.py` produces the per-wallet contract/EOA classification, `attribution.py` traces the funding graph, and `verify.py` re-derives every number in this post from the committed data and exits non-zero on any mismatch. The DexScreener snapshot and the live trade-tape re-check are dated and included as data files.

Companion repository and exact commit are linked with this submission.

## References

- GeckoTerminal API: https://api.geckoterminal.com
- DexScreener API: https://docs.dexscreener.com
- Bitquery EVM Transfers API: https://docs.bitquery.io
- Lin William Cong, Xi Li, Ke Tang, and Yang Yang, "Crypto Wash Trading," Management Science 69(11):6427-6454, 2023 (NBER Working Paper 30783). Establishes that a large share of reported crypto trading volume is fabricated and introduces statistical detection of wash trading; this study applies a complementary on-chain, per-wallet balanced-flow test on DEX pools.
