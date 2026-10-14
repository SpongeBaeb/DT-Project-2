// 공용 서버 경제 계산 패널: 선박별 사전계산 비용(base 시나리오)을 우리 모델 결과와 나란히 보이고, 그 가격을 입력 가격으로 적용한다.
import { useEffect, useState } from "react";
import type { Scenario, Ship, ShipCost } from "../data";
import { CAUSE_KO, econParams, econShip, economicsPrices, FLAG_TEXT, type EconParams, type EconScenario, type EconShip } from "../economics";
import { setPrices } from "../store";
import { num, pct } from "../format";
import { Help } from "./ui";
import { Decomp, eok } from "../pages/Diagnosis";

type St = { p: EconParams; s: EconShip } | "loading" | { error: string };

export default function EconomicsPanel({ ship, ours, by, sc }: { ship: Ship; ours: ShipCost | null | undefined; by: number; sc: Scenario }) {
  const [st, setSt] = useState<St>("loading");
  const [applied, setApplied] = useState<EconScenario | null>(null);
  const [pick, setPick] = useState<EconScenario>("기준");
  const [yi, setYi] = useState(0);
  useEffect(() => {
    let alive = true;
    setSt("loading"); setApplied(null);
    Promise.all([econParams(), econShip(ship.imo)])
      .then(([p, s]) => alive && setSt({ p, s }))
      .catch((e) => alive && setSt({ error: String(e.message ?? e) }));
    return () => { alive = false; };
  }, [ship.imo]);

  if (st === "loading") return <section className="tc"><div className="tc-h"><div><h2>공용 서버 경제 계산</h2><p className="muted">불러오는 중입니다. 공용 서버가 유휴 상태면 30초 이상 걸릴 수 있습니다.</p></div></div></section>;
  if ("error" in st) return <section className="tc"><div className="tc-h"><div><h2>공용 서버 경제 계산</h2><p className="notice">{st.error.includes("404") || st.error.includes("없") ? "이 선박의 경제 계산 자료가 공용 서버에 없습니다." : st.error}</p></div></div></section>;

  const { p, s } = st;
  const rows = [...s.precomputed].filter((r) => r.price_scenario === "base").sort((a, b) => a.year - b.year);
  const mine = ours?.s?.[sc];
  const stale = !s.current_mrv_versions.includes(s.economic_mrv_version);
  const apply = () => {
    const pr = economicsPrices(p, s, pick);
    if (!pr) return;
    setPrices(pr);
    setApplied(pick);
  };
  const first = rows[0];
  const cur = rows[Math.min(yi, rows.length - 1)];
  const flags = Object.keys(FLAG_TEXT).filter((f) => Number(s.inputs[f]) === 1);
  return (
    <section className="tc">
      <div className="tc-h">
        <div>
          <h2>공용 서버 경제 계산</h2>
          <p>공용 서버가 사전계산한 {ship.n}의 연도별 비용입니다. 가격 기준일 {p.price_date} · 경제 자료 MRV {s.economic_mrv_version}{stale ? ` (현재 ${s.current_mrv_versions.join(", ")}과 다름)` : ""}. 단위 억 원.</p>
        </div>
      </div>
      <div className="dh-act" style={{ margin: "0 0 14px", alignItems: "center" }}>
        <div className="seg" role="tablist" aria-label="적용할 경제 지표 시나리오">
          {(["낮음", "기준", "높음"] as EconScenario[]).map((k) => <button key={k} role="tab" aria-selected={pick === k} className={pick === k ? "on" : ""} onClick={() => setPick(k)}>{k}</button>)}
        </div>
        <button className="btn ghost sm" onClick={apply}>이 가격을 입력 가격으로 적용</button>
        {applied && <span className="small muted">적용했습니다 ({applied}). 아래 계산이 연료 {num(Number(s.inputs[`fuel_price_usd_per_t_${{ 낮음: "low", 기준: "base", 높음: "high" }[applied]}`]), 0)} USD/t 기준으로 바뀝니다.</span>}
      </div>
      {rows.length === 0 ? <p className="notice">이 선박의 사전계산 비용이 없습니다.</p> : (
        <div className="tc-grid">
          <div className="card">
            <div className="tbl">
              <table className="t">
                <thead><tr><th>연도</th><th>연료비</th><th>탄소 비용</th><th>합계(중앙값)</th><th>80% 구간</th><th>{by} 대비</th><th>우리 모델 {sc}</th></tr></thead>
                <tbody>
                  {rows.map((r, i) => {
                    const m = mine?.[i]?.[0];
                    return (
                      <tr key={r.year} className={i === yi ? "sel" : ""} onClick={() => setYi(i)} style={{ cursor: "pointer" }}>
                        <td>{r.year}</td><td>{eok(r.fuel_cost_mkrw)}</td><td>{eok(r.carbon_cost_mkrw)}</td><td><b>{eok(r.total_cost_mkrw_p50)}</b></td>
                        <td>{eok(r.total_cost_mkrw_p10, 0)}~{eok(r.total_cost_mkrw_p90, 0)}</td>
                        <td className={r.change_vs_2025_mkrw_p50 > 0 ? "up" : "down"}>{r.change_vs_2025_mkrw_p50 >= 0 ? "+" : ""}{eok(r.change_vs_2025_mkrw_p50)}</td>
                        <td>{m !== undefined ? <>{eok(m)} <span className="muted small">({pct(((m - r.total_cost_mkrw_p50) / r.total_cost_mkrw_p50) * 100, 0)})</span></> : "–"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="card-foot">
              공용 서버 가격 가정(base): 연료 {first ? num(first.fuel_price_usd_per_t, 0) : "–"} USD/t · 배출권 {first ? num(first.eua_price_eur_per_t, 0) : "–"} EUR/t · 환율 {num(Number(p.items.find((i) => i.key === "fx_krw_per_usd")?.value), 0)}원/USD.
              우리 모델 열은 팀 비용표의 {sc} 시나리오이며, 가격 가정과 자료 판이 달라 차이가 날 수 있습니다. 연도를 누르면 오른쪽 분해가 바뀝니다.
            </p>
          </div>
          {cur && (
            <div className="card">
              <h3 style={{ marginBottom: 12 }}>{by}→{cur.year}년 비용 변화 원인 · 중앙값</h3>
              <Decomp
                parts={[["해상 효율", cur.effect_sea_eff_mkrw_p50 ?? 0], ["정박 배출", cur.effect_berth_mkrw_p50 ?? 0], ["규제 (부과율·CH₄·N₂O)", cur.effect_regulation_mkrw ?? 0], ["연료 가격", cur.effect_fuel_price_mkrw ?? 0], ["배출권 가격", cur.effect_eua_price_mkrw ?? 0]]}
                total={cur.change_vs_2025_mkrw_p50}
              />
              <dl className="srv-dl" style={{ marginTop: 14 }}>
                <div><dt>항해 1해리당 비용</dt><dd>{cur.cost_per_nm_krw_p50 ? `${num(cur.cost_per_nm_krw_p50, 0)}원` : "–"}{cur.cost_per_nm_krw_2025 ? <span className="muted small"> ({by}년 {num(cur.cost_per_nm_krw_2025, 0)}원)</span> : null}</dd></div>
                <div><dt>동급 대비 비용 차이</dt><dd>{cur.peer_cost_diff_mkrw !== null && cur.peer_cost_diff_mkrw !== undefined ? `${cur.peer_cost_diff_mkrw >= 0 ? "+" : ""}${eok(cur.peer_cost_diff_mkrw)}` : "–"}</dd></div>
                <div><dt>동급 대비 효율 격차</dt><dd>{cur.peer_gap_pct_2025 !== null && cur.peer_gap_pct_2025 !== undefined ? `${by}년 ${pct(cur.peer_gap_pct_2025)}` : "–"}{cur.peer_gap_pct_forecast !== null && cur.peer_gap_pct_forecast !== undefined ? ` → ${cur.year}년 ${pct(cur.peer_gap_pct_forecast)}` : ""}</dd></div>
                <div><dt>연료비 비중</dt><dd>{num(cur.fuel_cost_share_pct, 0)}%</dd></div>
              </dl>
              {flags.length > 0 && <ul className="warn-list" style={{ marginTop: 12 }}>{flags.map((f) => <li key={f}>{FLAG_TEXT[f] ?? f}</li>)}</ul>}
            </div>
          )}
        </div>
      )}
      <Help label="서버 안내와 가격 항목">
        <ul>{[...new Set(s.warnings)].map((w) => <li key={w}>{w}</li>)}</ul>
        <div className="tbl" style={{ marginTop: 10 }}>
          <table className="t">
            <thead><tr><th>항목</th><th>낮음</th><th>기준</th><th>높음</th></tr></thead>
            <tbody>
              <tr><td>연료 가격 (이 선박, USD/t)</td>{(["low", "base", "high"] as const).map((k) => <td key={k}>{num(Number(s.inputs[`fuel_price_usd_per_t_${k}`]), 1)}</td>)}</tr>
              <tr><td>배출권 (EUR/t)</td>{(["low", "base", "high"] as const).map((k) => <td key={k}>{num(Number(p.items.find((i) => i.key === `eua_price_eur_per_t_${k}`)?.value), 1)}</td>)}</tr>
            </tbody>
          </table>
        </div>
      </Help>
    </section>
  );
}
