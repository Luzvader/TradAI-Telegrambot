"""
Tests para data/fundamentals.py — FundamentalData dataclass.
"""

from data.fundamentals import FundamentalData


def test_fundamental_data_defaults():
    fd = FundamentalData(ticker="AAPL")
    assert fd.ticker == "AAPL"
    assert fd.name == "N/A"
    assert fd.pe_ratio is None
    assert fd.value_score == 0.0


def test_fundamental_data_with_values():
    fd = FundamentalData(
        ticker="MSFT",
        name="Microsoft",
        sector="Technology",
        pe_ratio=30.5,
        roe=0.40,
        current_price=400.0,
    )
    assert fd.name == "Microsoft"
    assert fd.pe_ratio == 30.5
    assert fd.roe == 0.40
    assert fd.current_price == 400.0


def test_fundamental_data_raw_dict():
    fd = FundamentalData(ticker="X", raw={"extra": True})
    assert fd.raw["extra"] is True
