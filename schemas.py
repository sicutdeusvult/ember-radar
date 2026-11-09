"""Tool schemas — what the model reads to decide when to call Ember Radar."""

_COIN = {
    "type": "string",
    "description": "The coin: its mint address, pool address, symbol (with or without $, e.g. 'GPUCAT' or '$GPUCAT') or name.",
}

EMBER_MARKETS = {
    "name": "ember_markets",
    "description": (
        "Discover coins on Ember, the Solana launchpad where every coin trades against a tokenized stock (NVDAx, TSLAx, "
        "SPYx…) or a blue chip (SOL, USDC) and routes its trading fees to holders, buybacks, a lotto, a trader or liquidity. "
        "Returns the venue's totals plus a ranked list of coins with price, market cap, curve progress to graduation, 24h "
        "volume, fees, trades, holders, 24h move, fee module and age. Use it for 'what's trending / new / about to graduate "
        "on Ember', 'coins paired with NVDAx', 'holder-reward coins', or to find a coin before ember_coin."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "sort": {
                "type": "string",
                "enum": ["trending", "new", "graduating", "movers", "volume", "mcap", "fees", "holders", "oldest"],
                "description": "trending = 24h volume with recency; new = newest first; graduating = closest to graduation (not yet graduated); movers = biggest 24h price move; fees = most fees earned in 24h. Default trending.",
            },
            "pair": {
                "type": "string",
                "description": "Only coins quoted in this pair token: a ticker like 'NVDAx', 'SOL', 'USDC', or a group: 'stocks' (every tokenized stock), 'crypto'.",
            },
            "mode": {
                "type": "string",
                "description": "Only coins with this fee module: holders, burn, lotto, dip, bounty, deep, keep, split, fomo, perp, basket…",
            },
            "graduated": {"type": "boolean", "description": "true = only graduated coins (in their own DAMM v2 pool); false = only coins still on the curve."},
            "query": {"type": "string", "description": "Text to match in the name or symbol."},
            "limit": {"type": "integer", "description": "How many coins to return (1–25, default 10)."},
        },
    },
}

EMBER_COIN = {
    "name": "ember_coin",
    "description": (
        "One Ember coin's whole card: identity and links, pair token, price, market cap, curve progress or graduation, "
        "24h volume / fees / trades, holders, the fee module (what the fees do, how often, next run, rounds paid, last "
        "recipients), all-time fees and payouts, creator, fee split, 24h high/low, description, curated note and the page URL. "
        "Use it when the user names a coin or asks 'what is X', 'how is X doing', 'is X safe / legit on Ember'."
    ),
    "parameters": {
        "type": "object",
        "properties": {"coin": _COIN},
        "required": ["coin"],
    },
}

EMBER_HOLDERS = {
    "name": "ember_holders",
    "description": (
        "Top holders of an Ember coin with their share of the supply, the total holder count and how concentrated the top "
        "10 are. Use it for 'who holds X', 'is X concentrated', 'how many holders'. Pool, DEX and lending vaults are "
        "excluded by the venue (they are program accounts, not people)."
    ),
    "parameters": {
        "type": "object",
        "properties": {"coin": _COIN, "page": {"type": "integer", "description": "Page of 10 holders, from 0 (default 0)."}},
        "required": ["coin"],
    },
}

EMBER_TRADES = {
    "name": "ember_trades",
    "description": (
        "Recent trades of an Ember coin (side, size in dollars, wallet, time) with buy/sell totals over the window. Use it for 'who is buying X', 'is X being sold', 'recent activity on X'."
    ),
    "parameters": {
        "type": "object",
        "properties": {"coin": _COIN, "limit": {"type": "integer", "description": "How many trades (1–100, default 25)."}},
        "required": ["coin"],
    },
}

EMBER_FEES = {
    "name": "ember_fees",
    "description": (
        "What an Ember coin's fee engine has done: the tax rate, fees accrued and claimed, what went to the creator, what is "
        "pending, and the recent payout rounds (holder rewards, buybacks & burns, lotto prizes, bounties, trader payouts) "
        "with amounts, recipients and times. Use it for 'how much has X paid holders', 'when was the last burn', "
        "'is the fee module actually running'."
    ),
    "parameters": {
        "type": "object",
        "properties": {"coin": _COIN, "limit": {"type": "integer", "description": "How many recent payouts to list (1–50, default 10)."}},
        "required": ["coin"],
    },
}

EMBER_FEED = {
    "name": "ember_feed",
    "description": (
        "Ember's live tape: the latest launches, buys, sells, holder payouts, buybacks & burns, lotto draws and bounties "
        "across the whole venue, newest first, with dollar sizes. Use it for 'what's happening on Ember right now', "
        "'any new launches in the last hour', 'biggest buys today'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "description": "Only this kind of event: launch, buy, sell, holders, burn, lotto, bounty, dip, graduate. Default: all.",
            },
            "coin": {"type": "string", "description": "Only events of this coin (mint, symbol or name)."},
            "minutes": {"type": "integer", "description": "Only events from the last N minutes."},
            "limit": {"type": "integer", "description": "How many events (1–100, default 30)."},
        },
    },
}

EMBER_FOMO_BOARD = {
    "name": "ember_fomo_board",
    "description": (
        "The fomode 👀 leaderboard: FOMO traders whose coins on Ember pay them their fees — handle, followers, PnL, the coins "
        "launched for each, what they were paid all-time and in 24h, and venue totals. Use it for 'who are the fomode traders', "
        "'which trader earns the most from Ember coins', 'coins launched for <handle>'."
    ),
    "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "description": "How many traders (1–50, default 10)."}}},
}

EMBER_PAIRS = {
    "name": "ember_pairs",
    "description": (
        "The pair (quote) tokens a coin can be launched against on Ember: tokenized stocks (xStocks, Ondo, Backpack, "
        "PreStocks…), blue-chip crypto and SOL/USDC, with ticker, name, provider and dollar price, plus the venue's launch "
        "economics (fee tiers, graduation caps, fee split). Use it for 'can I pair with TSLA', 'which stocks are on Ember', "
        "'what does a launch cost / how are fees split'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Filter by ticker, name or provider (e.g. 'NVDA', 'Tesla', 'xStocks')."},
            "group": {"type": "string", "enum": ["stocks", "crypto", "base", "all"], "description": "Only this group. Default all."},
            "limit": {"type": "integer", "description": "How many pairs (1–200, default 40)."},
        },
    },
}

EMBER_WATCH = {
    "name": "ember_watch",
    "description": (
        "Your Ember watchlist (kept per Hermes profile). add a coin, remove one, list them, or clear. A watched coin is "
        "what ember_pulse and the start-of-turn pulse report on. Use it when the user says 'watch X', 'add X to my list', "
        "'stop watching X', 'what am I watching'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "remove", "list", "clear"], "description": "Default list."},
            "coin": {"type": "string", "description": "The coin for add/remove (mint, symbol or name)."},
            "note": {"type": "string", "description": "Optional note to keep with the coin (why you watch it, a target)."},
        },
    },
}

EMBER_PULSE = {
    "name": "ember_pulse",
    "description": (
        "What changed on your Ember watchlist since you last looked: price moves past the threshold, graduations, payout "
        "rounds paid, holder-count jumps — and the current line of every watched coin. Use it for 'anything new on my coins', "
        "'how is my watchlist doing', or at the start of a check-in."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "min_move_pct": {"type": "number", "description": "Report price moves of at least this percent (default: the plugin setting, 15)."},
        },
    },
}

ALL = [EMBER_MARKETS, EMBER_COIN, EMBER_HOLDERS, EMBER_TRADES, EMBER_FEES, EMBER_FEED, EMBER_FOMO_BOARD, EMBER_PAIRS, EMBER_WATCH, EMBER_PULSE]
