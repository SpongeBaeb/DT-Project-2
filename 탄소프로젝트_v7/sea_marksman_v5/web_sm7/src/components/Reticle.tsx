// 조준 막대: 동급 중간(0)을 기준선으로, 이 배의 해상 효율 위치를 조준선으로 표시한다.
// 가로축은 동급 대비 차이(로그 비율). ±50% 밖은 끝에 붙이고 화살표로 표시한다.
import { pct } from "../format";

const LIM = Math.log(1.5);

export default function Reticle({ sea, peer, exp, compact, label = true }: { sea: number; peer: number; exp?: number; compact?: boolean; label?: boolean }) {
  const W = compact ? 220 : 560, H = compact ? 30 : 96, pl = compact ? 8 : 16, pr = compact ? 8 : 16;
  const cy = compact ? 15 : 46;
  const sx = (v: number) => {
    const d = Math.max(-LIM, Math.min(LIM, Math.log(v / peer)));
    return pl + ((d + LIM) / (2 * LIM)) * (W - pl - pr);
  };
  const x0 = sx(peer), xs = sx(sea), xe = exp !== undefined ? sx(exp) : undefined;
  const d = (sea / peer - 1) * 100;
  const out = Math.abs(Math.log(sea / peer)) > LIM;
  const R = compact ? 6 : 11;
  const ticks = compact ? [] : [-40, -20, 20, 40].map((p) => ({ p, x: sx(peer * (1 + p / 100)) }));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={`ret ${d > 0 ? "hi" : "lo"}`} role="img"
      aria-label={`해상 효율 동급 대비 ${pct(d)}`}>
      <line x1={pl} x2={W - pr} y1={cy} y2={cy} className="axis" />
      {ticks.map((t) => (
        <g key={t.p}>
          <line x1={t.x} x2={t.x} y1={cy - 4} y2={cy + 4} className="tick" />
          <text x={t.x} y={cy + 20} textAnchor="middle" className="lab">{t.p > 0 ? `+${t.p}%` : `${t.p}%`}</text>
        </g>
      ))}
      <line x1={xs} x2={x0} y1={cy} y2={cy} className="span" />
      <line x1={x0} x2={x0} y1={cy - (compact ? 10 : 18)} y2={cy + (compact ? 10 : 18)} className="zero" />
      {xe !== undefined && <line x1={xe} x2={xe} y1={cy - (compact ? 7 : 13)} y2={cy + (compact ? 7 : 13)} className="exp" />}
      <circle cx={xs} cy={cy} r={R} className="ring" />
      <line x1={xs - R - 4} x2={xs - R + 3} y1={cy} y2={cy} className="cross" />
      <line x1={xs + R - 3} x2={xs + R + 4} y1={cy} y2={cy} className="cross" />
      <line x1={xs} x2={xs} y1={cy - R - 4} y2={cy - R + 3} className="cross" />
      <line x1={xs} x2={xs} y1={cy + R - 3} y2={cy + R + 4} className="cross" />
      {out && <text x={xs + (d > 0 ? -R - 8 : R + 8)} y={cy + 4} textAnchor={d > 0 ? "end" : "start"} className="lab">{d > 0 ? "▶" : "◀"}</text>}
      {!compact && label && (
        <>
          <text x={x0} y={cy - 26} textAnchor="middle" className="lab">동급 중간값</text>
          {xe !== undefined && Math.abs(xe - x0) > 60 && Math.abs(xe - xs) > 50 && <text x={xe} y={cy - 26} textAnchor="middle" className="lab">같은 조건 예측</text>}
          <text x={xs} y={H - 4} textAnchor="middle" className="lab b">{pct(d)}</text>
        </>
      )}
    </svg>
  );
}
