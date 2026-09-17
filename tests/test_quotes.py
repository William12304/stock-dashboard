import unittest
from scripts.update_quotes import normalize


def fixture():
    return {"meta": {"symbol": "TSLA", "currency": "USD", "regularMarketPrice": 100,
                     "regularMarketTime": 90, "previousClose": 80,
                     "currentTradingPeriod": {"pre": {"start": 100, "end": 200},
                                              "regular": {"start": 200, "end": 300},
                                              "post": {"start": 300, "end": 400}}},
            "timestamp": [110, 120, 130, 210, 310, 320],
            "indicators": {"quote": [{"close": [101, 105, None, 110, 99, 0]}]}}


class QuoteTests(unittest.TestCase):
    def test_premarket_uses_last_regular_close_and_ignores_future(self):
        quote = normalize(fixture(), 150)
        self.assertAlmostEqual(quote["pre"]["changePercent"], 5)
        self.assertEqual(quote["pre"]["time"], 120)
        self.assertIsNone(quote["post"])
        self.assertEqual(quote["marketState"], "pre")

    def test_regular_market_premarket_uses_previous_close(self):
        data = fixture()
        data["meta"]["regularMarketTime"] = 250
        quote = normalize(data, 260)
        self.assertAlmostEqual(quote["pre"]["changePercent"], 31.25)
        self.assertEqual(quote["marketState"], "regular")

    def test_afterhours_uses_same_day_close(self):
        data = fixture()
        data["meta"]["regularMarketTime"] = 300
        quote = normalize(data, 350)
        self.assertAlmostEqual(quote["post"]["changePercent"], -1)
        self.assertEqual(quote["post"]["time"], 310)

    def test_missing_prices_are_not_zero(self):
        data = fixture()
        data["meta"]["regularMarketPrice"] = None
        with self.assertRaises(ValueError):
            normalize(data, 350)

    def test_zero_previous_close_is_unavailable(self):
        data = fixture()
        data["meta"]["previousClose"] = 0
        self.assertIsNone(normalize(data, 150)["regular"]["changePercent"])


if __name__ == "__main__":
    unittest.main()
