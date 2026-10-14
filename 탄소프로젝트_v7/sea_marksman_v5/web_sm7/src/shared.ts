// 팀 공용 백엔드 (Ship Retrofit Analysis API 0.3.0, Render). 개발 서버가 /shared 를 BACKEND_URL 로 넘긴다.
// 쓰는 곳: 시장 가격(환율·EUA·연료·에너지·운임), 군집 상세·유사 선박, 초기 모델 진단(팀 모델 서버가 꺼져 있을 때 대체).
// 무료 서버라 유휴 상태에서 첫 응답이 30초 이상 걸릴 수 있다.
const BASE = (import.meta.env.VITE_SHARED_BASE as string | undefined)?.replace(/\/$/, "") || `${import.meta.env.BASE_URL}shared`;

export class SharedError extends Error {}

export async function shared<T>(path: string, body?: unknown, timeoutMs = 60000): Promise<T> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(`${BASE}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body), signal: ctl.signal,
    });
    let j: any; // eslint-disable-line @typescript-eslint/no-explicit-any
    try { j = await r.json(); } catch { throw new SharedError("공용 서버 응답을 읽지 못했습니다."); }
    if (!r.ok) {
      const d = Array.isArray(j?.detail) ? j.detail.map((e: { loc?: string[]; msg: string }) => `${(e.loc ?? []).slice(1).join(".") || "입력"}: ${e.msg}`).join(" · ") : j?.detail;
      throw new SharedError(d || `공용 서버 요청 실패 (${r.status})`);
    }
    return j as T;
  } catch (e) {
    if (e instanceof SharedError) throw e;
    throw new SharedError("공용 서버에 연결하지 못했습니다. 네트워크 또는 서버 상태를 확인하세요.");
  } finally { clearTimeout(t); }
}

// ── 시장 지표 ──
export type MarketStatus = "live" | "stale" | "historical" | "unavailable" | "mock";
export interface MarketPoint {
  metric: string; value: number | null; unit: string | null; as_of_date: string | null; fetched_at: string; source: string; status: MarketStatus;
  reason?: string | null; port?: string | null; source_url?: string | null; price_basis?: string | null; frequency?: string | null; source_file?: string | null;
}
export interface MarketSeries { metric: string; unit: string; source: string; items: { as_of_date: string; value: number }[]; total: number; has_more: boolean; source_url?: string; price_basis?: string }

export const marketFx = () => shared<{ usd_krw: MarketPoint; eur_krw: MarketPoint; eur_usd?: MarketPoint }>("/market/fx");
export const marketCarbon = () => shared<{ eua: MarketPoint }>("/market/carbon");
export const marketFuel = () => shared<{ vlsfo: MarketPoint; mgo?: MarketPoint; ifo380?: MarketPoint }>("/market/fuel");
export const marketEnergy = () => shared<{ brent?: MarketPoint; lng_or_gas?: MarketPoint }>("/market/energy");
export const marketDryBulk = () => shared<{ bdi?: MarketPoint }>("/market/freight/dry-bulk");
export async function marketHistory(metric: string, max = 3000): Promise<MarketSeries> {
  const first = await shared<MarketSeries>(`/market/history?metric=${metric}&limit=1000&offset=0`);
  const items = [...first.items];
  let off = 1000;
  while (first.total > items.length && off < max) {
    const p = await shared<MarketSeries>(`/market/history?metric=${metric}&limit=1000&offset=${off}`);
    items.push(...p.items);
    off += 1000;
    if (!p.has_more) break;
  }
  return { ...first, items };
}

// ── 군집 상세 (기존 cluster.sqlite, 2축 유형 + 유사 선박) ──
export interface ClusterAxis { silhouette?: number | null; outlier_pct?: number | null; slow_steaming_pct?: number | null; design_good_pct?: number | null; design_poor_pct?: number | null; axis_name: string; type_id: number; type_name: string; description: string; n_ships: number; share_pct: number; intra_eu_pct: number; berth_pct: number; age: number; speed_kn: number; top_ship_types: string; co2nm_vs_peers_pct: number }
export interface ClusterDetail {
  ship: {
    exposure_prob_max: number; profile_prob_max: number | null; design_level?: string | null; design_rank_pct?: number | null; size_class?: string | null; cluster_run?: string;
    speed_vs_peers?: number | null; co2nm_vs_same_speed_pct?: number | null; co2nm_vs_peers_pct?: number | null; design_eff_vs_peers?: number | null;
    exposure_prob_1?: number | null; exposure_prob_2?: number | null; exposure_prob_3?: number | null; exposure_outlier?: number | null;
    profile_prob_1?: number | null; profile_prob_2?: number | null; profile_prob_3?: number | null; profile_outlier?: number | null;
    slow_steaming?: number | null; speed_kn?: number | null; intra_eu_share?: number | null; berth_share?: number | null; age_life_ratio?: number | null;
  };
  exposure: ClusterAxis; profile: ClusterAxis | null;
  similar: { rank: number; similar_imo: number; name: string; ship_type: string; profile_name?: string; design_level?: string; age?: number }[];
}
export const clusterOf = (imo: number) => shared<ClusterDetail>(`/ships/${imo}/cluster`);

// ── 초기 모델 진단 (sea-baseline-1.0.0) ──
export interface InitialInputs {
  ship_type: string; report_year: number; built_year: number; dwt?: number | null; gt?: number | null; co2_t: number; berth_co2_t: number;
  distance_nm: number; sea_hours: number; fuel_t?: number | null; co2_per_fuel?: number | null; intra_eu_share?: number | null; ice_class?: string | null; mrv_basis: boolean;
}
export interface InitialResult {
  status: string; model_version: string; data_hash: string; model_status: string; model_basis: string;
  sea: { actual: number; expected: number; peer_median?: number; peer_n?: number; vs_peer_pct?: number; vs_expected_pct: number };
  berth: { actual_t: number; expected_t: number; ratio?: number };
  causes: { key: string; label: string; value: number }[]; cause_unit: string;
  warnings: string[]; checks: { rule: string; ok: boolean }[];
  validation?: { n_test: number; sea?: { mae: number; median_baseline_mae: number; r2?: number } };
}
export interface InitialModelInfo { model_version: string; data_hash: string; generated_at: string; model_kind: string; validation_method: string; limitations: string[]; types: Record<string, { basis: string; n_records: number; n_ships: number; validation: { n_test: number; sea?: { mae: number; median_baseline_mae: number; r2?: number } } }> }
export const initialDiagnose = (i: InitialInputs) => shared<InitialResult>("/diagnose", i);
export const initialModel = () => shared<InitialModelInfo>("/diagnose/model");
export const sharedHealth = () => shared<{ status: string }>("/health", undefined, 90000);

/** 표준 선종 코드 → 공용 서버(원본 MRV) 선종 이름 */
export const MRV_TYPE: Record<string, string> = {
  bulk: "Bulk carrier", tanker: "Oil tanker", chemical_tanker: "Chemical tanker", container: "Container ship", general_cargo: "General cargo ship",
  vehicle_carrier: "Vehicle carrier", ro_pax: "Ro-pax ship", gas_carrier: "Gas carrier", lng_carrier: "LNG carrier", ro_ro: "Ro-ro ship",
  cruise: "Cruise passenger ship", reefer: "Refrigerated cargo carrier", container_ro_ro: "Container/ro-ro cargo ship",
};

// ── 선박 전체 상세 (/ships/{imo}): 서버가 MRV 원자료로 계산한 CII 값, 규제 평가, 군집 ──
export interface ShipAnalysis {
  data_year: number; calculation_mode: string;
  values: Record<string, number | string | null>;
  regulatory_assessment: {
    status: string; config_version?: string; note?: string;
    results: { rule_id: string; metric: string; status: string; reason?: string | null; predicted_value: number | null; threshold: number | null; exceed_when: string; unit: string; reference_year: number; source: string }[];
  };
  miss_probability_assessment: { status: string; target_year: number; required_improvement: number | null; p_miss: number | null; p_star: number | null; p_star_basis_year?: number; missing_inputs?: string[]; note?: string };
  warnings?: string[];
}
export interface ShipDetail {
  imo: string; ship_name?: string; data_year?: number;
  source_record: Record<string, string | number | null>;
  analysis: ShipAnalysis;
  warnings?: string[];
}
export const shipDetail = (imo: number) => shared<ShipDetail>(`/ships/${imo}`, undefined, 90000);

// ── 군집 유형·품질 ──
export interface ClusterType { axis: "exposure" | "profile"; axis_name: string; type_id: number; type_name: string; description: string; n_ships: number; share_pct: number }
export interface ClusterRun { cluster_run: string; axis: string; axis_name: string; method: string; n_types: number; variables: string; n_ships: number; silhouette: number; stability_mean: number; stability_min: number; ari_ship_type: number; rule_accuracy: number; base_year: number; window: string }
export interface ClusterCoverage { ships_total: number; matched: number; cluster_total: number; profile_missing: number; ships_without_cluster: number; cluster_without_ship: number }
export const clusterTypes = () => shared<ClusterType[]>("/cluster/types");
export const clusterRuns = () => shared<ClusterRun[]>("/cluster/runs");
export const clusterCoverage = () => shared<ClusterCoverage>("/cluster/coverage");
