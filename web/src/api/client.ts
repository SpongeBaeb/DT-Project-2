/**
 * 데이터 가져오기 한 곳.
 *  - 데이터에 있는 배: 정적 JSON (/data/...) — 서버 계산 없음
 *  - 사용자가 입력한 배: 진단 API (/api/... → vite 가 127.0.0.1:8000 으로 넘김)
 * 두 경로 모두 같은 DiagnosisResult 를 돌려준다.
 */
import type { DiagnoseRequest, DiagnosisResult, IndexEntry, Meta, ShipFile, WhatIfSpeedRequest, WhatIfSpeedResponse } from "./types";

const SERVER_DOWN = "서버에 연결할 수 없습니다. 프로젝트 폴더에서  uv run python tasks.py dev  를 실행했는지 확인하세요.";

/** 네트워크 자체가 실패하면(서버 꺼짐) 브라우저는 'TypeError: Failed to fetch' 만 준다 → 할 일을 알려 주는 문장으로 바꾼다 */
async function request(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch {
    throw new Error(SERVER_DOWN);
  }
}

async function getJson<T>(url: string): Promise<T> {
  const r = await request(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return (await r.json()) as T;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const r = await request(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  // vite 는 켜져 있고 API(8000)만 꺼져 있으면 프록시가 502/500 을 돌려준다
  if (r.status === 502 || r.status === 503 || (r.status === 500 && !(r.headers.get("content-type") ?? "").includes("json"))) {
    throw new Error("진단 API가 꺼져 있습니다. uv run python tasks.py dev  (또는 serve) 를 실행하세요.");
  }
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(typeof detail.detail === "string" ? detail.detail : JSON.stringify(detail.detail ?? r.status));
  }
  return (await r.json()) as T;
}

export const data = {
  meta: () => getJson<Meta>("/data/meta.json"),
  index: () => getJson<IndexEntry[]>("/data/index.json"),
  ship: (imo: number) => getJson<ShipFile>(`/data/ships/${imo}.json`),
};

export const api = {
  diagnose: (req: DiagnoseRequest) => postJson<DiagnosisResult>("/api/diagnose", req),
  whatIfSpeed: (req: WhatIfSpeedRequest) => postJson<WhatIfSpeedResponse>("/api/whatif/speed", req),
};
