"use client";
import MarketsTable from "./MarketsTable";

export default function PricesWidget() {
  const defaultSymbols = ["BTC", "ETH", "XRP", "SOL", "BNB"];
  return <MarketsTable symbols={defaultSymbols} />;
}
