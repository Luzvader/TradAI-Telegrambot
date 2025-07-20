"use client";
import MarketsTable from "../../components/MarketsTable";

export default function MarketsPage() {
  const symbols = ["BTC", "ETH", "XRP", "SOL", "BNB"];
  return (
    <div>
      <h2>Markets</h2>
      <MarketsTable symbols={symbols} period="24h" />
    </div>
  );
}
