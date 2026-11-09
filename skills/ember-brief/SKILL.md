---
name: ember-brief
description: The shape of an Ember brief — a short daily or on-demand summary of the Ember launchpad built from the Ember Radar tools.
version: 0.1.0
author: Ember (embercurve.fun)
license: MIT
metadata:
  hermes:
    tags: [Ember, Solana, Launchpad, Crypto, Brief]
    related_skills: [ember-radar:ember-research]
---

# The Ember brief

A brief is what a trader reads in one minute with coffee: what is new, what moved, what paid, what is about to
graduate, and what happened to the coins they watch. It is built from five calls and nothing else:

| Section | Call | Keep |
|---|---|---|
| New launches | `ember_markets sort=new limit=6` | those with `age` under 24h; name, pair, cap, module |
| Movers | `ember_markets sort=movers limit=5` | symbol, change_24h, cap, pair |
| About to graduate | `ember_markets sort=graduating limit=3` | symbol, curve %, cap |
| Paid to holders | `ember_feed kind=holders limit=10` | the biggest two or three by `usd` |
| Your watchlist | `ember_pulse` | every line of `changes`; one line per coin if nothing changed |

## Rules

- Under 200 words. Headings only if there are three or more sections with content; otherwise short paragraphs.
- Skip a section that is empty; never write "no new launches" as a section of its own — fold it into one sentence.
- Every coin gets its pair in parentheses the first time (`GPUCAT (NVDAx)`) and the biggest one or two get their URL.
- Numbers come formatted from the tools; do not recompute them.
- The venue line (`venue` in `ember_markets`: coins, 24h volume, fees, paid out all-time) makes a good last line.
- No predictions, no advice; a brief reports.
- `tone` is a word the user picked: `plain` says it straight, `analyst` adds one sentence of context per section,
  `degen` is allowed to enjoy itself but keeps the numbers exact.
