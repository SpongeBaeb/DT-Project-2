/** 비용 칸: 사용자가 가격을 넣으면 calc.ts 로 즉시 계산. [담당: 최재희] */
import { useState } from "react";
import type { DiagnosisResult, ShipInputs } from "../api/types";
import { annualCost, gapToPeerCost, type Prices } from "../calc";

type YearInput = ShipInputs["years"][number];

const DEFAULT_PRICES: Prices = { fuelUsdPerT: 620, euaEurPerT: 72, krwPerUsd: 1380, krwPerEur: 1500, asOf: "직접 입력" };
const won = (v: number) => `${(v / 1e8).toFixed(2)}억 원`;

export default function CostPanel({ result: r, input }: { result: DiagnosisResult; input: YearInput }) {
  const [p, setP] = useState<Prices>(DEFAULT_PRICES);
  const etsKnown = input.ets_co2_t != null;
  const ship = {
    year: r.year,
    seaEffKgNm: r.sea.actual,
    distanceNm: input.distance_nm,
    berthT: r.berth.actual_t,
    co2PerFuel: input.fuel_t ? input.co2_t / input.fuel_t : 3.11,
    etsShare: etsKnown ? input.ets_co2_t! / input.co2_t : 0.75,
  };
  const c = annualCost(ship, p);
  const gap = gapToPeerCost(ship, r.sea.peer_median, p);
  const field = (k: keyof Prices, label: string) => (
    <label className="price">
      {label}
      <input type="number" value={p[k] as number} onChange={(e) => setP({ ...p, [k]: Number(e.target.value) })} />
    </label>
  );
  return (
    <div>
      <div className="prices">
        {field("fuelUsdPerT", "연료 USD/t")}
        {field("euaEurPerT", "배출권 EUR/t")}
        {field("krwPerUsd", "원/USD")}
        {field("krwPerEur", "원/EUR")}
      </div>
      <table className="compact">
        <tbody>
          <tr><td>연료비</td><td className="num">{won(c.fuelCostKrw)}</td></tr>
          <tr><td>배출권 비용</td><td className="num">{won(c.etsCostKrw)}</td></tr>
          <tr><td><b>합계</b></td><td className="num"><b>{won(c.totalKrw)}</b></td></tr>
          <tr><td>동급 중간 효율이었다면 차이</td><td className={`num ${gap.totalKrw > 0 ? "worse" : "better"}`}>{gap.totalKrw > 0 ? "+" : ""}{won(gap.totalKrw)}</td></tr>
        </tbody>
      </table>
      <p className="muted small">가격 기준: {p.asOf}{etsKnown ? "" : " · ETS 대상 비율 0.75 가정(보고값 없음)"}</p>
    </div>
  );
}
