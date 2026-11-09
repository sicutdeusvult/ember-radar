"""Ember Radar tests: every handler against a fixture server that answers like Ember does.

    python -m unittest discover -s tests -v        (from the plugin directory)

No network: a local HTTP server serves recorded ``/api/solana/*`` responses from ``tests/fixtures``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
PLUGIN_DIR = HERE.parent
FIXTURES = HERE / "fixtures"

# The plugin is a package whose directory carries a dash, so load it the way Hermes does: by path.
_tmp_home = tempfile.mkdtemp(prefix="ember-radar-test-")
os.environ["HERMES_HOME"] = _tmp_home
_spec = importlib.util.spec_from_file_location("ember_radar", PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(PLUGIN_DIR)])
ember_radar = importlib.util.module_from_spec(_spec)
sys.modules["ember_radar"] = ember_radar
_spec.loader.exec_module(ember_radar)
from ember_radar import fmt, tools, watch  # noqa: E402

MINT = "DemoMint000000000000000000000000000000000001"
POOL = "DemoPool000000000000000000000000000000000001"


def _fixture_for(path: str) -> bytes | None:
    p = path[len("/api/solana/") :] if path.startswith("/api/solana/") else None
    if p is None:
        return None
    name = p.replace("/", "_").replace("?", "_").replace("=", "_").replace("&", "_") + ".json"
    f = FIXTURES / name
    if f.exists():
        return f.read_bytes()
    # the handlers ask with their own limits/pages: fall back on the recorded variant of the same route
    stem = p.split("?")[0].replace("/", "_")
    for g in FIXTURES.glob(stem + "*.json"):
        return g.read_bytes()
    return None


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = _fixture_for(unquote(self.path))
        if body is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"no fixture"}')
            return
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # quiet
        pass


class ToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.site = f"http://127.0.0.1:{cls.server.server_address[1]}"
        tools.configure(cls.site, pulse=True, pulse_min_move_pct=15.0, pulse_cooldown_min=30)
        watch.clear()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def call(self, name, **args):
        out = tools.HANDLERS[name](args)
        self.assertIsInstance(out, str)
        return json.loads(out)

    # ----------------------------------------------------------------------------- shaping
    def test_fmt(self):
        self.assertEqual(fmt.usd(1234567), "$1.23M")
        self.assertEqual(fmt.usd(28400), "$28.4K")
        self.assertEqual(fmt.usd(2.84e-05), "$0.0₄284")
        self.assertEqual(fmt.usd(0.5), "$0.50")
        self.assertEqual(fmt.pct(12.345), "+12.3%")
        self.assertEqual(fmt.count(3.1e9), "3.1B")
        self.assertEqual(fmt.short("FJDy9FDRy6bwGEUKuAC98bUtN8MkpE2pT7Dj7HE3Z7Q1"), "FJDy…Z7Q1")
        self.assertEqual(fmt.ago(time.time() - 125), "2m ago")

    def test_markets_default(self):
        d = self.call("ember_markets")
        self.assertEqual(d["venue"]["coins"], 26)
        self.assertEqual(len(d["coins"]), 10)
        c = d["coins"][0]
        for k in ("name", "symbol", "mint", "pair", "price", "mcap", "change_24h", "volume_24h", "holders", "fees_go_to", "curve", "url"):
            self.assertIn(k, c)
        self.assertTrue(c["url"].startswith(self.site + "/t/"))

    def test_markets_sorts_and_filters(self):
        new = self.call("ember_markets", sort="new", limit=3)["coins"]
        self.assertEqual(len(new), 3)
        grad = self.call("ember_markets", sort="graduating", limit=5)["coins"]
        self.assertTrue(all(c["curve"] != "graduated" for c in grad))
        only_grad = self.call("ember_markets", graduated=True, limit=25)["coins"]
        self.assertEqual(len(only_grad), 5)
        self.assertTrue(all(c["curve"] == "graduated" for c in only_grad))
        nvda = self.call("ember_markets", pair="NVDAx", limit=25)["coins"]
        self.assertTrue(nvda and all(c["pair"] == "NVDAx" for c in nvda))
        stocks = self.call("ember_markets", pair="stocks", limit=25)["coins"]
        self.assertTrue(all(c["pair"] not in ("SOL", "USDC", "MET") for c in stocks))
        holders = self.call("ember_markets", mode="holders", limit=25)["coins"]
        self.assertTrue(holders and all(c["fees_go_to"].startswith("Holder rewards") for c in holders))
        q = self.call("ember_markets", query="gpu")["coins"]
        self.assertEqual([c["symbol"] for c in q], ["GPUCAT"])
        self.assertEqual(len(self.call("ember_markets", limit=100)["coins"]), 25)  # capped

    def test_coin_lookups(self):
        for ref in ("GPUCAT", "$gpucat", "GPU Cat", MINT, POOL):
            d = self.call("ember_coin", coin=ref)
            self.assertEqual(d["coin"]["symbol"], "GPUCAT", ref)
        c = self.call("ember_coin", coin="GPUCAT")["coin"]
        self.assertEqual(c["pair"], "NVDAx")
        self.assertEqual(c["tax"], "2% per trade")
        self.assertEqual(c["module"]["mode"], "holders")
        self.assertIn("rounds_paid", c["module"])
        self.assertIn("fee_split", c)
        self.assertIn("error", self.call("ember_coin", coin="no-such-coin"))
        self.assertIn("error", self.call("ember_coin"))

    def test_holders(self):
        d = self.call("ember_holders", coin="GPUCAT")
        self.assertEqual(d["holders_total"], 812)
        self.assertEqual(len(d["holders"]), 10)
        self.assertEqual(d["concentration"], "moderate")
        self.assertTrue(d["top10_share"].endswith("%"))

    def test_trades(self):
        d = self.call("ember_trades", coin="GPUCAT", limit=5)
        self.assertEqual(len(d["trades"]), 5)
        self.assertEqual(d["buys"]["count"] + d["sells"]["count"], 5)
        self.assertTrue(d["net_flow"].startswith(("$", "-$")))
        t = d["trades"][0]
        for k in ("side", "usd", "tokens", "price", "wallet", "when", "tx"):
            self.assertIn(k, t)

    def test_fees(self):
        d = self.call("ember_fees", coin="GPUCAT", limit=3)
        self.assertEqual(d["tax"], "2% per trade")
        self.assertEqual(len(d["recent_payouts"]), 3)
        self.assertIn("NVDAx", d["accrued_unclaimed"]["amount"])
        self.assertEqual(d["recent_payouts"][0]["kind"], "holders")

    def test_feed(self):
        d = self.call("ember_feed", limit=5)
        self.assertEqual(len(d["events"]), 5)
        self.assertIn("buy", d["kinds_on_tape"])
        h = self.call("ember_feed", kind="holders", limit=50)["events"]
        self.assertTrue(h and all(e["kind"] == "holders" for e in h))
        one = self.call("ember_feed", coin="GPUCAT", limit=50)["events"]
        self.assertTrue(one and all(e["mint"] == MINT for e in one))
        self.assertEqual(self.call("ember_feed", minutes=0, limit=3)["matched"], 3)

    def test_fomo_board(self):
        d = self.call("ember_fomo_board", limit=2)
        self.assertEqual(len(d["traders"]), 2)
        self.assertEqual(d["traders"][0]["handle"], "unipcs")
        self.assertEqual(d["totals"]["traders"], 3)

    def test_pairs(self):
        d = self.call("ember_pairs", query="tesla")
        self.assertEqual([p["ticker"] for p in d["pairs"]], ["TSLAx"])
        self.assertEqual(d["by_group"]["stocks"], 167)
        self.assertIn("fee_tiers", d["launch_economics"])
        crypto = self.call("ember_pairs", group="crypto", limit=200)["pairs"]
        self.assertTrue(crypto and all(p["group"] == "crypto" for p in crypto))
        self.assertIn("modules", self.call("ember_pairs")["launch_economics"])

    # ----------------------------------------------------------------------------- watchlist and pulse
    def test_watch_and_pulse(self):
        self.assertEqual(self.call("ember_watch", action="clear")["watching"], [])
        a = self.call("ember_watch", action="add", coin="GPUCAT", note="nvidia pair")
        self.assertEqual(a["added"]["symbol"], "GPUCAT")
        self.assertEqual(a["watching"], ["GPUCAT"])
        b = self.call("ember_watch", action="add", coin="PIE")
        self.assertEqual(b["watching"], ["GPUCAT", "PIE"])
        lst = self.call("ember_watch")  # default list
        self.assertEqual(lst["count"], 2)
        self.assertEqual(lst["watching"][0]["note"], "nvidia pair")
        self.assertEqual(lst["watching"][0]["since_added"], "+0.0%")
        quiet = self.call("ember_pulse")
        self.assertEqual(quiet["changes"], ["Nothing notable since the last look."])
        self.assertEqual(len(quiet["watching"]), 2)
        # the market moves: rewrite the stored snapshot as if the coin had been 30% cheaper an hour ago
        d = watch.load()
        s = d["coins"][MINT]["snapshot"]
        s["priceUsd"] *= 0.7
        s["rounds"] -= 2
        s["at"] -= 3600
        watch.save(d)
        moved = self.call("ember_pulse")
        self.assertTrue(any("GPUCAT +42.9%" in ln for ln in moved["changes"]), moved["changes"])
        self.assertTrue(any("paid 2 holder rewards rounds" in ln for ln in moved["changes"]), moved["changes"])
        # reported once: the snapshot moved on, so the next pulse is quiet again
        self.assertEqual(self.call("ember_pulse")["changes"], ["Nothing notable since the last look."])
        # a smaller move stays under the threshold
        d = watch.load()
        d["coins"][MINT]["snapshot"]["priceUsd"] *= 0.95
        watch.save(d)
        self.assertEqual(self.call("ember_pulse")["changes"], ["Nothing notable since the last look."])
        self.assertTrue(any("+5.3%" in ln for ln in self.call("ember_pulse", min_move_pct=3)["changes"]))
        rm = self.call("ember_watch", action="remove", coin="$gpucat")
        self.assertEqual(rm["removed"], ["GPUCAT"])
        self.assertEqual(rm["watching"], ["PIE"])
        self.assertIn("error", self.call("ember_watch", action="remove", coin="nothing"))
        self.assertEqual(self.call("ember_watch", action="clear")["cleared"], 1)
        self.assertIn("hint", self.call("ember_pulse"))

    def test_pulse_hook(self):
        self.call("ember_watch", action="clear")
        self.assertIsNone(ember_radar._pulse_hook(session_id="s", user_message="hi"))  # empty watchlist: silent
        self.call("ember_watch", action="add", coin="GPUCAT")
        d = watch.load()
        d["coins"][MINT]["snapshot"]["priceUsd"] *= 2
        d["last_pulse_at"] = 0
        watch.save(d)
        ember_radar._pulse_last_try = 0
        out = ember_radar._pulse_hook(session_id="s", user_message="hi", is_first_turn=True, platform="cli")
        self.assertIsInstance(out, dict)
        self.assertIn("GPUCAT -50.0%", out["context"])
        # the cooldown: the next turn is quiet even though the snapshot would move again
        d = watch.load()
        d["coins"][MINT]["snapshot"]["priceUsd"] *= 2
        watch.save(d)
        ember_radar._pulse_last_try = 0
        self.assertIsNone(ember_radar._pulse_hook(session_id="s", user_message="again"))
        self.call("ember_watch", action="clear")

    def test_slash_command(self):
        self.call("ember_watch", action="clear")
        top = ember_radar._cmd("")
        self.assertIn("Ember · 26 coins", top)
        self.assertIn("Trending:", top)
        card = ember_radar._cmd("gpucat")
        self.assertIn("GPU Cat (GPUCAT) · NVDAx pair", card)
        self.assertIn("Holder rewards", card)
        self.assertIn("Watching GPUCAT", ember_radar._cmd("watch gpucat target 50k"))
        self.assertIn("target 50k", ember_radar._cmd("list"))
        self.assertIn("Ember pulse:", ember_radar._cmd("pulse"))
        self.assertIn("Removed GPUCAT", ember_radar._cmd("unwatch gpucat"))
        self.assertIn("empty", ember_radar._cmd("list"))
        self.assertIn("fomode", ember_radar._cmd("fomo"))
        self.assertIn("TSLAx", ember_radar._cmd("pairs tesla"))
        self.assertIn("Ember tape:", ember_radar._cmd("feed burn"))
        self.assertTrue(ember_radar._cmd("help").startswith("/ember"))
        self.assertTrue(ember_radar._cmd("no-such-coin-xyz").startswith("Ember: No coin"))

    # ----------------------------------------------------------------------------- failure modes
    def test_unreachable_site_is_an_error_not_an_exception(self):
        tools.configure("http://127.0.0.1:9")  # nothing listens here
        try:
            d = self.call("ember_markets")
            self.assertIn("error", d)
            self.assertIn("not reachable", d["error"])
            self.assertTrue(ember_radar._cmd("").startswith("Ember: "))
            self.assertIsNone(ember_radar._pulse_hook(session_id="s", user_message="x"))
        finally:
            tools.configure(self.site)

    def test_register_wires_everything(self):
        class Ctx:
            def __init__(self):
                self.tools, self.hooks, self.commands, self.skills, self.blueprints = [], [], [], [], []

            def get_config(self, key, default=None):
                return {"api_url": ToolsTest.site, "pulse": False, "pulse_min_move_pct": 20, "pulse_cooldown_min": 5}.get(key, default)

            def register_tool(self, **kw):
                self.tools.append(kw["name"])

            def register_hook(self, name, cb, **kw):
                self.hooks.append(name)

            def register_command(self, name, handler, **kw):
                self.commands.append(name)

            def register_skill(self, name, path, **kw):
                self.skills.append((name, Path(path).exists()))

            def register_automation_blueprint(self, key, **kw):
                self.blueprints.append((key, kw["slots"][0]["name"]))

        ctx = Ctx()
        ember_radar.register(ctx)
        manifest = (PLUGIN_DIR / "plugin.yaml").read_text(encoding="utf-8")
        for t in ctx.tools:
            self.assertIn(f"  - {t}\n", manifest)
        self.assertEqual(len(ctx.tools), 10)
        self.assertEqual(ctx.hooks, ["pre_llm_call"])
        self.assertEqual(ctx.commands, ["ember"])
        self.assertEqual(ctx.skills, [("ember-brief", True), ("ember-research", True)])
        self.assertEqual(ctx.blueprints, [("brief", "time")])
        self.assertFalse(tools.setting("pulse"))
        self.assertEqual(tools.setting("pulse_min_move_pct"), 20)
        tools.configure(self.site, pulse=True, pulse_min_move_pct=15.0, pulse_cooldown_min=30)


if __name__ == "__main__":
    unittest.main()
