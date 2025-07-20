from unittest.mock import Mock, patch
from urllib.error import URLError, HTTPError

"""Tests para el cliente de TradingView."""

from tradai.tradingview import TradingViewClient


def test_build_payload():
    """Verifica que el payload incluya los tickers esperados."""
    client = TradingViewClient()
    payload = client._build_payload(["BTC", "ETH"])
    assert payload["symbols"]["tickers"] == [
        "BINANCE:BTCUSDT",
        "BINANCE:ETHUSDT",
    ]


def test_fetch_markets_uses_urlopen():
    """Comprueba que se utilice ``urlopen`` al hacer la petición."""
    client = TradingViewClient()
    mock_response = Mock()
    mock_response.read.return_value = b"{\"data\": []}"
    mock_response.__enter__ = lambda self=mock_response: mock_response
    mock_response.__exit__ = lambda *args: None
    with patch("tradai.tradingview.request.urlopen", return_value=mock_response) as m_open:
        markets = client.fetch_markets(["BTC"])
        assert m_open.call_count == 1
    assert markets == {}


def test_fetch_markets_handles_url_errors():
    """Si ocurre un error de red se devuelve un dict vacío y se loggea."""
    client = TradingViewClient()
    with patch("tradai.tradingview.request.urlopen", side_effect=URLError("boom")):
        with patch("tradai.tradingview.logging.warning") as m_warn:
            markets = client.fetch_markets(["BTC"])
            m_warn.assert_called_once()
    assert markets == {}


def test_fetch_markets_handles_http_errors():
    """Errores HTTP también deben manejarse devolviendo un dict vacío."""
    client = TradingViewClient()
    http_err = HTTPError(url="http://x", code=500, msg="boom", hdrs=None, fp=None)
    with patch("tradai.tradingview.request.urlopen", side_effect=http_err):
        with patch("tradai.tradingview.logging.warning") as m_warn:
            markets = client.fetch_markets(["BTC"])
            m_warn.assert_called_once()
    assert markets == {}
