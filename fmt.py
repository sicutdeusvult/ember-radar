"""Human numbers for the model and for /ember: $1.2M, 12.5%, 3h ago, Ab3d…9xYz."""

from __future__ import annotations

import time
from typing import Any

MODE_LABELS = {
    "keep": "Keep it (fees to the creator)",
    "split": "Split (fees to up to 5 wallets)",
    "holders": "Holder rewards (fees paid to holders)",
    "burn": "Buyback & burn",
    "dip": "Dip Defender (buys its own dip)",
    "bounty": "Top Buyer Bounty",
    "deep": "Deep Pool (fees become liquidity)",
    "lotto": "SuperLotto (fees drawn to holders)",
    "lp": "Liquidity",
    "diamond": "Diamond hands",
    "basket": "Basket (fees buy a basket of assets)",
    "booster": "Booster",
    "fomo": "fomode 👀 (fees to a FOMO trader)",
    "perp": "Conviction (fees run a perp position)",
    "predict": "Predict",
}


def num(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        return v if v == v and v not in (float("inf"), float("-inf")) else default  # NaN / inf guard
    except (TypeError, ValueError):
        return default


def usd(x: Any, *, dash: str = "—") -> str:
    v = num(x, float("nan"))
    if v != v:
        return dash
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e9:
        return f"{sign}${a / 1e9:.2f}B"
    if a >= 1e6:
        return f"{sign}${a / 1e6:.2f}M"
    if a >= 1e4:
        return f"{sign}${a / 1e3:.1f}K"
    if a >= 1:
        return f"{sign}${a:,.0f}" if a >= 100 else f"{sign}${a:,.2f}"
    if a == 0:
        return "$0"
    if a >= 0.01:
        return f"{sign}${a:.2f}" if a >= 0.1 else f"{sign}${a:.3f}"
    # a coin price: keep 4 significant digits, subscript the zeros the way the site does
    s = f"{a:.12f}".rstrip("0")
    frac = s.split(".")[1]
    zeros = len(frac) - len(frac.lstrip("0"))
    digits = frac.lstrip("0")[:4]
    if zeros >= 4:
        sub = "₀₁₂₃₄₅₆₇₈₉"
        return f"{sign}$0.0{''.join(sub[int(c)] for c in str(zeros))}{digits}"
    return f"{sign}$0.{'0' * zeros}{digits}"


def pct(x: Any, *, signed: bool = True, digits: int = 1) -> str:
    v = num(x, float("nan"))
    if v != v:
        return "—"
    s = f"{v:+.{digits}f}%" if signed else f"{v:.{digits}f}%"
    return s


def count(x: Any) -> str:
    v = num(x)
    if v >= 1e9:
        return f"{v / 1e9:.1f}B"
    if v >= 1e6:
        return f"{v / 1e6:.1f}M"
    if v >= 1e4:
        return f"{v / 1e3:.1f}K"
    return f"{int(v):,}"


def ago(ts: Any, now: float | None = None) -> str:
    t = num(ts)
    if t <= 0:
        return "—"
    if t > 1e12:  # milliseconds
        t /= 1000
    d = max(0.0, (now or time.time()) - t)
    if d < 60:
        return f"{int(d)}s ago"
    if d < 3600:
        return f"{int(d // 60)}m ago"
    if d < 86400:
        return f"{int(d // 3600)}h ago"
    return f"{int(d // 86400)}d ago"


def age(ts: Any, now: float | None = None) -> str:
    """How old something is, without 'ago': 3h, 2d, 5mo."""
    t = num(ts)
    if t <= 0:
        return "—"
    d = max(0.0, (now or time.time()) - t)
    if d < 3600:
        return f"{max(1, int(d // 60))}m"
    if d < 86400:
        return f"{int(d // 3600)}h"
    if d < 86400 * 60:
        return f"{int(d // 86400)}d"
    return f"{int(d // (86400 * 30))}mo"


def in_(ts: Any, now: float | None = None) -> str:
    """Time until a future stamp: in 12m, in 3h."""
    t = num(ts)
    if t <= 0:
        return "—"
    d = t - (now or time.time())
    if d <= 0:
        return "due"
    if d < 3600:
        return f"in {max(1, int(d // 60))}m"
    if d < 86400:
        return f"in {int(d // 3600)}h"
    return f"in {int(d // 86400)}d"


def short(addr: Any, head: int = 4, tail: int = 4) -> str:
    s = str(addr or "")
    return s if len(s) <= head + tail + 1 else f"{s[:head]}…{s[-tail:]}"


def qty(x: Any, ticker: Any = "") -> str:
    """An amount of the pair token: 0.7036 NVDAx, 1.542e-07 NVDAx."""
    v = num(x)
    body = f"{v:,.4g}" if v >= 1e-3 or v == 0 else f"{v:.4g}"
    return f"{body} {ticker}".strip()


def mode_label(mode: Any) -> str:
    m = str(mode or "").lower()
    return MODE_LABELS.get(m, m or "—")


def trend_from_spark(spark: Any) -> float | None:
    """24h move from the spark the venue serves (first point → last point), in percent."""
    if not isinstance(spark, list) or len(spark) < 2:
        return None
    a, b = num(spark[0]), num(spark[-1])
    if a <= 0:
        return None
    return (b / a - 1) * 100
