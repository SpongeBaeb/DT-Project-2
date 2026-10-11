/**
 * 내 선박 진단 (6장) [담당: 박준재·장원우]
 * ① 직접 입력  ② IMO 로 불러와 수정 (#/my?imo=...)  ③ 파일 업로드(시간이 남으면)
 * 입력 → POST /diagnose → 같은 DiagnosisView. 입력값은 서버에 저장되지 않는다.
 */
import { useEffect, useState } from "react";
import { api, data } from "../api/client";
import type { DiagnoseRequest, DiagnosisResult, Meta, ShipInputs } from "../api/types";
import DiagnosisView from "../components/DiagnosisView";

type YearInput = ShipInputs["years"][number];

const EMPTY: DiagnoseRequest = {
  ship: { ship_type: "tanker", dwt: 100000, build_year: 2015 },
  years: [{ year: 2025, co2_t: 30000, berth_co2_t: 2000, distance_nm: 60000, sea_hours: 5000 }],
  mrv_basis_confirmed: false,
};

export default function MyShip({ meta }: { meta: Meta | null }) {
  const [req, setReq] = useState<DiagnoseRequest>(EMPTY);
  const [result, setResult] = useState<DiagnosisResult | null>(null);
  const [base, setBase] = useState<DiagnosisResult | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const imo = new URLSearchParams(window.location.hash.split("?")[1] ?? "").get("imo");
    if (imo) data.ship(Number(imo)).then((s) => { setReq({ ...s.inputs, mrv_basis_confirmed: true }); setBase(s.results.at(-1)!); });
  }, []);

  const last = req.years[req.years.length - 1];
  const setShip = (k: string, v: unknown) => setReq({ ...req, ship: { ...req.ship, [k]: v } });
  const setLast = (k: keyof YearInput, v: number | null) =>
    setReq({ ...req, years: [...req.years.slice(0, -1), { ...last, [k]: v } as YearInput] });

  async function run() {
    setBusy(true); setErr("");
    try { setResult(await api.diagnose(req)); } catch (e) { setErr(String(e)); setResult(null); } finally { setBusy(false); }
  }

  const num = (label: string, value: number | null | undefined, on: (v: number | null) => void, required = true) => (
    <label>{label}{required && " *"}
      <input type="number" value={value ?? ""} onChange={(e) => on(e.target.value === "" ? null : Number(e.target.value))} />
    </label>
  );

  return (
    <section>
      <h1>내 선박 진단</h1>
      <p className="muted small">EU MRV 보고 기준 값을 넣어 주세요. 앞 연도 {req.years.length - 1}개는 이력(위치·예측)에 쓰고, 마지막 연도를 진단합니다.</p>
      <div className="form">
        <label>선종 *
          <select value={req.ship.ship_type} onChange={(e) => setShip("ship_type", e.target.value)}>
            {(meta?.ship_types ?? ["tanker"]).map((t) => <option key={t}>{t}</option>)}
          </select>
        </label>
        {num("재화중량 t", req.ship.dwt, (v) => setShip("dwt", v))}
        {num("건조연도", req.ship.build_year, (v) => setShip("build_year", v))}
        {num("보고 연도", last.year, (v) => setLast("year", v))}
        {num("CO₂ t", last.co2_t, (v) => setLast("co2_t", v))}
        {num("정박 중 CO₂ t", last.berth_co2_t, (v) => {
          // 정박 배출만 바꾸는 가정: 해상 CO₂는 그대로, 전체 CO₂와 그에 비례하는 값(연료·ETS·역내)은 같은 비율로 함께 움직인다
          const co2 = last.co2_t + (v ?? 0) - last.berth_co2_t;
          const k = co2 / last.co2_t;
          const scale = (x: number | null | undefined) => (x == null ? x : x * k);
          setReq({ ...req, years: [...req.years.slice(0, -1), {
            ...last, berth_co2_t: v ?? 0, co2_t: co2,
            fuel_t: scale(last.fuel_t), ets_co2_t: scale(last.ets_co2_t), co2_intra_eu_t: scale(last.co2_intra_eu_t),
          }] });
        })}
        {num("항해 거리 해리", last.distance_nm, (v) => setLast("distance_nm", v))}
        {num("해상 시간 h", last.sea_hours, (v) => setLast("sea_hours", v))}
        {num("연료 t", last.fuel_t, (v) => setLast("fuel_t", v), false)}
        {num("EU 역내 CO₂ t", last.co2_intra_eu_t, (v) => setLast("co2_intra_eu_t", v), false)}
        {num("평균 적재량 t", last.cargo_t, (v) => setLast("cargo_t", v), false)}
        <label className="check"><input type="checkbox" checked={req.mrv_basis_confirmed} onChange={(e) => setReq({ ...req, mrv_basis_confirmed: e.target.checked })} /> EU MRV 보고 기준 값입니다</label>
        <button onClick={run} disabled={busy}>{busy ? "진단 중…" : "진단"}</button>
      </div>
      {err && <p className="error">{err}</p>}
      {result && base && (
        <p className="compare">원래 결과와 비교: 동급 대비 {base.sea.vs_peer_pct.toFixed(1)}% → <b>{result.sea.vs_peer_pct.toFixed(1)}%</b> · 정박 배수 {base.berth.ratio.toFixed(1)} → <b>{result.berth.ratio.toFixed(1)}</b></p>
      )}
      {result && <DiagnosisView result={result} input={last} />}
    </section>
  );
}
