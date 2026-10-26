"""Sample quotes for the demo.

These are static, illustrative prices, not live market data. In the product
the broker adapter or a market-data client supplies the last price; the
engine does not care where the number comes from.
"""

SAMPLE_QUOTES: dict[str, float] = {
    "AAPL": 232.10,
    "MSFT": 418.55,
    "NVDA": 186.40,
    "TSLA": 258.30,
    "AMD": 164.20,
    "SPY": 571.25,
    "QQQ": 489.60,
    "PLTR": 142.75,
    "SOFI": 21.84,
    "HOOD": 118.60,
}

# Sample option contracts: contract description -> (underlying, premium per share)
SAMPLE_OPTIONS: dict[str, tuple[str, float]] = {
    "SPY 2026-11-20 575 C": ("SPY", 3.40),
    "SPY 2026-11-20 560 P": ("SPY", 2.95),
    "NVDA 2026-11-20 190 C": ("NVDA", 6.10),
    "TSLA 2026-11-20 260 C": ("TSLA", 11.80),
    "AAPL 2026-12-18 240 C": ("AAPL", 4.25),
}

TEMPLATES = [
    "discretionary",
    "moving-average pullback",
    "MACD cross",
    "earnings hold",
    "swing (3 to 10 days)",
]
