"use client";

import StrategyBuilder from "../../components/StrategyBuilder";

export default function StrategiesPage() {
  return (
    <div>
      <h2>Strategies</h2>
      <StrategyBuilder />
      <BacklogTable />
    </div>
  );
}
import BacklogTable from "../../components/BacklogTable";
