// 내 선박 진단: 데이터에 없는 선박, 보고 전 당해 연도 값, 신조선 계획값을 팀 진단 API(POST /diagnose)로 진단한다.
// 여러 연도를 넣으면 마지막 연도를 진단하고 앞 연도는 위치 z·예측에 쓴다. 입력값은 저장하지 않는다(API도 저장하지 않음).
import { useEffect, useState } from "react";
import type { Meta, Ship } from "../data";
import { exposureName, profileName, typeKo, vsPeer } from "../data";
import { ApiError, causesOf, diagnose, shipInputs, type DiagnosisResult, type ShipInputs, type YearInput } from "../api";
import { go } from "../store";
import { num, pct, times } from "../format";
import { Card, CheckIcon, Empty, Help } from "../components/ui";
import Reticle from "../components/Reticle";
import { CauseBars } from "../components/charts";
import { FACTOR_NAME } from "./Home";
import { initialDiagnose, MRV_TYPE, type InitialResult } from "../shared";

/** 공용 서버 초기 모델 결과 (팀 모델 서버가 꺼져 있을 때 대체) */
function InitialView({ r }: { r: InitialResult }) {
  const m = Math.max(5, ...r.causes.map((c) => Math.abs(c.value * 100)));
  return (
    <Card title="공용 서버 초기 모델 결과" sub={`${r.model_version} · ${r.model_status}`}>
      <p className="notice" style={{ marginTop: 0 }}>팀 모델 진단 서버에 연결되지 않아 공용 서버의 초기 기준 모델(선종별 릿지 로그 선형)로 계산했습니다. 위치 z·1~3년 예측·착시 신호는 포함되지 않으며, 결과 표의 팀 모델 값과 다를 수 있습니다.</p>
      <div className="vs">
        <div><div className="k">해상 효율 (kg CO₂/해리)</div><div className="v">{num(r.sea.actual)}</div><div className="d">같은 조건 예측 {num(r.sea.expected)} 대비 <b className={r.sea.vs_expected_pct > 0 ? "up" : "down"}>{pct(r.sea.vs_expected_pct)}</b>{r.sea.peer_median ? ` · 동급 중간 ${num(r.sea.peer_median)} 대비 ${pct(r.sea.vs_peer_pct)}` : ""}</div></div>
        <div><div className="k">정박 배출 (톤/년)</div><div className="v">{num(r.berth.actual_t)}</div><div className="d">같은 조건 예측 {num(r.berth.expected_t)}톤의 {times(r.berth.ratio)}</div></div>
      </div>
      <h4 className="cl-h">요인 기여 ({r.cause_unit})</h4>
      {r.causes.map((c) => (
        <div key={c.key} className="dc-row"><span>{c.label}</span>
          <div className="dc-track"><span className="z" /><span className="f" style={{ background: c.value >= 0 ? "var(--signal)" : "var(--base)", left: c.value >= 0 ? "50%" : `${50 - (Math.abs(c.value * 100) / m) * 50}%`, width: `${(Math.abs(c.value * 100) / m) * 50}%` }} /></div>
          <span className="dc-v">{c.value >= 0 ? "+" : ""}{(c.value * 100).toFixed(1)}%p</span></div>
      ))}
      <ul className="checks" style={{ marginTop: 12 }}>{r.checks.map((c) => <li key={c.rule}><CheckIcon ok={c.ok} /><span>{c.rule}</span><span className="val">{c.ok ? "통과" : "확인 필요"}</span></li>)}</ul>
      {r.warnings.length > 0 && <ul className="warn-list">{r.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
      <p className="card-foot">데이터 해시 {r.data_hash.slice(0, 12)} · {r.model_basis}</p>
    </Card>
  );
}

const FUELS: Record<string, number> = { "중유(HFO)": 3.114, "경유(LFO)": 3.151, "선박용 경유(MGO/MDO)": 3.206, LNG: 2.75, 메탄올: 1.375 };
const ICE = ["IA Super", "IA", "IB", "IC", "PC7", "PC6", "PC5", "PC4", "PC3", "PC2", "PC1"];
const POS: Record<DiagnosisResult["position"]["cls"], string> = { consistently_high: "지속 초과", typical: "통상 범위", consistently_low: "지속 우수" };

type F = Record<string, string>;
const f = (v?: string) => (v === undefined || v.trim() === "" ? undefined : Number(v.replace(/,/g, "")));
const str = (v?: number | null) => (v === undefined || v === null ? "" : String(Math.round(v * 1000) / 1000));
const yearToForm = (y: YearInput): F => ({ year: String(y.year), co2: str(y.co2_t), berth: str(y.berth_co2_t), dist: str(y.distance_nm), hours: str(y.sea_hours), fuel: str(y.fuel_t), intra: str(y.co2_intra_eu_t), ets: str(y.ets_co2_t), cargo: str(y.cargo_t), fuel_kind: "" });
const EMPTY_YEAR: F = { year: "2025", co2: "", berth: "", dist: "", hours: "", fuel: "", intra: "", ets: "", cargo: "", fuel_kind: "" };
const EMPTY_SHIP: F = { type: "bulk", dwt: "", gt: "", built: "", loa: "", ice: "", eedi: "", ek: "", name: "" };

/** ships.json 한 행 → 입력 (API 없이 불러오기: 마지막 보고 연도 1개) */
function fromShip(s: Ship): ShipInputs {
  return {
    ship: { imo: s.imo, name: s.n, ship_type: s.t, dwt: s.dwt ?? 0, build_year: s.b ?? s.ly - s.age, gt: s.gt, length_m: s.loa, ice_class: s.ice, eedi: s.ev, eedi_kind: s.ek },
    years: [{ year: s.ly, co2_t: s.co2, berth_co2_t: s.bt, distance_nm: s.dist, sea_hours: s.hrs, fuel_t: s.cpf ? s.co2 / s.cpf : null, co2_intra_eu_t: s.intra !== undefined ? s.intra * s.co2 : null, ets_co2_t: s.ets !== undefined ? s.ets * s.co2 : null }],
  };
}

function yearOf(y: F): { v?: YearInput; missing: string[] } {
  const cpf = y.fuel_kind ? FUELS[y.fuel_kind] : undefined;
  const co2 = f(y.co2) ?? (f(y.fuel) !== undefined && cpf !== undefined ? f(y.fuel)! * cpf : undefined);
  const need: [string, unknown][] = [["연간 CO₂ (또는 연료량 + 연료 종류)", co2], ["정박 중 CO₂", f(y.berth)], ["항해 거리", f(y.dist)], ["해상 시간", f(y.hours)]];
  const missing = need.filter(([, v]) => v === undefined || Number.isNaN(v)).map(([k]) => `${y.year}년 ${k}`);
  if (missing.length || f(y.year) === undefined) return { missing };
  return { missing, v: { year: f(y.year)!, co2_t: co2!, berth_co2_t: f(y.berth)!, distance_nm: f(y.dist)!, sea_hours: f(y.hours)!, fuel_t: f(y.fuel) ?? null, co2_intra_eu_t: f(y.intra) ?? null, ets_co2_t: f(y.ets) ?? null, cargo_t: f(y.cargo) ?? null } };
}

function Result({ r, compact }: { r: { sea: number; peer: number; exp: number; bt: number; br: number }; compact?: boolean }) {
  const v = (r.sea / r.peer - 1) * 100;
  return (
    <>
      <div className="vs">
        <div><div className="k">해상 효율 (kg CO₂/해리)</div><div className="v">{num(r.sea)}</div><div className="d">동급 중간값 {num(r.peer)} 대비 <b className={v > 0 ? "up" : "down"}>{pct(v)}</b></div></div>
        <div><div className="k">정박 배출 (톤/년)</div><div className="v">{num(r.bt)}</div><div className="d">같은 조건 예측값의 {times(r.br)}</div></div>
      </div>
      <div style={{ marginTop: 12 }}><Reticle sea={r.sea} peer={r.peer} exp={r.exp} compact={compact} /></div>
    </>
  );
}

export default function MyShip({ ships, meta, imo }: { ships: Ship[]; meta: Meta; imo?: number }) {
  const src = imo ? ships.find((s) => s.imo === imo) : undefined;
  const [S, setS] = useState<F>(EMPTY_SHIP);
  const [Y, setY] = useState<F[]>([EMPTY_YEAR]);
  const [cur, setCur] = useState(0);
  const [loadMsg, setLoadMsg] = useState<string | null>(null);
  const [mrv, setMrv] = useState(true);
  const [link, setLink] = useState(true);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<DiagnosisResult | null>(null);
  const [runErr, setRunErr] = useState<string | null>(null);
  const [down, setDown] = useState(false);
  const [ini, setIni] = useState<InitialResult | null>(null);
  const [iniBusy, setIniBusy] = useState(false);
  const [imoQ, setImoQ] = useState("");

  const fill = (inp: ShipInputs) => {
    const sh = inp.ship;
    setS({ type: sh.ship_type, dwt: str(sh.dwt), gt: str(sh.gt), built: String(sh.build_year), loa: str(sh.length_m), ice: sh.ice_class ?? "", eedi: str(sh.eedi), ek: sh.eedi_kind ?? "", name: sh.name ?? "" });
    const ys = inp.years.map(yearToForm);
    setY(ys.length ? ys : [EMPTY_YEAR]);
    setCur(Math.max(0, ys.length - 1));
  };
  useEffect(() => {
    if (!imo) return;
    shipInputs(imo)
      .then((inp) => { fill(inp); setLoadMsg(`${inp.ship.name ?? `IMO ${imo}`}의 보고값 ${inp.years.length}개 연도(${inp.years[0].year}~${inp.years[inp.years.length - 1].year})를 불러왔습니다.`); })
      .catch((e) => {
        if (src) { fill(fromShip(src)); setLoadMsg(`진단 서버에 연결되지 않아 ${src.n}의 ${src.ly}년 값만 불러왔습니다. ${e instanceof ApiError ? e.message : ""}`); }
        else setLoadMsg(`IMO ${imo}를 불러오지 못했습니다. ${e instanceof ApiError ? e.message : ""}`);
      });
  }, [imo]); // eslint-disable-line react-hooks/exhaustive-deps

  const parsedYears = Y.map(yearOf);
  const missing = [
    ...(f(S.dwt) === undefined ? ["재화중량"] : []), ...(f(S.built) === undefined ? ["건조연도"] : []),
    ...parsedYears.flatMap((p) => p.missing),
  ];
  const yearsOk = parsedYears.every((p) => p.v);
  const dup = new Set(Y.map((y) => y.year)).size !== Y.length;
  const run = async () => {
    if (missing.length || !yearsOk || dup) return;
    setBusy(true); setRunErr(null); setDown(false); setIni(null);
    try {
      const r = await diagnose({
        ship: { imo: src?.imo ?? null, name: S.name || null, ship_type: S.type, dwt: f(S.dwt)!, build_year: f(S.built)!, gt: f(S.gt) ?? null, length_m: f(S.loa) ?? null, ice_class: S.ice || null, eedi: f(S.eedi) ?? null, eedi_kind: f(S.eedi) !== undefined ? S.ek || null : null },
        years: parsedYears.map((p) => p.v!), mrv_basis_confirmed: mrv,
      });
      setRes(r);
    } catch (e) { setRunErr(String((e as Error).message)); setRes(null); setDown(e instanceof ApiError && /연결|응답하지/.test(String((e as Error).message))); }
    setBusy(false);
  };

  const runInitial = async () => {
    const last = parsedYears[parsedYears.length - 1]?.v;
    if (!last) return;
    setIniBusy(true); setRunErr(null);
    try {
      setIni(await initialDiagnose({
        ship_type: MRV_TYPE[S.type] ?? S.type, report_year: last.year, built_year: f(S.built)!, dwt: f(S.dwt) ?? null, gt: f(S.gt) ?? null,
        co2_t: last.co2_t, berth_co2_t: last.berth_co2_t, distance_nm: last.distance_nm, sea_hours: last.sea_hours, fuel_t: last.fuel_t ?? null,
        intra_eu_share: last.co2_intra_eu_t != null ? Math.min(1, last.co2_intra_eu_t / last.co2_t) : null, ice_class: S.ice || null, mrv_basis: mrv,
      }));
    } catch (e) { setRunErr(String((e as Error).message)); }
    setIniBusy(false);
  };
  const y = Y[cur] ?? EMPTY_YEAR;
  const setYear = (k: string, v: string) => setY(Y.map((x, i) => (i === cur ? { ...x, [k]: v } : x)));
  const types = Object.keys(meta.types).sort((a, b) => typeKo(a).localeCompare(typeKo(b), "ko"));
  const seaPart = f(y.co2) !== undefined && f(y.berth) !== undefined ? f(y.co2)! - f(y.berth)! : undefined;
  const r = res;
  const rc = r ? causesOf(r) : undefined;
  const extW = r ? r.warnings : [];

  return (
    <div className="wrap">
      <div className="page-h">
        <h1>내 선박 진단</h1>
        <p>데이터에 없는 선박, 보고 전 당해 연도 값, 신조선 계획값을 입력해 결과 표와 동일한 모델(진단 API)로 진단합니다. 여러 연도를 입력하면 마지막 연도를 진단하고 이전 연도는 위치 z와 1~3년 예측에 반영합니다. 입력값은 저장하지 않습니다.</p>
      </div>
      <div className="my-grid">
        <aside className="my-form" aria-label="입력">
          <h3>IMO로 불러오기</h3>
          <form className="imo" onSubmit={(e) => { e.preventDefault(); if (imoQ.trim()) go(`/my?imo=${imoQ.trim()}`); }}>
            <input value={imoQ} onChange={(e) => setImoQ(e.target.value)} placeholder="IMO 번호 (예: 9776767)" inputMode="numeric" aria-label="IMO 번호" />
            <button className="btn ghost sm" type="submit">불러오기</button>
          </form>
          {loadMsg && <p className="small" style={{ marginTop: 8 }}>{loadMsg} 수정 후 진단을 실행하세요. <a href="#/my">비우기</a></p>}

          <h3>제원</h3>
          <div className="grid2">
            <label className="field full"><span className="req">선종</span><select value={S.type} onChange={(e) => setS({ ...S, type: e.target.value })}>{types.map((t) => <option key={t} value={t}>{typeKo(t)}</option>)}</select></label>
            <label className="field"><span className="req">재화중량 <span className="u">DWT</span></span><input type="number" value={S.dwt} onChange={(e) => setS({ ...S, dwt: e.target.value })} /></label>
            <label className="field"><span>총톤수</span><input type="number" value={S.gt} onChange={(e) => setS({ ...S, gt: e.target.value })} /><span className="hint">로팩스·크루즈·자동차운반선은 크기 기준</span></label>
            <label className="field"><span className="req">건조연도</span><input type="number" value={S.built} onChange={(e) => setS({ ...S, built: e.target.value })} /></label>
            <label className="field"><span>전장 <span className="u">m</span></span><input type="number" value={S.loa} onChange={(e) => setS({ ...S, loa: e.target.value })} /></label>
            <label className="field"><span>내빙 등급</span><select value={S.ice} onChange={(e) => setS({ ...S, ice: e.target.value })}><option value="">없음</option>{ICE.map((x) => <option key={x}>{x}</option>)}</select></label>
            <label className="field"><span>설계 효율 지표</span><select value={S.ek} onChange={(e) => setS({ ...S, ek: e.target.value })}><option value="">없음</option><option>EEDI</option><option>EEXI</option><option>EIV</option></select></label>
            <label className="field"><span>지표 값</span><input type="number" value={S.eedi} onChange={(e) => setS({ ...S, eedi: e.target.value })} /><span className="hint">gCO₂/t·nm</span></label>
          </div>

          <h3>연도별 보고값</h3>
          <div className="yr-tabs" role="tablist" aria-label="연도">
            {Y.map((x, i) => <button key={i} role="tab" aria-selected={i === cur} className={i === cur ? "on" : ""} onClick={() => setCur(i)}>{x.year || "연도"}{i === Y.length - 1 ? " · 진단" : ""}</button>)}
            <button className="add" onClick={() => { const last = Y[Y.length - 1]; const ny = { ...last, year: String((f(last.year) ?? 2024) + 1) }; setY([...Y, ny]); setCur(Y.length); }}>+ 연도</button>
            {Y.length > 1 && <button className="add" onClick={() => { setY(Y.filter((_, i) => i !== cur)); setCur(Math.max(0, cur - 1)); }}>선택 연도 삭제</button>}
          </div>
          <div className="grid2">
            <label className="field"><span className="req">보고 연도</span><input type="number" value={y.year} onChange={(e) => setYear("year", e.target.value)} /></label>
            <label className="field"><span className="req">연간 CO₂ <span className="u">톤</span></span><input type="number" value={y.co2} onChange={(e) => setYear("co2", e.target.value)} /><span className="hint">미상 시 연료량 + 연료 종류</span></label>
            <label className="field"><span className="req">정박 중 CO₂ <span className="u">톤</span></span><input type="number" value={y.berth} onChange={(e) => {
              const nb = e.target.value, co2 = f(y.co2), ob = f(y.berth), b2 = f(nb);
              setY(Y.map((x, i) => (i === cur ? { ...x, berth: nb, ...(link && co2 !== undefined && ob !== undefined && b2 !== undefined ? { co2: String(Math.round((co2 - ob + b2) * 10) / 10) } : {}) } : x)));
            }} /></label>
            <label className="field"><span className="req">항해 거리 <span className="u">해리</span></span><input type="number" value={y.dist} onChange={(e) => setYear("dist", e.target.value)} /></label>
            <label className="opt-line full"><input type="checkbox" checked={link} onChange={(e) => setLink(e.target.checked)} />정박 CO₂ 변경 시 연간 CO₂ 연동 (해상 부분 유지)</label>
            {seaPart !== undefined && <p className="small muted full">해상 CO₂ {num(seaPart)}톤{f(y.dist) ? ` · 해상 효율 ${num((seaPart * 1000) / f(y.dist)!, 1)} kg/해리` : ""}</p>}
            <label className="field"><span className="req">해상 시간</span><input type="number" value={y.hours} onChange={(e) => setYear("hours", e.target.value)} /><span className="hint">시간</span></label>
            <label className="field"><span>연료량 <span className="u">톤</span></span><input type="number" value={y.fuel} onChange={(e) => setYear("fuel", e.target.value)} /></label>
            <label className="field"><span>연료 종류</span><select value={y.fuel_kind} onChange={(e) => setYear("fuel_kind", e.target.value)}><option value="">선택 안 함</option>{Object.keys(FUELS).map((k) => <option key={k}>{k}</option>)}</select></label>
            <label className="field"><span>EU 역내 CO₂ <span className="u">톤</span></span><input type="number" value={y.intra} onChange={(e) => setYear("intra", e.target.value)} /></label>
            <label className="field"><span>ETS 대상 CO₂ <span className="u">톤</span></span><input type="number" value={y.ets} onChange={(e) => setYear("ets", e.target.value)} /></label>
            <label className="field"><span>평균 적재량 <span className="u">톤</span></span><input type="number" value={y.cargo} onChange={(e) => setYear("cargo", e.target.value)} /></label>
          </div>
          <label className="opt-line" style={{ marginTop: 16 }}><input type="checkbox" checked={mrv} onChange={(e) => setMrv(e.target.checked)} />EU MRV 보고 기준 값 (EU 관련 항해만)</label>
          {missing.length > 0 && <p className="small muted" style={{ marginTop: 10 }}>미입력 필수 항목: {missing.join(", ")}</p>}
          {dup && <p className="small muted" style={{ marginTop: 10 }}>보고 연도가 중복되었습니다.</p>}
          <button className="btn target" style={{ marginTop: 14, width: "100%" }} disabled={busy || missing.length > 0 || !yearsOk || dup} onClick={run}>{busy ? "진단 중…" : "진단 실행"}</button>
          {runErr && <p className="notice">{runErr}</p>}
          {down && <button className="btn ghost" style={{ marginTop: 8, width: "100%" }} disabled={iniBusy} onClick={runInitial}>{iniBusy ? "공용 서버 계산 중… (첫 응답 30초 이상)" : "공용 서버 초기 모델로 진단 (마지막 연도)"}</button>}
        </aside>

        <div className="my-res">
          {ini && !r ? <InitialView r={ini} /> : !r || !rc ? (
            <div className="card"><Empty title="필수 항목 입력 후 진단을 실행하세요"><p>동급 대비 해상 효율, 차이 요인 분해, 위치 z, 1~3년 예측, 데이터 점검 결과를 표시합니다.</p></Empty></div>
          ) : (
            <>
              {(!mrv || extW.length > 0 || r.position.note) && (
                <div className="notice" style={{ margin: 0 }}>
                  {!mrv && <p><b>기준 불일치:</b> 모델은 EU 관련 항해 값으로 학습되었습니다. 전체 항해 값 입력 시 비교가 정확하지 않습니다.</p>}
                  {extW.map((w) => <p key={w}>{w}</p>)}
                  {r.position.note && <p>{r.position.note}</p>}
                </div>
              )}
              <Card title="동급 대비 해상 효율" sub={`${typeKo(r.ship_type)} · 크기 ${r.size_bin}분위 · ${r.year}년`}>
                {src && src.ly === r.year ? (
                  <div className="cmp2">
                    <div><h3 style={{ marginBottom: 8 }}>보고값 ({src.ly})</h3><Result r={{ sea: src.sea, peer: src.peer, exp: src.exp, bt: src.bt, br: src.br }} compact /></div>
                    <div><h3 style={{ marginBottom: 8 }}>입력값</h3><Result r={{ sea: r.sea.actual, peer: r.sea.peer_median, exp: r.sea.expected, bt: r.berth.actual_t, br: r.berth.ratio }} compact /></div>
                  </div>
                ) : <Result r={{ sea: r.sea.actual, peer: r.sea.peer_median, exp: r.sea.expected, bt: r.berth.actual_t, br: r.berth.ratio }} />}
                <p className="card-foot">같은 조건 예측값 {num(r.sea.expected)} kg/해리 대비 {pct(r.sea.vs_expected_pct)}.{src && src.ly === r.year ? ` 보고값 기준 동급 대비 ${pct(vsPeer(src))}.` : ""}</p>
              </Card>
              <Card title="차이 요인 분해"><CauseBars c={rc} names={FACTOR_NAME} speedWait={meta.types[r.ship_type]?.speed_is_wait ?? false} /></Card>
              <div className="two">
                <Card title="위치 z" sub={`${r.position.n_years}개 연도`}>
                  <div className="cb-big" style={{ color: "var(--ink)" }}>{r.position.z === null ? "–" : r.position.z.toFixed(1)}</div>
                  <p className="small">{POS[r.position.cls]}{r.position.n_years < 2 ? " · 단년 입력이므로 참고용" : ""}</p>
                </Card>
                <Card title="1~3년 해상 효율 예측" sub="중앙값 · 80% 구간">
                  {r.forecast.some((x) => x.p50 !== null) ? (
                    <table className="t"><tbody>{r.forecast.map((x) => <tr key={x.year}><td>{x.year}</td><td><b>{num(x.p50)}</b></td><td>{num(x.p10)}~{num(x.p90)}</td></tr>)}</tbody></table>
                  ) : <p className="muted small">예측 대상 조건에 미달합니다.</p>}
                </Card>
              </div>
              <Card title="데이터 점검" sub={r.signals.some((x) => x.on) ? `착시 신호 ${r.signals.filter((x) => x.on).length}건` : "착시 신호 없음"}>
                <ul className="checks">
                  {r.checks.map((c) => <li key={c.rule}><CheckIcon ok={c.ok} /><span>{c.rule}{c.detail && <small>{c.detail}</small>}</span><span className="val">{c.ok ? "통과" : "확인 필요"}</span></li>)}
                  {r.signals.map((x) => <li key={x.code}><CheckIcon ok={!x.on} /><span>{x.label}</span><span className="val">{x.on ? "해당" : "–"}</span></li>)}
                  <li><CheckIcon ok={!r.types.ops_outlier} /><span>이상 운항 (선종별 운항 군집에서 먼 상위 2.5%)</span><span className="val">{r.types.ops_outlier ? "해당" : "–"}</span></li>
                </ul>
                <p className="card-foot">유형: {exposureName(meta, r.types.exposure ?? undefined) ?? "–"} · {profileName(meta, r.types.age_design ?? undefined) ?? "선령·설계 유형 미산출(설계 효율 값 없음)"}</p>
              </Card>
              <Help label="산정 방식">
                <p>진단 API(POST /diagnose) 응답입니다. 결과 표와 같은 전처리·모델 코드를 사용하므로, 데이터에 있는 선박의 보고값을 그대로 넣으면 진단 화면과 같은 값이 나옵니다. 모델 {r.model_version} · 데이터 {r.data_hash}.</p>
                <p>감속 효과는 비용 계산의 속력 변경(물리 규칙)으로 산정하십시오. 평균 속력 계수에는 대기 시간이 포함되어 있습니다.</p>
              </Help>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
