// CII 한 글자가 만드는 네 가지 착시와 Sea Marksman의 해결 (발표 A 파트 4장)
//   ① 정박이 섞인다 → 해상 효율 + 정박 별도 비교     ② 조건이 다른 배와 비교된다 → 같은 조건 예측 + 원인 막대
//   ③ 한 해 값은 출렁인다 → 위치 z (여러 해, 줄여 잡기)   ④ 보고 오류·특수 운항 → 착시 신호 5종 표시
import type { ReactNode } from "react";
import type { Grade, HistRow, Meta, Ship } from "../data";
import { vsExp, vsPeer } from "../data";
import { num, pct, times } from "../format";
import { Grade_, SIGNAL_PLAIN } from "./ui";

export const ILLUSIONS = [
  { k: "berth", n: "①", name: "정박이 섞인다", why: "CII = CO₂ ÷ (크기 × 거리). 항구에서 쓴 연료는 CO₂에 더해지지만 거리는 늘리지 않습니다.", fix: "정박을 뺀 해상 효율로 비교하고, 정박 배출은 같은 조건 예측·예년과 따로 비교합니다." },
  { k: "cond", n: "②", name: "조건이 다른 배와 비교된다", why: "크기·속력·선령이 다른 배가 같은 기준선에 놓입니다. 느린 배의 등급에는 대기 같은 운항 사정이 섞입니다.", fix: "같은 선종·연도·크기의 동급과 같은 조건 예측값으로 비교하고, 차이를 요인별 원인 막대로 나눕니다." },
  { k: "year", n: "③", name: "한 해 값은 출렁인다", why: "한 해의 값은 운항 사정에 크게 흔들려, 크게 나빠진 배의 약 절반이 이듬해 되돌아갑니다.", fix: "여러 해의 같은 조건 대비 차이를 모아 줄여 잡은 위치 z로 판정합니다. 2 이상이면 지속 초과입니다." },
  { k: "report", n: "④", name: "보고 오류·특수 운항", why: "선사 보고값에는 단위 실수, 화석연료 범위 밖 연료 계수, 짧은 EU 구간, 셔틀 탱커 같은 특수 운항이 섞입니다.", fix: "착시 신호 5종을 숫자 옆에 표시합니다. 값을 고치거나 숨기지 않고 표시만 합니다." },
] as const;
export type IllusionKey = (typeof ILLUSIONS)[number]["k"];

const GRADE_COLOR: Record<Grade, string> = { A: "var(--gA)", B: "var(--gB)", C: "var(--gC)", D: "var(--gD)", E: "var(--gE)" };

/** 연도별 CII 비율(2026 기준선 대비) 막대, 색 = 등급 */
export function CiiYears({ hist, height = 150 }: { hist: HistRow[]; height?: number }) {
  const rows = hist.filter((r) => r[11] !== null && r[11] !== undefined) as (HistRow & { 11: number })[];
  if (!rows.length) return <p className="muted small">CII 등급 산정 대상이 아닙니다.</p>;
  const top = Math.max(1.2, ...rows.map((r) => r[11])) * 1.12;
  const W = 600, H = height, pl = 8, pr = 92, pt = 22, pb = 26;
  const bw = Math.min(54, ((W - pl - pr) / rows.length) * 0.62);
  const sx = (i: number) => pl + ((i + 0.5) / rows.length) * (W - pl - pr);
  const sy = (v: number) => pt + (1 - v / top) * (H - pt - pb);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart cii-years" role="img" aria-label={`연도별 CII 등급 ${rows.map((r) => `${r[0]}년 ${r[10] ?? "-"}`).join(", ")}`}>
      <line x1={pl} x2={W - pr} y1={sy(1)} y2={sy(1)} className="grid" strokeDasharray="4 4" />
      <text x={W - pr + 8} y={sy(1) + 4} className="ax">2026 기준선</text>
      {rows.map((r, i) => (
        <g key={r[0]}>
          <rect x={sx(i) - bw / 2} y={sy(r[11])} width={bw} height={Math.max(2, sy(0) - sy(r[11]))} rx={4} fill={r[10] ? GRADE_COLOR[r[10]] : "var(--rule)"} />
          <text x={sx(i)} y={sy(r[11]) - 6} textAnchor="middle" className="lbl b">{r[10] ?? "–"}</text>
          <text x={sx(i)} y={H - 8} textAnchor="middle" className="ax">{r[0]}</text>
        </g>
      ))}
    </svg>
  );
}

interface Card { on: boolean; head: ReactNode; body: ReactNode }

/** 한 척의 네 가지 착시 점검 */
export function illusionCards(s: Ship, meta: Meta): Record<IllusionKey, Card> {
  const vp = vsPeer(s), ve = vsExp(s);
  const exBerth = s.ciir !== undefined && s.bs !== undefined ? s.ciir * (1 - s.bs) : undefined;
  const berthOn = !!s.sig?.includes("berth");
  const condGap = Math.abs(vp - ve);
  const condOn = condGap >= 10 || (Math.sign(vp) !== Math.sign(ve) && Math.abs(vp) >= 5);
  const yearOn = Math.abs(ve) >= 10 && (s.z === undefined || Math.abs(s.z) < meta.thresholds.z_consistently_high);
  const other = (s.sig ?? []).filter((x) => x !== "berth");
  const repOn = other.length > 0 || !!s.oo;
  return {
    berth: {
      on: berthOn,
      head: berthOn ? <>정박 배출이 예측의 <b>{times(s.br)}</b></> : <>정박 배출 정상 범위 ({times(s.br)})</>,
      body: <>연간 CO₂의 {Math.round((s.bs ?? 0) * 100)}%가 정박 중 배출.{exBerth !== undefined && s.ciir !== undefined ? <> 정박을 빼면 CII 비율 {s.ciir.toFixed(2)} → 약 <b>{exBerth.toFixed(2)}</b>.</> : null}</>,
    },
    cond: {
      on: condOn,
      head: <>동급 대비 <b>{pct(vp)}</b> · 같은 조건 대비 <b>{pct(ve)}</b></>,
      body: condOn ? <>크기·속력·운항 조건을 맞추면 차이가 {Math.abs(ve) < Math.abs(vp) ? "줄어듭니다" : "커집니다"}. 원인 막대에서 어느 조건이 차이를 만드는지 확인하세요.</> : <>조건을 맞춰도 차이가 비슷합니다. 동급 비교를 그대로 읽어도 됩니다.</>,
    },
    year: {
      on: yearOn,
      head: <>올해 {pct(ve)} · 위치 z <b>{s.z === undefined ? "–" : s.z.toFixed(1)}</b>{s.zy ? ` (${s.zy}년)` : ""}</>,
      body: yearOn ? <>올해 값은 크게 벗어났지만 여러 해로 보면 {s.z === undefined ? "판정할 자료가 부족합니다" : "통상 범위입니다"}. 한 해 값만으로 판단하지 않습니다.</>
        : s.z !== undefined && s.z >= meta.thresholds.z_consistently_high ? <>여러 해에 걸쳐 같은 조건보다 지속적으로 높습니다 (지속 초과).</> : <>올해 값과 여러 해 위치가 같은 방향입니다.</>,
    },
    report: {
      on: repOn,
      head: repOn ? <>{[...other.map((x) => SIGNAL_PLAIN[x][0]), ...(s.oo ? ["이상 운항"] : [])].join(" · ")}</> : <>보고값 이상 없음</>,
      body: repOn ? <>{other.length ? SIGNAL_PLAIN[other[0]][1] : "선종별 운항 군집에서 멀리 떨어진 운항 패턴"}. 등급과 비교 결과는 보고값 확인 후 해석하세요.</> : <>착시 신호 5종 중 정박 외 신호가 없습니다.</>,
    },
  };
}

/** 진단 화면: CII 한 글자 → 네 가지 착시 점검 */
export function IllusionCheck({ s, meta, hist }: { s: Ship; meta: Meta; hist: HistRow[] | null }) {
  const c = illusionCards(s, meta);
  const n = Object.values(c).filter((x) => x.on).length;
  return (
    <div className="ill">
      <div className="ill-top">
        <div className="ill-grade">
          <span className="k">{s.ly}년 CII</span>
          {s.cii ? <Grade_ g={s.cii} /> : <span className="muted">산정 대상 아님</span>}
          <p>{s.cii ? <>이 한 글자 뒤에서 착시 {n}건이 확인됩니다.</> : <>CII 대상이 아니어도 네 가지 점검은 같습니다.</>}</p>
        </div>
        <div className="ill-bars">{hist ? <CiiYears hist={hist} /> : <p className="muted">불러오는 중…</p>}</div>
      </div>
      <div className="ill-grid">
        {ILLUSIONS.map((x) => (
          <div key={x.k} className={`ill-card ${c[x.k].on ? "on" : ""}`}>
            <div className="ill-h"><span className="ill-n">{x.n}</span><b>{x.name}</b><span className={`ill-tag ${c[x.k].on ? "on" : ""}`}>{c[x.k].on ? "해당" : "해당 없음"}</span></div>
            <p className="ill-head">{c[x.k].head}</p>
            <p className="ill-body">{c[x.k].body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/** 홈: 네 가지 착시의 근거 수치 (기준 연도 전체) */
export function illusionEvidence(meta: Meta): Record<IllusionKey, ReactNode> {
  const I = meta.illusions;
  return {
    berth: <>CII 비율이 가장 나쁜 2.5%({num(I.berth.n_worst)}척)의 <b>{I.berth.worst}%</b>에 정박 신호. 가운데 50%는 {I.berth.mid}%.</>,
    cond: <>같은 선종 안에서 가장 느린 4분위의 D·E 비율 <b>{I.speed.slow_de}%</b>, 나머지 {I.speed.other_de}%.</>,
    year: <>해상 효율이 전년보다 20% 이상 나빠진 {num(I.year.n_jump)}건 중 <b>{I.year.reverted}%</b>가 이듬해 절반 이상 되돌아감.</>,
    report: <>CII가 가장 좋은 2.5%의 <b>{I.report.best}%</b>에 착시 신호. 착시는 나쁜 등급에만 있지 않습니다 (가운데 {I.report.mid}%).</>,
  };
}
