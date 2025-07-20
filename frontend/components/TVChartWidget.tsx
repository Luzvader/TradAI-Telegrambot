"use client";
export default function TVChartWidget() {
  return (
    <iframe
      src="https://s.tradingview.com/embed-widget/mini-symbol-overview/?symbol=BINANCE:BTCUSDT&locale=en"
      style={{ width: "100%", height: "100%", border: "none" }}
    />
  );
}
