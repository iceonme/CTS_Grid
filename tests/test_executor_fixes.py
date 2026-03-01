import unittest
from datetime import datetime

from core import Order, OrderStatus, OrderType, Side
from executors.okx import OKXExecutor
from executors.paper import PaperExecutor


class _FakeOKXAPI:
    def get_positions(self, inst_id=None):
        return [
            {
                "instId": "BTC-USDT",
                "pos": "0.25",
                "avgPx": "50000",
                "upl": "10",
            }
        ]

    def get_balances(self):
        return []


class TestExecutorFixes(unittest.TestCase):
    def test_paper_executor_buy_size_in_quote_converts_to_base(self):
        executor = PaperExecutor(initial_capital=1000.0, fee_rate=0.0, slippage_model="none")
        executor.update_market_data(datetime(2026, 1, 1), 100.0)

        order = Order(
            order_id="test_order_1",
            symbol="BTC-USDT",
            side=Side.BUY,
            size=200.0,  # quote notional (USDT)
            order_type=OrderType.MARKET,
            meta={"size_in_quote": True},
        )
        order_id = executor.submit_order(order)

        self.assertTrue(order_id)
        self.assertEqual(order.status, OrderStatus.FILLED)
        self.assertAlmostEqual(order.filled_size, 2.0)
        self.assertAlmostEqual(executor.get_cash(), 800.0)
        pos = executor.get_position("BTC-USDT")
        self.assertIsNotNone(pos)
        self.assertAlmostEqual(pos.size, 2.0)

    def test_okx_executor_symbol_normalization_uses_dash_for_positions(self):
        executor = OKXExecutor(api_key="k", api_secret="s", passphrase="p", is_demo=True)
        executor.api = _FakeOKXAPI()

        pos = executor.get_position("BTC/USDT")
        self.assertIsNotNone(pos)
        self.assertEqual(pos.symbol, "BTC-USDT")

        all_pos = executor.get_all_positions()
        self.assertEqual(len(all_pos), 1)
        self.assertEqual(all_pos[0].symbol, "BTC-USDT")

        context_positions = {p.symbol: p for p in all_pos}
        self.assertIsNotNone(context_positions.get("BTC-USDT"))


if __name__ == "__main__":
    unittest.main()
