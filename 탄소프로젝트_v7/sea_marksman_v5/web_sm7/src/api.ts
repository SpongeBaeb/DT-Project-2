// 팀 진단 API (api/main.py) 연결. 모양은 contracts/api.py 와 같다.
// 개발 서버는 /api 를 http://127.0.0.1:8000 으로 넘긴다 (vite.config.ts). 다른 주소는 VITE_API_BASE 로 지정.
import type { FactorKey } from "./data";

export interface ShipStatic { imo?: number | null; name?: string | null; ship_type: string; dwt: number; build_year: number; gt?: number | null; length_m?: number | null; ice_class?: string | null; eedi?: number | null; eedi_kind?: string | null }
export interface YearInput { year: number; co2_t: number; berth_co2_t: number; distance_nm: number; sea_hours: number; fuel_t?: number | null; co2_intra_eu_t?: number | null; ets_co2_t?: number | null; cargo_t?: number | null }
export interface ShipInputs { ship: ShipStatic; years: YearInput[] }
export interface DiagnoseRequest extends ShipInputs { mrv_basis_confirmed: boolean }

export interface DiagnosisResult {
  model_version: string;
  data_hash: string;
  imo: number | null;
  year: number;
  ship_type: string;
  size_bin: number;
  checks: { rule: string; ok: boolean; detail: string }[];
  sea: { actual: number; expected: number; peer_median: number; vs_peer_pct: number; vs_expected_pct: number; causes: { factor: string; label: string; log_contrib: number; pct_points: number }[] };
  berth: { actual_t: number; expected_t: number; ratio: number; z: number; hist_min: number | null; hist_max: number | null; hist_z: number | null };
  position: { z: number | null; n_years: number; cls: "consistently_high" | "typical" | "consistently_low"; note: string };
  signals: { code: string; label: string; on: boolean }[];
  types: { exposure: number | null; age_design: number | null; ops_outlier: boolean };
  forecast: { year: number; p10: number | null; p50: number | null; p90: number | null }[];
  warnings: string[];
}

const BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") || `${import.meta.env.BASE_URL}api`;

export class ApiError extends Error {}

async function call<T>(p: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${BASE}${p}`, init);
  } catch {
    throw new ApiError("진단 서버에 연결할 수 없습니다. run_sea_marksman_v5.bat 으로 실행했는지 확인하세요.");
  }
  if (!r.ok) {
    let msg = `${r.status}`;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : Array.isArray(j.detail) ? j.detail.map((d: { msg: string; loc?: string[] }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join(" / ") : msg;
    } catch { /* 본문 없음 */ }
    if (r.status === 502 || r.status === 504) throw new ApiError("진단 서버가 응답하지 않습니다. run_sea_marksman_v5.bat 으로 실행했는지 확인하세요.");
    throw new ApiError(msg);
  }
  return r.json();
}

export const health = () => call<{ status: "ok"; model_version: string; data_hash: string }>("/health");
export const shipInputs = (imo: number) => call<ShipInputs>(`/ships/${imo}/inputs`);
export const diagnose = (req: DiagnoseRequest) =>
  call<DiagnosisResult>("/diagnose", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) });

/** 결과의 원인 막대 → 화면 요인 키 (%p) */
const KEY: Record<string, FactorKey> = { size: "size", speed_pattern: "speed", sea_time: "hours", eu_exposure: "intra", age_design: "age", fuel: "fuel", ice: "ice", other: "other", unexplained: "rest" };
export function causesOf(r: DiagnosisResult): Record<FactorKey, number> {
  const c = { size: 0, speed: 0, hours: 0, intra: 0, age: 0, fuel: 0, ice: 0, other: 0, rest: 0 } as Record<FactorKey, number>;
  for (const x of r.sea.causes) if (KEY[x.factor]) c[KEY[x.factor]] += x.pct_points;
  return c;
}

// ── AIS 현재 위치 (서버가 aisstream.io 에서 모아 둔 값) ──
export interface AisPosition {
  imo: number;
  status: "ok" | "stale" | "waiting" | "no_position" | "no_key";
  connected: boolean;
  mmsi?: number;
  lat?: number; lon?: number;
  sog?: number | null; cog?: number | null; heading?: number | null;
  nav_status?: string | null;
  age_s?: number;
  received_at?: number;
  name?: string | null;
  destination?: string | null;
  eta?: { Month?: number; Day?: number; Hour?: number; Minute?: number } | null;
  draught?: number | null;
}
export async function aisOf(imo: number): Promise<AisPosition> {
  const r = await fetch(`${BASE}/ais/${imo}`);
  if (!r.ok) throw new ApiError(`AIS 조회 실패 (${r.status})`);
  return r.json();
}
