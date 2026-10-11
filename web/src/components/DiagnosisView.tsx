/**
 * 진단 화면 (기획서 3-1 시안). 데이터에 있는 배와 입력한 배가 이 컴포넌트 하나를 같이 쓴다.
 * ① 비교 ② 원인 막대 ③ 추이 ④ 데이터 점검 ⑤ 예측 ⑥ 비용 — 각 칸은 담당자가 다듬는다.
 */
import type { DiagnosisResult, ShipInputs } from "../api/types";
import CostPanel from "./CostPanel";

type YearInput = ShipInputs["years"][number];

const pct = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`;
const n0 = (v: number) => Math.round(v).toLocaleString();

export default function DiagnosisView({ result: r, history, input }: { result: DiagnosisResult; history?: DiagnosisResult[]; input?: YearInput }) {
  return (
    <div className="grid">
      <Card n={1} title={`${r.year}년, 동급과 비교`}>
        <div className="kv"><span>해상 효율</span><b>{n0(r.sea.actual)}</b><span className="muted">vs 동급 중간 {n0(r.sea.peer_median)} kg CO₂/해리</span></div>
        <div className={`big ${r.sea.vs_peer_pct > 0 ? "worse" : "better"}`}>동급보다 {pct(r.sea.vs_peer_pct)}</div>
        <div className="muted small">같은 조건 예측 {n0(r.sea.expected)} 대비 {pct(r.sea.vs_expected_pct)}</div>
        <hr />
        <div className="kv"><span>정박 배출</span><b>{n0(r.berth.actual_t)}</b><span className="muted">vs 같은 조건 {n0(r.berth.expected_t)} t</span></div>
        <div className={r.berth.z >= 2 ? "big worse" : "big"}>예측의 {r.berth.ratio.toFixed(1)}배</div>
        {r.berth.hist_min != null && <div className="muted small">예년 {r.berth.hist_min.toFixed(2)}~{r.berth.hist_max!.toFixed(2)}배</div>}
      </Card>

      <Card n={2} title="해상 효율 차이의 원인 (합 = 동급 대비 차이)">
        <CauseBars causes={r.sea.causes} />
      </Card>

      <Card n={3} title="추이 (해상 효율, 동급 대비)">
        {history && history.length > 1 ? <Trend points={history.map((h) => ({ x: h.year, y: h.sea.vs_peer_pct }))} /> : <p className="muted">여러 해를 넣으면 추이가 보입니다.</p>}
        <div className="small">
          위치 z = {r.position.z == null ? "–" : r.position.z.toFixed(2)} ({r.position.n_years}년) · <b>{r.position.cls}</b>
          {r.position.note && <div className="muted">{r.position.note}</div>}
        </div>
      </Card>

      <Card n={4} title="데이터 점검">
        <ul className="checks">
          {r.checks.map((c) => <li key={c.rule} className={c.ok ? "" : "worse"}>{c.ok ? "✓" : "✗"} {c.rule}{c.detail && <span className="muted"> — {c.detail}</span>}</li>)}
          {r.signals.filter((s) => s.on).map((s) => <li key={s.code} className="worse">⚠ 착시 신호: {s.label}</li>)}
        </ul>
        {r.warnings.length > 0 && <ul className="muted small">{r.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
      </Card>

      <Card n={5} title="앞으로 1~3년 (중앙값과 80% 구간)">
        <table className="compact">
          <thead><tr><th>연도</th><th>10%</th><th>중앙</th><th>90%</th></tr></thead>
          <tbody>{r.forecast.map((f) => <tr key={f.year}><td>{f.year}</td><td className="num">{f.p10 == null ? "–" : n0(f.p10)}</td><td className="num"><b>{f.p50 == null ? "–" : n0(f.p50)}</b></td><td className="num">{f.p90 == null ? "–" : n0(f.p90)}</td></tr>)}</tbody>
        </table>
      </Card>

      <Card n={6} title="비용">
        {input ? <CostPanel result={r} input={input} /> : <p className="muted">입력값이 없어 비용을 계산할 수 없습니다.</p>}
      </Card>

      <p className="muted small full">모델 {r.model_version} · 데이터 {r.data_hash} · 분석은 인과가 아니라 연관이며, 결정은 사용자가 내립니다.</p>
    </div>
  );
}

function Card({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="card">
      <h3><span className="badge">{n}</span>{title}</h3>
      {children}
    </section>
  );
}

function CauseBars({ causes }: { causes: DiagnosisResult["sea"]["causes"] }) {
  const shown = causes.filter((c) => Math.abs(c.pct_points) >= 0.05);
  const max = Math.max(1, ...shown.map((c) => Math.abs(c.pct_points)));
  const total = causes.reduce((a, c) => a + c.log_contrib, 0);
  return (
    <div>
      {shown.map((c) => (
        <div key={c.factor} className="bar-row">
          <span className="bar-label">{c.label}</span>
          <svg viewBox="-100 0 200 14" preserveAspectRatio="none" className="bar">
            <line x1="0" x2="0" y1="0" y2="14" stroke="currentColor" opacity="0.3" />
            <rect x={c.pct_points < 0 ? (c.pct_points / max) * 100 : 0} y="2" height="10" width={(Math.abs(c.pct_points) / max) * 100} className={c.pct_points > 0 ? "fill-worse" : "fill-better"} />
          </svg>
          <span className="num small">{c.pct_points > 0 ? "+" : ""}{c.pct_points.toFixed(1)}</span>
        </div>
      ))}
      <div className="muted small">합 {(total * 100).toFixed(1)} (로그 %p) = ln(실제/동급 중간)</div>
    </div>
  );
}

function Trend({ points }: { points: { x: number; y: number }[] }) {
  const W = 300, H = 110, P = 22;
  const xs = points.map((p) => p.x), ys = [...points.map((p) => p.y), 0];
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const [y0, y1] = [Math.min(...ys) - 5, Math.max(...ys) + 5];
  const sx = (x: number) => P + ((x - x0) / Math.max(1, x1 - x0)) * (W - 2 * P);
  const sy = (y: number) => H - P - ((y - y0) / (y1 - y0)) * (H - 2 * P);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="trend">
      <line x1={P} x2={W - P} y1={sy(0)} y2={sy(0)} strokeDasharray="3 3" stroke="currentColor" opacity="0.4" />
      <text x={W - P} y={sy(0) - 3} textAnchor="end" className="axis">동급 중간</text>
      <polyline fill="none" stroke="var(--accent)" strokeWidth="2" points={points.map((p) => `${sx(p.x)},${sy(p.y)}`).join(" ")} />
      {points.map((p) => <circle key={p.x} cx={sx(p.x)} cy={sy(p.y)} r="3" fill="var(--accent)" />)}
      <text x={sx(x0)} y={H - 4} className="axis">{x0}</text>
      <text x={sx(x1)} y={H - 4} textAnchor="end" className="axis">{x1}</text>
    </svg>
  );
}
