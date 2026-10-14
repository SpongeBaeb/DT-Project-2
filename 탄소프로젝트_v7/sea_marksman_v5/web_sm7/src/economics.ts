// 공용 서버 경제 계산 (/economics/*): 비용 모델의 가격 시나리오·환율·ETS 비율과 선박별 사전계산 비용.
// 서버 경고: 경제 자료 MRV 판(v61)이 현재 판(v62)과 다르고, 환율은 팀 고정 초안 값, 사전계산은 base 가격 시나리오뿐이다.
// 이 값을 입력 가격으로 적용하거나 우리 모델 결과와 비교하는 용도로만 쓴다.
import type { Prices } from "./calc";
import { shared } from "./shared";

export interface EconParamItem { key: string; value: number | string; unit?: string | null; note?: string | null }
export interface EconMeta { data_source: string; calculation_mode: string; price_date: string; economic_mrv_version: string; current_mrv_versions: string[]; warnings: string[] }
export interface EconParams extends EconMeta { items: EconParamItem[] }
export interface EconRow {
  imo: string; year: number; price_scenario: string; price_date: string; distance_nm: number;
  fuel_price_usd_per_t: number; eua_price_eur_per_t: number; fuel_cost_mkrw: number; carbon_cost_mkrw: number; fuel_cost_share_pct: number;
  total_cost_mkrw_p10: number; total_cost_mkrw_p50: number; total_cost_mkrw_p90: number; total_cost_mkrw_2025: number;
  change_vs_2025_mkrw_p50: number; top_cause?: string | null; peer_cost_diff_mkrw?: number | null;
  effect_sea_eff_mkrw_p50?: number | null; effect_berth_mkrw_p50?: number | null; effect_regulation_mkrw?: number | null;
  effect_fuel_price_mkrw?: number | null; effect_eua_price_mkrw?: number | null;
  cost_per_nm_krw_p50?: number | null; cost_per_nm_krw_2025?: number | null;
  peer_gap_pct_2025?: number | null; peer_gap_pct_forecast?: number | null; peer_cost_diff_per_nm_krw?: number | null;
}
export interface EconShip extends EconMeta { inputs: Record<string, number | string | null>; precomputed: EconRow[] }

let paramsP: Promise<EconParams> | null = null;
export const econParams = () => (paramsP ??= shared<EconParams>("/economics/params", undefined, 90000).catch((e) => { paramsP = null; throw e; }));
export const econShip = (imo: number) => shared<EconShip>(`/economics/ships/${imo}`, undefined, 90000);

export type EconScenario = "낮음" | "기준" | "높음";
const SUFFIX: Record<EconScenario, string> = { 낮음: "low", 기준: "base", 높음: "high" };

export function paramNum(p: EconParams, key: string): number | undefined {
  const v = Number(p.items.find((i) => i.key === key)?.value);
  return Number.isFinite(v) ? v : undefined;
}

/** 공용 서버 경제 지표를 입력 가격으로 변환. 값이 하나라도 없으면 적용하지 않는다 */
export function economicsPrices(p: EconParams, ship: EconShip, sc: EconScenario): Prices | undefined {
  const s = SUFFIX[sc];
  const fuel = Number(ship.inputs[`fuel_price_usd_per_t_${s}`]);
  const eua = paramNum(p, `eua_price_eur_per_t_${s}`);
  const fxu = paramNum(p, "fx_krw_per_usd"), fxe = paramNum(p, "fx_krw_per_eur");
  if (![fuel, eua, fxu, fxe].every((v) => typeof v === "number" && Number.isFinite(v) && v > 0)) return undefined;
  const base = { origin: "economics" as const, as_of: p.price_date, status: "provided" };
  const o = (source: string, basis?: string) => ({ ...base, source, basis });
  return {
    fuel_usd: fuel, eua_eur: eua, fx_usd: fxu, fx_eur: fxe,
    date: `공용 서버 경제 지표 (${sc}, ${p.price_date})`,
    src: {
      fuel_usd: o(`공용 서버 경제 지표 · ${sc} 시나리오`, "선박별 연료 가격 (연료 그룹·로테르담 기준)"),
      eua_eur: o(`공용 서버 경제 지표 · ${sc} 시나리오`),
      fx_usd: o("공용 서버 경제 지표 · 팀 고정 환율(초안)", "실시간 시장 환율이 아님"),
      fx_eur: o("공용 서버 경제 지표 · 팀 고정 환율(초안)", "실시간 시장 환율이 아님"),
    },
  };
}

export const CAUSE_KO: Record<string, string> = { price: "가격", sea_eff: "해상 효율", berth: "정박 배출", regulation: "규제", distance: "운항량" };

/** 사전계산 점검 플래그 (inputs.flag_*) → 설명 */
export const FLAG_TEXT: Record<string, string> = {
  flag_fuel_price_approx: "연료 가격을 근사값으로 채웠습니다",
  flag_no_fuel_price: "연료 가격이 없어 계산 정확도가 낮습니다",
  flag_short_sea_time: "해상 시간이 짧아 연간 값 변동이 큽니다",
  flag_berth_unusual: "정박 배출이 평소와 크게 다릅니다",
  flag_no_peer: "비교할 동급 기준값이 없습니다",
};
