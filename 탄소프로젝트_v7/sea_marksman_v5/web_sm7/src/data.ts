// 데이터 모양과 불러오기. 원본: python -m publish.web_sm → public/data/*.json
// 값은 팀 결과 표(형식 2.6)·비용 표 1~3 그대로이며 반올림만 했다. 해상 효율 = (CO₂ − 정박 중 CO₂) ÷ 항해 거리 (kg CO₂/해리)

export type FactorKey = "size" | "speed" | "hours" | "intra" | "age" | "fuel" | "ice" | "other" | "rest";
export const FACTORS: FactorKey[] = ["speed", "hours", "intra", "age", "fuel", "ice", "size", "other", "rest"];
export type SignalKey = "berth" | "short" | "fuel" | "report" | "special";
export const SIGNALS: SignalKey[] = ["berth", "short", "fuel", "report", "special"];
export type Grade = "A" | "B" | "C" | "D" | "E";
export const GRADES: Grade[] = ["A", "B", "C", "D", "E"];
/** [중앙값(p50), 10%, 90%] */
export type Band = [number, number, number];

export interface Ship {
  imo: number;
  ly: number; // 마지막 보고 연도 (진단 연도)
  n: string; // 선박명
  on?: string[]; // 옛 이름
  t: string; // 표준 선종 코드 (bulk, container …)
  dwt?: number;
  gt?: number;
  loa?: number;
  b?: number; // 건조연도
  age: number;
  co?: string; // 관리회사
  ice?: string;
  ek?: string; // 설계 효율 지표 종류
  ev?: number;
  fg?: string; // 연료 그룹: 석유계 | LNG 계열 | LPG 추정 | 기타 대체연료 | 대체연료(구분 불가)
  cpf?: number; // 연료 1톤당 CO₂
  co2: number;
  dist: number;
  hrs: number;
  spd: number;
  intra?: number; // EU 역내 비중
  ets?: number; // ETS 대상 CO₂ 비율
  co2pn: number; // 전체 거리당 CO₂
  cii?: Grade; // 그해 기준 CII 등급 (팀 파이프라인)
  cii26?: Grade; // 2026년 기준 CII 등급
  ciir?: number; // 2026년 기준선 대비 비율
  sea: number;
  peer: number; // 동급 중간
  exp: number; // 같은 조건 예측값
  sq: number; // 크기 4분위 (0~3)
  c: Record<FactorKey, number>; // 요인별 기여 (%p, ln×100). 합 = ln(실제/동급 중간)
  z?: number; // 위치 z
  zy: number;
  bt: number;
  be: number;
  br: number;
  bz: number; // 같은 조건 대비 정박 표준 점수
  brp?: [number, number]; // 예년 배수 범위
  bhz?: number; // 예년 대비 정박 표준 점수
  bs?: number;
  sig?: SignalKey[];
  fc?: Band[]; // 해상 효율 1~3년 예측
  fct?: Band[]; // 전체 효율(정박 포함) 1~3년 예측
  pde?: [number, number, number]; // 1~3년 뒤 CII D·E 확률
  pm?: number; // 다음 해 감축 요구 미달 확률
  lst?: "target" | "watch";
  lr?: number; // 리스트 안 순위
  pp?: number; // 유지 확률
  pup?: string;
  pdn?: string;
  tx?: number; // EU 규제 노출도 유형 1~3
  txp?: number;
  ta?: number; // 선령·설계 유형 1~3
  tap?: number;
  oo?: boolean; // 이상 운항
  w?: string[]; // 경고
}

// [연도, 해상 효율, 동급 중간, 정박 CO₂, 정박 같은 조건, 해상 시간, 전체 거리당 CO₂, 거리, 같은 조건 예측값, 위치 z, CII 등급, CII 비율(2026 기준), CO₂ 합계]
export type HistRow = [number, number, number, number, number, number, number, number, number, number | null, Grade | null, number | null, number];

// 비용 (백만 원). 행: [총비용 대표·하한·상한, 연료비, 탄소 비용, 동급 대비 차이, 총변화, 효율몫, 규제몫, 가격몫_연료, 가격몫_배출권, 총비용_가정B]
export type CostRow = [number, number, number, number, number, number, number, number, number, number, number, number];
export type Scenario = "낮음" | "기준" | "높음";
export interface ShipCost { b: [number, number, number]; fg?: string; k?: string; pg?: number; s?: Record<Scenario, CostRow[]> }

export interface TypeSummary { n: number; ships: number; r2: number; speed_elasticity: number; speed_is_wait: boolean }
export interface Acceptance {
  position?: { n_selected: number; n_single_year: number; retention_model: number; retention_single_year: number; retention_random: number; select_until?: number };
  verdict?: { criterion: string; value: number | null; threshold: string; pass: boolean }[];
  [k: string]: unknown;
}
export interface Meta {
  generated: string;
  base_year: number;
  n_ships: number;
  n_all: number;
  model_version: string;
  data_hash: string;
  result_table_version: string;
  sources?: string[];
  stages: string[];
  thresholds: { short_sea_hours: number; co2_per_fuel_min: number; cargo_dwt_ratio_max: number; min_speed_kn: number; berth_sigma: number; z_consistently_high: number; special_operators: string[] };
  main_engine_share: Record<string, number>;
  types: Record<string, TypeSummary>;
  factors: Record<FactorKey, string>;
  funnel: { all: number; clean: number; high: number; high_all: number };
  validation: Acceptance | null;
  list: { year: number; p_star: number | null; de_cut: number; watch_ratings: string[]; target: number; watch: number };
  type_names: { exposure: Record<string, string>; profile: Record<string, string> };
  persist: { groups: string[]; base_rate: number | null };
  illusions: {
    n: number;
    berth: { worst: number; mid: number; n_worst: number };
    speed: { slow_de: number; other_de: number };
    year: { n_jump: number; reverted: number };
    report: { ends5: number; mid: number; best: number; best_fuel: number | null };
  };
  cost: { unit: string; years: number[]; ets_share: Record<string, number>; settings: [string, string, string][]; prices: Record<string, string | number>[] };
}

let shipsP: Promise<Ship[]> | null = null;
let metaP: Promise<Meta> | null = null;
let histP: Promise<Record<string, HistRow[]>> | null = null;
let costP: Promise<Record<string, ShipCost>> | null = null;

const get = <T,>(f: string): Promise<T> =>
  fetch(`${import.meta.env.BASE_URL}data/${f}`).then((r) => {
    if (!r.ok) throw new Error(`${f}을(를) 불러오지 못했습니다 (${r.status}). python -m publish.web_sm 을 먼저 실행하세요.`);
    return r.json();
  });

export const loadShips = () => (shipsP ??= get<Ship[]>("ships.json"));
export const loadMeta = () => (metaP ??= get<Meta>("meta.json"));
export const loadHist = () => (histP ??= get<Record<string, HistRow[]>>("hist.json"));
export const loadCost = () => (costP ??= get<Record<string, ShipCost>>("cost.json"));

export const TYPE_KO: Record<string, string> = {
  container: "컨테이너선", bulk: "벌크선", tanker: "유조선", chemical_tanker: "화학제품운반선", general_cargo: "일반화물선",
  vehicle_carrier: "자동차운반선", ro_pax: "로팩스선", gas_carrier: "가스운반선", lng_carrier: "LNG운반선", ro_ro: "로로선",
  cruise: "크루즈선", reefer: "냉동화물선", container_ro_ro: "컨테이너·로로선",
};
export const typeKo = (t: string) => TYPE_KO[t] ?? t;

/** ln 차이(%p, ×100) → 실제 % 차이 */
export const lnPct = (lnx100: number) => (Math.exp(lnx100 / 100) - 1) * 100;
/** 동급 대비 차이 (%) */
export const vsPeer = (s: Pick<Ship, "sea" | "peer">) => (s.sea / s.peer - 1) * 100;
/** 같은 조건 예측값 대비 차이 (%) */
export const vsExp = (s: Pick<Ship, "sea" | "exp">) => (s.sea / s.exp - 1) * 100;

/** 같은 선종 안 크기 4분위 이름 */
export const SIZE_Q = ["1분위", "2분위", "3분위", "4분위"];

/** 동형선: 같은 선종, 건조연도 ±1년, 재화중량 ±3%, 길이 ±2% (기획서 용어 표) */
export function sistersOf(s: Ship, ships: Ship[]): Ship[] {
  if (!s.dwt || !s.loa || !s.b) return [];
  return ships.filter((x) => x.imo !== s.imo && x.ly === s.ly && x.t === s.t && x.b !== undefined && x.dwt && x.loa &&
    Math.abs(x.b - s.b!) <= 1 && Math.abs(x.dwt / s.dwt! - 1) <= 0.03 && Math.abs(x.loa / s.loa! - 1) <= 0.02);
}

export const isHigh = (s: Ship) => (s.z ?? -99) >= 2;
export const exposureName = (m: Meta, id?: number) => (id === undefined ? undefined : m.type_names.exposure[String(id)]);
export const profileName = (m: Meta, id?: number) => (id === undefined ? undefined : m.type_names.profile[String(id)]);
export const LIST_NAME = { target: "영업 타깃", watch: "관찰" } as const;
