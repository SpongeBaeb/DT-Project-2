// 시장 지표 (팀 공용 서버): EUA 경매 가격 추이, 환율, Brent·아시아 LNG, 건화물 운임(BDI). 모두 출처·기준일·상태를 함께 표시한다.
import { useEffect, useMemo, useState } from "react";
import { marketDryBulk, marketEnergy, marketHistory, type MarketPoint, type MarketSeries } from "../shared";
import { useMarket } from "../market";
import { num } from "../format";

const STATUS: Record<string, string> = { live: "일별 기준값", stale: "이전 수신값", historical: "과거 관측값", unavailable: "자료 없음", mock: "예시값" };

function Tile({ label, p, unit, d = 1 }: { label: string; p?: MarketPoint; unit?: string; d?: number }) {
  return (
    <div className={`mk-tile ${!p || p.value === null ? "na" : ""}`}>
      <span className="k">{label}</span>
      <b>{p && p.value !== null ? num(p.value, d) : "–"}<small> {unit ?? p?.unit ?? ""}</small></b>
      <span className="muted small">{p ? `${STATUS[p.status] ?? p.status}${p.as_of_date ? ` · ${p.as_of_date}` : ""}` : "불러오는 중"}</span>
      <span className="muted small">{p?.source ?? ""}</span>
    </div>
  );
}

/** EUA 월평균 추이 (경매일 가중 평균의 월평균) */
function EuaChart({ s }: { s: MarketSeries }) {
  const [hov, setHov] = useState<number | null>(null);
  const pts = useMemo(() => {
    const m = new Map<string, number[]>();
    for (const it of s.items) { const k = it.as_of_date.slice(0, 7); (m.get(k) ?? m.set(k, []).get(k)!).push(it.value); }
    return [...m].sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => ({ k, v: v.reduce((a, b) => a + b, 0) / v.length }));
  }, [s]);
  if (pts.length < 2) return null;
  const W = 600, H = 200, pl = 40, pr = 12, pt = 14, pb = 26;
  const hi = Math.max(...pts.map((p) => p.v)) * 1.08;
  const sx = (i: number) => pl + (i / (pts.length - 1)) * (W - pl - pr);
  const sy = (v: number) => pt + (1 - v / hi) * (H - pt - pb);
  const years = pts.map((p, i) => [p.k, i] as const).filter(([k]) => k.endsWith("-01"));
  const h = hov === null ? null : pts[hov];
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="EUA 월평균 가격 추이" onMouseLeave={() => setHov(null)}
        onMouseMove={(e) => { const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect(); const x = ((e.clientX - r.left) / r.width) * W; setHov(Math.max(0, Math.min(pts.length - 1, Math.round(((x - pl) / (W - pl - pr)) * (pts.length - 1))))); }}>
        {[0, 25, 50, 75, 100].filter((t) => t < hi).map((t) => <g key={t}><line x1={pl} x2={W - pr} y1={sy(t)} y2={sy(t)} className="grid" /><text x={pl - 6} y={sy(t) + 4} textAnchor="end" className="ax">{t}</text></g>)}
        <path d={pts.map((p, i) => `${i ? "L" : "M"}${sx(i)},${sy(p.v)}`).join(" ")} fill="none" stroke="var(--base)" strokeWidth={2} />
        {years.map(([k, i]) => <text key={k} x={sx(i)} y={H - 8} textAnchor="middle" className="ax">{k.slice(0, 4)}</text>)}
        {h && hov !== null && <><line x1={sx(hov)} x2={sx(hov)} y1={pt} y2={H - pb} stroke="var(--ink-3)" strokeDasharray="3 3" /><circle cx={sx(hov)} cy={sy(h.v)} r={4.5} fill="var(--base)" stroke="var(--surface)" strokeWidth={2} /></>}
      </svg>
      <div className="chart-info">{h ? <><b>{h.k}</b><span>월평균 {num(h.v, 2)} EUR/tCO₂</span></> : <span className="muted">커서를 올리면 월평균 값을 표시합니다. 경매일 가중 평균의 월평균.</span>}</div>
    </>
  );
}

export default function MarketPanel() {
  const m = useMarket();
  const [en, setEn] = useState<{ brent?: MarketPoint; lng_or_gas?: MarketPoint } | null>(null);
  const [bdi, setBdi] = useState<MarketPoint | undefined>();
  const [eua, setEua] = useState<MarketSeries | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    marketEnergy().then(setEn).catch(() => setErr("에너지 가격을 불러오지 못했습니다."));
    marketDryBulk().then((d) => setBdi(d.bdi)).catch(() => undefined);
    marketHistory("EUA").then(setEua).catch(() => setErr("EUA 추이를 불러오지 못했습니다."));
  }, []);
  return (
    <section className="mk">
      <div className="tc-h">
        <div>
          <h2>시장 지표</h2>
          <p>팀 공용 서버의 시장 자료입니다. 장중 실시간 가격이 아니므로 기준일과 출처를 확인하십시오. 연료 가격 공급자는 아직 연결되지 않았습니다.</p>
        </div>
      </div>
      <div className="mk-grid">
        <Tile label="원/USD" p={m.points.fx_usd} unit="원" />
        <Tile label="원/EUR" p={m.points.fx_eur} unit="원" />
        <Tile label="배출권 (EUA)" p={m.points.eua_eur} unit="EUR/tCO₂" d={2} />
        <Tile label="연료 (VLSFO, 로테르담)" p={m.points.fuel_usd} unit="USD/t" />
        <Tile label="Brent 원유" p={en?.brent} unit="USD/배럴" d={2} />
        <Tile label="아시아 LNG" p={en?.lng_or_gas} unit="USD/MMBtu" d={2} />
        <Tile label="건화물 운임 (BDI)" p={bdi} unit="pt" d={0} />
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-h"><h3>EUA 가격 추이</h3><span className="small muted">{eua ? `${eua.source} · ${num(eua.items.length)}개 경매일` : "불러오는 중…"}</span></div>
        {eua ? <EuaChart s={eua} /> : <p className="muted small">{err || "공용 서버에서 불러오는 중… (유휴 상태면 30초 이상)"}</p>}
      </div>
      {err && <p className="notice">{err}</p>}
    </section>
  );
}
