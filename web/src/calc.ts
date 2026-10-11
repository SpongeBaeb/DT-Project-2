/**
 * 비용 계산 모듈 (기획서 5-5절) — 화면과 분리된 순수 함수. [담당: 최재희]
 *
 * 가격은 사용자가 넣는다 → 브라우저에서 즉시 계산. 서버로 옮길 때도 이 파일만 옮기면 된다.
 * 검증: contracts/golden/cost_cases.json 의 기준 사례 (calc.test.ts), 분해 합 = 변화 (오차 1e-9).
 */

// ───────────────────────────── 입력 ─────────────────────────────
export interface Prices {
  fuelUsdPerT: number; // 연료 가격 USD/t
  euaEurPerT: number; // 배출권 가격 EUR/t CO₂
  krwPerUsd: number;
  krwPerEur: number;
  asOf: string; // 기준일 — 결과에 함께 표시
}

export interface ShipYearCost {
  year: number;
  seaEffKgNm: number; // 해상 효율 (결과 표·API)
  distanceNm: number;
  berthT: number; // 정박 CO₂
  co2PerFuel: number; // 연료 1톤당 CO₂ (보고값, 화석 ≈ 3.11~3.21)
  etsShare: number; // ETS 대상 비율 (역내·EU 정박 100%, 출입 항해 50% 를 섞은 보고값)
}

/** EU ETS 해운 부과 비율 (지침 2023/959): 2024 40%, 2025 70%, 2026~ 100% */
export function etsPhaseIn(year: number): number {
  if (year < 2024) return 0;
  if (year === 2024) return 0.4;
  if (year === 2025) return 0.7;
  return 1;
}

// ───────────────────────────── 연간 비용 ─────────────────────────────
export interface AnnualCost {
  co2T: number;
  fuelT: number;
  fuelCostKrw: number;
  etsCostKrw: number;
  totalKrw: number;
}

export function annualCost(s: ShipYearCost, p: Prices): AnnualCost {
  const co2T = (s.seaEffKgNm * s.distanceNm) / 1000 + s.berthT;
  const fuelT = co2T / s.co2PerFuel;
  const fuelCostKrw = fuelT * p.fuelUsdPerT * p.krwPerUsd;
  const etsCostKrw = co2T * s.etsShare * etsPhaseIn(s.year) * p.euaEurPerT * p.krwPerEur;
  return { co2T, fuelT, fuelCostKrw, etsCostKrw, totalKrw: fuelCostKrw + etsCostKrw };
}

/** "동급 중간 효율이었다면" 대비 비용 차이 (정보로만 제공). 양수 = 동급보다 더 씀 */
export function gapToPeerCost(s: ShipYearCost, peerMedianKgNm: number, p: Prices): AnnualCost {
  const a = annualCost(s, p);
  const b = annualCost({ ...s, seaEffKgNm: peerMedianKgNm }, p);
  return {
    co2T: a.co2T - b.co2T,
    fuelT: a.fuelT - b.fuelT,
    fuelCostKrw: a.fuelCostKrw - b.fuelCostKrw,
    etsCostKrw: a.etsCostKrw - b.etsCostKrw,
    totalKrw: a.totalKrw - b.totalKrw,
  };
}

// ───────────────────────────── 비용 변화 분해 (LMDI-I) ─────────────────────────────
// 비용 = 연료비 + 탄소비
//   연료비 = 운항량(거리) × 효율(CO₂/거리) × 연료환산(1/CO₂per연료) × 연료가격(원)
//   탄소비 = 운항량 × 효율 × 규제(ETS비율×부과비율) × 배출권가격(원)
// 각 항을 로그평균 가중으로 나누면 요인 효과의 합이 정확히 변화와 같다.
export type Factor = "activity" | "efficiency" | "fuelMix" | "fuelPrice" | "regulation" | "carbonPrice";
export const FACTOR_LABELS: Record<Factor, string> = {
  activity: "운항량",
  efficiency: "효율",
  fuelMix: "연료 구성",
  fuelPrice: "연료 가격",
  regulation: "규제(부과 비율)",
  carbonPrice: "배출권 가격",
};

const EPS = 1e-12; // 0 값(예: 2023년 부과 비율 0) 처리용 작은 값

function logMean(a: number, b: number): number {
  if (Math.abs(a - b) < 1e-15 * Math.max(Math.abs(a), Math.abs(b), 1)) return a;
  return (a - b) / (Math.log(a) - Math.log(b));
}

function terms(s: ShipYearCost, p: Prices) {
  const activity = s.distanceNm;
  const efficiency = ((s.seaEffKgNm * s.distanceNm) / 1000 + s.berthT) / s.distanceNm; // t CO₂/nm (정박 포함)
  return {
    fuel: { activity, efficiency, fuelMix: 1 / s.co2PerFuel, fuelPrice: p.fuelUsdPerT * p.krwPerUsd },
    carbon: {
      activity,
      efficiency,
      regulation: Math.max(s.etsShare * etsPhaseIn(s.year), EPS),
      carbonPrice: p.euaEurPerT * p.krwPerEur,
    },
  };
}

const product = (o: Record<string, number>) => Object.values(o).reduce((a, b) => a * b, 1);

export interface Decomposition {
  before: number;
  after: number;
  effects: Record<Factor, number>;
}

export function decomposeCostChange(s0: ShipYearCost, p0: Prices, s1: ShipYearCost, p1: Prices): Decomposition {
  const t0 = terms(s0, p0);
  const t1 = terms(s1, p1);
  const effects: Record<Factor, number> = {
    activity: 0, efficiency: 0, fuelMix: 0, fuelPrice: 0, regulation: 0, carbonPrice: 0,
  };
  for (const key of ["fuel", "carbon"] as const) {
    const f0 = t0[key] as Record<string, number>;
    const f1 = t1[key] as Record<string, number>;
    const v0 = product(f0);
    const v1 = product(f1);
    const w = logMean(v1, v0);
    for (const k of Object.keys(f0)) effects[k as Factor] += w * Math.log(f1[k] / f0[k]);
  }
  const before = product(t0.fuel) + product(t0.carbon);
  const after = product(t1.fuel) + product(t1.carbon);
  return { before, after, effects };
}

// ───────────────────────────── 가정 효과·회수 시점 ─────────────────────────────
export interface Investment {
  capexKrw: number; // 공사비
  downtimeDays: number; // 공사 기간
  dailyLossKrw: number; // 공사 기간 하루 손실
  discountRate: number; // 연 할인율 (예: 0.08)
  years: number; // 평가 기간
}

export interface Payback {
  npvKrw: number;
  paybackYear: number | null; // 누적 절감 ≥ 공사비 + 공사 기간 손실 이 되는 첫 해 (1부터), 없으면 null
  upfrontKrw: number;
}

export function payback(annualSavingKrw: number[], inv: Investment): Payback {
  const upfront = inv.capexKrw + inv.downtimeDays * inv.dailyLossKrw;
  let npv = -upfront;
  let cum = 0;
  let pb: number | null = null;
  for (let t = 1; t <= inv.years; t++) {
    const s = annualSavingKrw[Math.min(t - 1, annualSavingKrw.length - 1)] ?? 0;
    npv += s / Math.pow(1 + inv.discountRate, t);
    cum += s;
    if (pb === null && cum >= upfront) pb = t;
  }
  return { npvKrw: npv, paybackYear: pb, upfrontKrw: upfront };
}
