// 비용 계산 모듈 (기획서 5-5절). 화면과 분리한 순수 함수라 서버로 옮기기 쉽다.
//   연간 CO₂   = 해상 효율(kg/해리) × 거리 ÷ 1000 + 정박 배출(t)
//   연간 연료  = 연간 CO₂ ÷ 연료 1톤당 CO₂
//   연료비     = 연간 연료 × 연료 가격(USD/t) × 원/USD
//   배출권     = 연간 CO₂ × ETS 대상 비율 × 연도별 부과 비율 × 배출권 가격(EUR/t) × 원/EUR
//   속력 가정  = 물리 규칙: 주기관 연료는 거리당 속력²에 비례, 보조기관·보일러는 시간(= 거리 ÷ 속력)에 비례
//   변화 분해  = 로그 평균 디비지아(LMDI): 나눈 값의 합 = 변화 (정확히)

export type PriceKey = "fuel_usd" | "eua_eur" | "fx_usd" | "fx_eur";
/** 가격 한 항목의 출처: 공용 서버 시장 조회(auto), 팀 가격 파일(team), 공용 서버 경제 지표(economics), 사용자 입력(manual) */
export interface PriceOrigin { origin: "auto" | "team" | "manual" | "economics"; source: string; as_of?: string | null; status?: string; url?: string | null; basis?: string | null }
export interface Prices {
  fuel_usd?: number; // 연료 USD/t
  eua_eur?: number; // 배출권 EUR/t
  fx_usd?: number; // 원/USD
  fx_eur?: number; // 원/EUR
  date?: string; // 기준일
  src?: Partial<Record<PriceKey, PriceOrigin>>; // 항목별 출처·기준일
}

export interface Operation {
  sea: number; // 해상 효율 kg CO₂/해리
  dist: number; // 항해 거리 해리
  berth: number; // 정박 CO₂ t
  cpf: number; // 연료 1톤당 CO₂
  ets: number; // ETS 대상 비율
  phase: number; // 부과 비율
}

const has = (x?: number): x is number => typeof x === "number" && Number.isFinite(x);
export const pricesReady = (p: Prices) => has(p.fuel_usd) && has(p.eua_eur) && has(p.fx_usd) && has(p.fx_eur);
export const missingPrices = (p: Prices) =>
  [!has(p.fuel_usd) && "연료 가격", !has(p.eua_eur) && "배출권 가격", !has(p.fx_usd) && "원/USD", !has(p.fx_eur) && "원/EUR"].filter(Boolean) as string[];

export const ETS_PHASE: Record<number, number> = { 2023: 0, 2024: 0.4, 2025: 0.7, 2026: 1 };
export const etsPhase = (y: number) => (y >= 2026 ? 1 : ETS_PHASE[y] ?? 0);

export function co2Of(o: Pick<Operation, "sea" | "dist" | "berth">) {
  return (o.sea * o.dist) / 1000 + o.berth;
}

export interface Cost { co2: number; fuel: number; fuelKrw?: number; etsKrw?: number; total?: number }
export function annualCost(o: Operation, p: Prices): Cost {
  const co2 = co2Of(o);
  const fuel = co2 / o.cpf;
  const fuelKrw = has(p.fuel_usd) && has(p.fx_usd) ? fuel * p.fuel_usd * p.fx_usd : undefined;
  const etsKrw = has(p.eua_eur) && has(p.fx_eur) ? co2 * o.ets * o.phase * p.eua_eur * p.fx_eur : undefined;
  return { co2, fuel, fuelKrw, etsKrw, total: fuelKrw !== undefined && etsKrw !== undefined ? fuelKrw + etsKrw : undefined };
}

/** 속력을 dv(예: −0.1 = 10% 감속)만큼 바꿀 때 해상 효율 배율. m = 주기관 연료 비중 */
export const speedFactor = (dv: number, m: number) => m * (1 + dv) ** 2 + (1 - m) / (1 + dv);

export interface Assumption { eff_pct: number; berth_pct: number; speed_pct: number; main_share: number }
export const NO_ASSUMPTION: Assumption = { eff_pct: 0, berth_pct: 0, speed_pct: 0, main_share: 0.8 };
/** 가정 적용: 효율 개선(%)·정박 감소(%)·속력 변경(%, 물리 규칙) */
export function applyAssumption(o: Operation, a: Assumption): Operation {
  return { ...o, sea: o.sea * (1 - a.eff_pct / 100) * speedFactor(a.speed_pct / 100, a.main_share), berth: o.berth * (1 - a.berth_pct / 100) };
}

export interface Project { capex_krw?: number; days: number; daily_loss_krw?: number; years: number; discount_pct: number }
export interface Npv { upfront?: number; annual: number[]; npv?: number; payback_years?: number }
/** 연도별 절감액(원) 목록으로 순현재가치·회수 시점(누적 절감 ≥ 공사비 + 공사 기간 손실, 할인 전) */
export function npvOf(savings: number[], pr: Project): Npv {
  const upfront = has(pr.capex_krw) ? pr.capex_krw + (has(pr.daily_loss_krw) ? pr.daily_loss_krw * pr.days : 0) : undefined;
  const annual = Array.from({ length: pr.years }, (_, i) => savings[Math.min(i, savings.length - 1)] ?? 0);
  if (upfront === undefined) return { annual };
  const r = pr.discount_pct / 100;
  const npv = annual.reduce((a, s, i) => a + s / (1 + r) ** (i + 1), -upfront);
  let cum = 0, payback: number | undefined;
  for (let i = 0; i < annual.length; i++) {
    if (cum + annual[i] >= upfront && annual[i] > 0) { payback = i + (upfront - cum) / annual[i]; break; }
    cum += annual[i];
  }
  return { upfront, annual, npv, payback_years: payback };
}

// ── 비용 변화 분해 (LMDI) ───────────────────────────────────────────
export type DecompKey = "dist" | "eff" | "berth" | "fuelkind" | "fuelprice" | "route" | "phase" | "euaprice";
export const DECOMP_NAME: Record<DecompKey, string> = {
  dist: "운항량 (거리)", eff: "해상 효율", berth: "정박 배출", fuelkind: "연료 종류 (CO₂÷연료)", fuelprice: "연료 가격",
  route: "ETS 대상 비율 (항로)", phase: "규제 (부과 비율)", euaprice: "배출권 가격",
};
const L = (a: number, b: number) => (Math.abs(a - b) < 1e-12 ? a : (a - b) / (Math.log(a) - Math.log(b)));

/** 두 해(0 → 1)의 비용 변화를 요인별로. 가격이 한 해만 있으면 두 해에 같은 값을 쓴다(가격 효과 0) */
export function decompose(o0: Operation, o1: Operation, p0: Prices, p1: Prices): { total: number; parts: Record<DecompKey, number> } | undefined {
  if (!pricesReady(p1)) return undefined;
  const q0 = pricesReady(p0) ? p0 : p1;
  const S0 = (o0.sea * o0.dist) / 1000, S1 = (o1.sea * o1.dist) / 1000;
  const C0 = S0 + o0.berth, C1 = S1 + o1.berth;
  const dSd = L(S1, S0) * Math.log(o1.dist / o0.dist), dSe = L(S1, S0) * Math.log(o1.sea / o0.sea), dB = o1.berth - o0.berth;
  const dC = C1 - C0;
  const w = Math.abs(dC) > 1e-12 ? { dist: dSd / dC, eff: dSe / dC, berth: dB / dC } : { dist: 0, eff: 0, berth: 0 };
  const parts = { dist: 0, eff: 0, berth: 0, fuelkind: 0, fuelprice: 0, route: 0, phase: 0, euaprice: 0 } as Record<DecompKey, number>;
  // 연료비 = CO₂ × (1/연료 1톤당 CO₂) × 연료 가격(원)
  const Pf0 = q0.fuel_usd! * q0.fx_usd!, Pf1 = p1.fuel_usd! * p1.fx_usd!;
  const F0 = (C0 / o0.cpf) * Pf0, F1 = (C1 / o1.cpf) * Pf1;
  const lf = L(F1, F0);
  const fC = lf * Math.log(C1 / C0);
  parts.dist += fC * w.dist; parts.eff += fC * w.eff; parts.berth += fC * w.berth;
  parts.fuelkind += lf * Math.log(o0.cpf / o1.cpf);
  parts.fuelprice += lf * Math.log(Pf1 / Pf0);
  // 배출권 = CO₂ × ETS 대상 비율 × 부과 비율 × 배출권 가격(원). 한쪽이 0이면 로그를 쓸 수 없어 차이 전체를 해당 요인으로
  const Pe0 = q0.eua_eur! * q0.fx_eur!, Pe1 = p1.eua_eur! * p1.fx_eur!;
  const E0 = C0 * o0.ets * o0.phase * Pe0, E1 = C1 * o1.ets * o1.phase * Pe1;
  if (E0 > 0 && E1 > 0) {
    const le = L(E1, E0);
    const eC = le * Math.log(C1 / C0);
    parts.dist += eC * w.dist; parts.eff += eC * w.eff; parts.berth += eC * w.berth;
    parts.route += le * Math.log(o1.ets / o0.ets);
    parts.phase += le * Math.log(o1.phase / o0.phase);
    parts.euaprice += le * Math.log(Pe1 / Pe0);
  } else {
    parts.phase += E1 - E0;
  }
  return { total: F1 + E1 - (F0 + E0), parts };
}
