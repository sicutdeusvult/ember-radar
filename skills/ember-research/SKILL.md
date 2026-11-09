---
name: ember-research
description: How to research a coin on Ember (the Solana launchpad) with the Ember Radar tools — what to check, what the numbers mean, what to say.
version: 0.1.0
author: Ember (embercurve.fun)
license: MIT
metadata:
  hermes:
    tags: [Ember, Solana, Launchpad, Crypto, Research]
    related_skills: [ember-radar:ember-brief]
---

# Researching a coin on Ember

Ember is a Solana launchpad on Meteora's dynamic bonding curve. Every coin is **paired** with a quote token — a
tokenized stock (NVDAx, TSLAx, SPYx…), a blue chip (SOL, USDC) or a meme — and every trade pays a **tax** (1–3%)
that is split between Meteora, the platform and the coin's **fee module**, which decides what the creator's side
does: paid to holders, used to buy back and burn, drawn as a lotto, handed to the top buyers, given to a FOMO
trader, turned into liquidity, or kept by the creator. A coin lives on its curve until its market cap reaches the
**graduation** cap (25K–40K USD); then it moves into its own DAMM v2 pool and keeps trading.

## The checklist

Call the tools in this order and read them together:

1. `ember_coin coin=<symbol or mint>` — the card. Note the **pair** (a stock pair means holders are paid in that
   stock token), the **curve** (how far from graduation, or graduated), the **tax**, the **module** (what the fees
   do, how often, rounds paid, next run) and the **all-time** fees vs paid-out. A module with many rounds and a
   recent `last_run` is running; `empty_rounds` means the pot never reached the minimum.
2. `ember_holders coin=…` — **top10_share**. Under 20% is spread out; over 40% is concentrated, and one wallet over
   10% deserves a sentence. Program accounts (pools, vaults) are already excluded by the venue, so these are people.
3. `ember_trades coin=… limit=50` — buys vs sells over the window and **net_flow**. Many tiny buys from different
   wallets is organic; a few large wallets alternating is not.
4. `ember_fees coin=…` — the payout ledger: amounts, recipients and times of each round. Regular rounds with
   many recipients are the point of Ember; a coin whose fees never reach anyone is not doing what it says.
5. `ember_feed coin=… minutes=120` — what happened recently, in words.
6. If the module is `fomo`: `ember_fomo_board` for the trader behind it (handle, followers, PnL, what they were paid).

## What to say

- Lead with the one-line verdict the user actually needs (what the coin is, whether its module is doing its job,
  how concentrated it is), then the numbers, then the URL.
- Dollar figures already come formatted (`$12.3K`); percentages are signed; `curve` is either `graduated` or a
  percentage to graduation.
- Never promise returns and never call a coin safe: say what is verifiable (payouts happened, holders are spread
  out, the module runs) and what is not (future price).
- A coin the venue does not list: say so plainly and suggest `ember_markets query=` to find it by name.

## Vocabulary

| Word | Meaning on Ember |
|---|---|
| pair / quote | the token the coin trades against and is paid out in (NVDAx, SOL, USDC…) |
| curve | the bonding curve; `progress` is how far its cap is toward graduation |
| graduation | the coin leaves the curve for a DAMM v2 pool with permanent liquidity |
| tax | the per-trade fee (1%, 2% or 3%) |
| module / mode | what the creator's share of the tax does: holders, burn, lotto, dip, bounty, deep, keep, split, fomo, perp, basket |
| round | one payout of the module (every 5–30 minutes once the pot is worth enough) |
| fomode 👀 | a coin whose fees go to a FOMO leaderboard trader; `flame` variants hand them part of the supply at graduation |
| curated | a coin the Ember team vouches for, with a note |
