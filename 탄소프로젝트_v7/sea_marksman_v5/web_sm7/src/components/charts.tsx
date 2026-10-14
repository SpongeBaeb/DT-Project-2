// 진단 화면의 그래프 (SVG 직접 구현). 모든 그래프는 마우스를 올리면 아래 정보 줄에 값을 보여 준다.
import { useState, type ReactNode } from "react";
import type { Band, FactorKey } from "../data";
import { FACTORS, lnPct } from "../data";
import { num, pct, pp, times } from "../format";

const niceTicks = (lo: number, hi: number, n = 4) => {
  const raw = (hi - lo) / n, p = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
};

function Info({ children }: { children: ReactNode }) {
  return <div className="chart-info" aria-live="polite">{children}</div>;
}

// ── 원인 막대: 같은 조건 예측과 비교해 요인별로 나눈 동급 대비 차이. 막대 합 = 차이 ──
export function CauseBars({ c, se, names, speedWait }: { c: Record<FactorKey, number>; se?: Partial<Record<FactorKey, number>>; names: Record<FactorKey, string>; speedWait: boolean }) {
  const [hov, setHov] = useState<FactorKey | "sum" | null>(null);
  const label = (k: FactorKey) => (k === "speed" ? (speedWait ? "평균 속력 (대기 포함)" : "평균 속력") : names[k]);
  const rows = FACTORS.filter((k) => k === "rest" || Math.abs(c[k]) >= 0.05).sort((a, b) => (a === "rest" ? 1 : b === "rest" ? -1 : Math.abs(c[b]) - Math.abs(c[a])));
  const total = FACTORS.reduce((a, k) => a + c[k], 0);
  const m = Math.max(5, ...rows.map((k) => Math.abs(c[k])), Math.abs(total)) * 1.08;
  const W = 600, lw = 170, rw = 64, rowH = 30, H = (rows.length + 1) * rowH + 30;
  const sx = (v: number) => lw + ((v + m) / (2 * m)) * (W - lw - rw);
  const x0 = sx(0);
  const weak = (k: FactorKey) => k !== "rest" && se?.[k] !== undefined && Math.abs(c[k]) < 2 * se[k]!;
  const bar = (v: number, y: number, cls: string, faint: boolean) => {
    const a = Math.min(x0, sx(v)), w = Math.max(1.5, Math.abs(sx(v) - x0));
    const r = Math.min(4, w / 2);
    // 끝만 둥글게 (기준선 쪽은 각지게)
    const d = v >= 0
      ? `M${a},${y} h${w - r} q${r},0 ${r},${r} v${12 - 2 * r} q0,${r} ${-r},${r} h${-(w - r)} z`
      : `M${a + w},${y} h${-(w - r)} q${-r},0 ${-r},${r} v${12 - 2 * r} q0,${r} ${r},${r} h${w - r} z`;
    return <path d={d} className={cls} fill={v >= 0 ? "var(--signal)" : "var(--base)"} fillOpacity={faint ? 0.35 : 1} />;
  };
  const hv = hov === "sum" ? undefined : hov;
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="해상 효율 차이의 원인 막대">
        {niceTicks(-m, m, 4).map((t) => (
          <g key={t}>
            <line x1={sx(t)} x2={sx(t)} y1={6} y2={H - 22} className="grid" />
            <text x={sx(t)} y={H - 6} textAnchor="middle" className="ax">{t > 0 ? `+${t}` : t}</text>
          </g>
        ))}
        <line x1={x0} x2={x0} y1={4} y2={H - 22} className="zero" />
        {rows.map((k, i) => {
          const y = 10 + i * rowH;
          return (
            <g key={k} onMouseEnter={() => setHov(k)} onMouseLeave={() => setHov(null)}>
              <rect x={0} y={y - 8} width={W} height={rowH} fill="transparent" />
              <text x={lw - 10} y={y + 10} textAnchor="end" className={`lbl ${k === "rest" ? "b" : ""}`}>{label(k)}</text>
              {bar(c[k], y, "", weak(k))}
              <text x={c[k] >= 0 ? sx(c[k]) + 6 : sx(c[k]) - 6} y={y + 10} textAnchor={c[k] >= 0 ? "start" : "end"} className="lbl">{pp(c[k])}</text>
            </g>
          );
        })}
        {(() => {
          const y = 10 + rows.length * rowH;
          return (
            <g onMouseEnter={() => setHov("sum")} onMouseLeave={() => setHov(null)}>
              <line x1={lw - 160} x2={W} y1={y - 9} y2={y - 9} stroke="var(--rule)" />
              <text x={lw - 10} y={y + 10} textAnchor="end" className="lbl b">동급 대비 차이</text>
              <rect x={Math.min(x0, sx(total))} y={y + 3} width={Math.max(1.5, Math.abs(sx(total) - x0))} height={6} rx={2} fill="var(--ink)" />
              <text x={total >= 0 ? sx(total) + 6 : sx(total) - 6} y={y + 10} textAnchor={total >= 0 ? "start" : "end"} className="lbl b">{pp(total)}</text>
            </g>
          );
        })()}
      </svg>
      <Info>
        {hov === "sum" ? <><b>동급 대비 차이</b><span>{pp(total)} (로그 차이) = {pct(lnPct(total), 1)}</span><span>요인 기여의 합</span></>
          : hv ? <><b>{label(hv)}</b><span>{pp(c[hv])}</span>{hv === "rest" ? <span>속력·크기·선령 등으로 설명되지 않는 부분. 선체 오손·엔진 상태 등이 섞여 있음</span>
            : se?.[hv] !== undefined && <span>±{(2 * se[hv]!).toFixed(1)}%p (95% 신뢰구간){weak(hv) ? " · 유의하지 않음" : ""}</span>}</>
          : <span className="muted">빨강: 연료를 더 쓰게 한 요인 · 청록: 줄인 요인. 막대에 커서를 올리면 값이 보입니다.</span>}
      </Info>
    </>
  );
}

// ── 추이: 해마다 동급 중간 대비 해상 효율 ──
export function TrendChart({ rows }: { rows: { y: number; v: number }[] }) {
  const [hov, setHov] = useState<number | null>(null);
  if (rows.length < 2) return <p className="muted small">보고 연도가 하나라 추이를 그릴 수 없습니다.</p>;
  const W = 600, H = 220, pl = 46, pr = 52, pt = 18, pb = 30;
  const lo = Math.min(-10, ...rows.map((r) => r.v)) - 9, hi = Math.max(10, ...rows.map((r) => r.v)) + 6;
  const x0 = rows[0].y, x1 = rows[rows.length - 1].y;
  const sx = (y: number) => pl + ((y - x0) / Math.max(1, x1 - x0)) * (W - pl - pr);
  const sy = (v: number) => pt + ((hi - v) / (hi - lo)) * (H - pt - pb);
  const path = rows.map((r, i) => `${i ? "L" : "M"}${sx(r.y)},${sy(r.v)}`).join(" ");
  const h = rows.find((r) => r.y === hov);
  const colW = (W - pl - pr) / Math.max(1, rows.length - 1);
  const first = rows[0], last = rows[rows.length - 1];
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="연도별 동급 대비 해상 효율" onMouseLeave={() => setHov(null)}>
        {niceTicks(lo, hi, 4).map((t) => (
          <g key={t}><line x1={pl} x2={W - pr} y1={sy(t)} y2={sy(t)} className="grid" /><text x={pl - 8} y={sy(t) + 4} textAnchor="end" className="ax">{t > 0 ? `+${t}` : t}%</text></g>
        ))}
        <line x1={pl} x2={W - pr} y1={sy(0)} y2={sy(0)} className="zero" />
        <text x={W - pr + 6} y={sy(0) + 4} className="ax">동급 0%</text>
        <path d={path} fill="none" stroke="var(--ink)" strokeWidth={2} strokeLinejoin="round" />
        {rows.map((r) => (
          <g key={r.y}>
            <circle cx={sx(r.y)} cy={sy(r.v)} r={hov === r.y ? 6 : 4.5} fill={r.v > 0 ? "var(--signal)" : "var(--base)"} stroke="var(--surface)" strokeWidth={2} />
            <text x={sx(r.y)} y={H - 8} textAnchor="middle" className="ax">{r.y}</text>
          </g>
        ))}
        {hov === null && [first, last].map((r) => (
          <text key={r.y} x={sx(r.y)} y={sy(r.v) + (r.v > 0 ? -12 : 20)} textAnchor="middle" className="lbl b">{pct(r.v)}</text>
        ))}
        {h && <line x1={sx(h.y)} x2={sx(h.y)} y1={pt} y2={H - pb} stroke="var(--ink-3)" strokeDasharray="3 3" />}
        {rows.map((r) => <rect key={`h${r.y}`} x={sx(r.y) - colW / 2} y={pt} width={colW} height={H - pt - pb} fill="transparent" onMouseEnter={() => setHov(r.y)} />)}
      </svg>
      <Info>{h ? <><b>{h.y}년</b><span>동급 대비 {pct(h.v, 1)}</span></> : <span className="muted">연도에 커서를 올리면 값을 표시합니다.</span>}</Info>
    </>
  );
}

// ── 앞으로 1~3년: 중앙값(점선)과 80% 구간. 팀 분위 회귀 예측 (p10·p50·p90) ──
export function FanChart({ hist, fc, peer, base, unit = "kg CO₂/해리", label = "해상 효율" }: { hist: { y: number; v: number }[]; fc: Band[]; peer?: number; base: number; unit?: string; label?: string }) {
  const [hov, setHov] = useState<number | null>(null);
  const past = hist.filter((r) => r.y >= base - 3 && r.y <= base);
  if (!past.length) return null;
  const fut = fc.map((f, i) => ({ y: base + 1 + i, m: f[0], lo: f[1], hi: f[2] }));
  const all = [...past.map((p) => p.v), ...fut.flatMap((f) => [f.lo, f.hi]), ...(peer ? [peer] : [])];
  const lo = Math.min(...all) * 0.92, hi = Math.max(...all) * 1.06;
  const W = 600, H = 240, pl = 52, pr = 70, pt = 16, pb = 30;
  const x0 = past[0].y, x1 = base + fc.length;
  const sx = (y: number) => pl + ((y - x0) / Math.max(1, x1 - x0)) * (W - pl - pr);
  const sy = (v: number) => pt + ((hi - v) / (hi - lo)) * (H - pt - pb);
  const last = past[past.length - 1];
  const band = `M${sx(last.y)},${sy(last.v)} ${fut.map((f) => `L${sx(f.y)},${sy(f.hi)}`).join(" ")} ${[...fut].reverse().map((f) => `L${sx(f.y)},${sy(f.lo)}`).join(" ")} Z`;
  const years = [...past.map((p) => p.y), ...fut.map((f) => f.y)];
  const colW = (W - pl - pr) / Math.max(1, years.length - 1);
  const hf = fut.find((f) => f.y === hov), hp = past.find((p) => p.y === hov);
  const end = fut[fut.length - 1];
  return (
    <>
      <div className="legend"><span><i style={{ background: "var(--ink)" }} className="line" />보고값</span><span><i style={{ background: "var(--signal)" }} className="line" />예상값(중앙)</span><span><i style={{ background: "rgba(224,83,44,.28)" }} />80% 범위</span>{peer ? <span><i style={{ background: "var(--base)" }} className="line" />동급 중간값 ({base})</span> : null}</div>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={`${label} 1~3년 예측`} onMouseLeave={() => setHov(null)}>
        {niceTicks(lo, hi, 4).map((t) => (
          <g key={t}><line x1={pl} x2={W - pr} y1={sy(t)} y2={sy(t)} className="grid" /><text x={pl - 8} y={sy(t) + 4} textAnchor="end" className="ax">{num(t)}</text></g>
        ))}
        {peer ? <line x1={pl} x2={W - pr} y1={sy(peer)} y2={sy(peer)} stroke="var(--base)" strokeWidth={1.5} strokeDasharray="5 4" /> : null}
        <path d={band} className="fc-band" />
        <path d={past.map((p, i) => `${i ? "L" : "M"}${sx(p.y)},${sy(p.v)}`).join(" ")} fill="none" stroke="var(--ink)" strokeWidth={2} />
        <path d={`M${sx(last.y)},${sy(last.v)} ${fut.map((f) => `L${sx(f.y)},${sy(f.m)}`).join(" ")}`} className="fc-line" />
        {past.map((p) => <circle key={p.y} cx={sx(p.y)} cy={sy(p.v)} r={4.5} fill="var(--ink)" stroke="var(--surface)" strokeWidth={2} />)}
        {fut.map((f) => <circle key={f.y} cx={sx(f.y)} cy={sy(f.m)} r={4.5} className="fc-dot f" />)}
        {years.map((y) => <text key={y} x={sx(y)} y={H - 8} textAnchor="middle" className="ax">{y}</text>)}
        <text x={sx(end.y) + 8} y={sy(end.m) + 4} className="lbl b">{num(end.m)}</text>
        <text x={sx(end.y) + 8} y={sy(end.hi) + 4} className="ax">{num(end.hi)}</text>
        <text x={sx(end.y) + 8} y={sy(end.lo) + 4} className="ax">{num(end.lo)}</text>
        {hov !== null && <line x1={sx(hov)} x2={sx(hov)} y1={pt} y2={H - pb} stroke="var(--ink-3)" strokeDasharray="3 3" />}
        {years.map((y) => <rect key={`h${y}`} x={sx(y) - colW / 2} y={pt} width={colW} height={H - pt - pb} fill="transparent" onMouseEnter={() => setHov(y)} />)}
      </svg>
      <Info>
        {hf ? <><b>{hf.y}년 예측</b><span>중앙값 {num(hf.m)}</span><span>80% 구간 {num(hf.lo)}~{num(hf.hi)}</span><span>{base}년 대비 {pct((hf.m / last.v - 1) * 100, 1)}</span></>
          : hp ? <><b>{hp.y}년 보고</b><span>{num(hp.v, 1)} {unit}</span></>
          : <span className="muted">연도에 커서를 올리면 값을 표시합니다. 단위 {unit}.</span>}
      </Info>
    </>
  );
}

// ── 정박 배출: 해마다 같은 조건 예측 대비 몇 배였나 ──
export function BerthChart({ rows }: { rows: { y: number; ratio: number | null }[] }) {
  const [hov, setHov] = useState<number | null>(null);
  const ok = rows.filter((r) => r.ratio !== null) as { y: number; ratio: number }[];
  if (!ok.length) return null;
  // 배수는 로그 축 (0.25 ~ 최대)
  const top = Math.max(4, ...ok.map((r) => r.ratio)) * 1.15, bot = 0.25;
  const W = 600, H = 150, pl = 40, pr = 12, pt = 14, pb = 24;
  const bw = Math.min(24, ((W - pl - pr) / rows.length) * 0.5);
  const sx = (i: number) => pl + ((i + 0.5) / rows.length) * (W - pl - pr);
  const sy = (v: number) => pt + (Math.log(top / Math.max(bot, v)) / Math.log(top / bot)) * (H - pt - pb);
  const h = ok.find((r) => r.y === hov);
  const ticks = [0.5, 1, 2, 5, 10, 20, 50].filter((t) => t >= bot && t <= top);
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="연도별 정박 배출의 같은 조건 대비 배수" onMouseLeave={() => setHov(null)}>
        {ticks.map((t) => <g key={t}><line x1={pl} x2={W - pr} y1={sy(t)} y2={sy(t)} className="grid" /><text x={pl - 6} y={sy(t) + 4} textAnchor="end" className="ax">{t}×</text></g>)}
        <line x1={pl} x2={W - pr} y1={sy(1)} y2={sy(1)} stroke="var(--ink-3)" strokeWidth={1} />
        {rows.map((r, i) => {
          if (r.ratio === null) return <text key={r.y} x={sx(i)} y={H - 6} textAnchor="middle" className="ax">{r.y}</text>;
          const y1 = sy(r.ratio), y0 = sy(1);
          const up = r.ratio >= 1;
          return (
            <g key={r.y} onMouseEnter={() => setHov(r.y)}>
              <rect x={sx(i) - bw / 2} y={Math.min(y0, y1)} width={bw} height={Math.max(1.5, Math.abs(y1 - y0))} rx={3} fill="var(--berth)" fillOpacity={up ? 1 : 0.4} />
              <rect x={sx(i) - (W - pl - pr) / rows.length / 2} y={pt} width={(W - pl - pr) / rows.length} height={H - pt - pb} fill="transparent" />
              <text x={sx(i)} y={H - 6} textAnchor="middle" className="ax">{r.y}</text>
            </g>
          );
        })}
      </svg>
      <Info>{h ? <><b>{h.y}년</b><span>정박 배출 = 같은 조건 예측값의 {times(h.ratio)}</span></> : <span className="muted">1× = 같은 조건 예측값. 막대에 커서를 올리면 값을 표시합니다.</span>}</Info>
    </>
  );
}
