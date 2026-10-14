// 홈 첫 화면의 조준경: 점 하나 = 배 한 척(실제 데이터 표본). 가로 위치 = 조건이 같은 배와 비교한 꾸준함 점수(z).
// 조준경이 세 배를 차례로 겨눈다: 정말 더 쓰는 배 → 정박 때문에 나빠 보인 배 → 보고 값이 이상한 배.
// 움직임 줄이기 설정이면 자동으로 넘기지 않는다. 5초 넘게 움직이므로 멈춤 버튼을 둔다.
import { useEffect, useMemo, useState } from "react";
import type { Meta, Ship } from "../data";
import { isHigh, vsPeer } from "../data";
import { num, pct, times } from "../format";
import { verdictOf, type VerdictKey } from "../verdict";
import { Grade_, ScopeIcon } from "./ui";

const W = 600, H = 470, X0 = 34, X1 = 566, Y0 = 34, Y1 = 400, Z_LO = -2.5, Z_HI = 4.5;
const R = 86;
const STEP = 5600;

function rand(seed: number) {
  let s = seed % 2147483647 || 1;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

interface Target { s: Ship; k: VerdictKey; tab: string }

export default function Scope({ ships, meta }: { ships: Ship[]; meta: Meta }) {
  const reduce = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(reduce);
  const [locked, setLocked] = useState(reduce);
  const by = meta.base_year;
  const zx = (z: number) => X0 + ((Math.max(Z_LO, Math.min(Z_HI, z)) - Z_LO) / (Z_HI - Z_LO)) * (X1 - X0);

  const { dots, targets } = useMemo(() => {
    const r = rand(77);
    const pool = ships.filter((s) => s.z !== undefined).sort((a, b) => a.imo - b.imo);
    const step = Math.max(1, pool.length / 520);
    const pos = new Map<number, [number, number]>();
    const dots: { id: number; x: number; y: number }[] = [];
    for (let k = 0; k < Math.min(520, pool.length); k++) {
      const s = pool[Math.floor(k * step)];
      const p: [number, number] = [zx(s.z!), Y0 + r() * (Y1 - Y0)];
      pos.set(s.imo, p);
      dots.push({ id: s.imo, ...{ x: p[0], y: p[1] } });
    }
    const real = ships.filter((s) => isHigh(s) && !s.sig?.length && s.z! < 4 && s.z! > 2.6 && vsPeer(s) > 15 && vsPeer(s) < 60).sort((a, b) => b.co2 - a.co2)[0];
    const berth = ships.find((s) => s.n === "TIGANI" && s.sig?.includes("berth")) ?? ships.filter((s) => s.sig?.includes("berth")).sort((a, b) => (b.br ?? 0) - (a.br ?? 0))[0];
    const check = ships.find((s) => s.n === "NEXUS" && s.sig?.includes("report")) ?? ships.find((s) => s.sig?.includes("report"));
    const targets: Target[] = [];
    if (real) targets.push({ s: real, k: "real", tab: "지속 초과" });
    if (berth) targets.push({ s: berth, k: verdictOf(berth), tab: "정박 요인" });
    if (check) targets.push({ s: check, k: verdictOf(check), tab: "보고값 이상" });
    for (const t of targets) if (!pos.has(t.s.imo) && t.s.z !== undefined) { const p: [number, number] = [zx(t.s.z), Y0 + 40 + r() * (Y1 - Y0 - 80)]; pos.set(t.s.imo, p); dots.push({ id: t.s.imo, x: p[0], y: p[1] }); }
    // 겨눌 배는 조준경이 화면 밖으로 나가지 않도록 세로 위치를 안쪽으로 당긴다
    for (const t of targets) { const p = pos.get(t.s.imo)!; p[1] = Math.max(Y0 + R, Math.min(Y1 - R + 20, p[1])); const d = dots.find((x) => x.id === t.s.imo)!; d.y = p[1]; }
    return { dots, targets: targets.map((t) => ({ ...t, p: pos.get(t.s.imo)! })) };
  }, [ships]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (reduce) return;
    setLocked(false);
    const a = window.setTimeout(() => setLocked(true), 1350);
    return () => window.clearTimeout(a);
  }, [i, reduce]);
  useEffect(() => {
    if (paused || targets.length < 2) return;
    const id = window.setTimeout(() => setI((x) => (x + 1) % targets.length), STEP);
    return () => window.clearTimeout(id);
  }, [i, paused, targets.length]);

  if (!targets.length) return null;
  const t = targets[i];
  const [cx, cy] = t.p;
  const g = t.s.cii;
  const read = t.k === "real"
    ? { s: <>같은 조건 대비 다년간 지속적으로 높은 배출. 단년 변동이 아닌 구조적 차이입니다.</>, v: [[pct(vsPeer(t.s)), `${by}년 동급 대비`], [t.s.z!.toFixed(1), "위치 z (기준 2)"]] }
    : t.k === "berth"
    ? { s: <>CII {g ?? "-"}등급. 등급 악화의 주원인은 해상 운항이 아닌 정박 배출입니다.</>, v: [[times(t.s.br), "정박 배출 (예측값 대비)"], [pct(vsPeer(t.s)), "해상 효율 (동급 대비)"]] }
    : { s: <>CII {g ?? "-"}등급. 보고값(적재량 또는 평균 속력)이 물리 범위를 벗어나 등급 신뢰도가 낮습니다.</>, v: [[g ?? "-", `CII ${by}`], ["검증 필요", "보고값"]] };

  return (
    <div className="scope-wrap">
      <svg className={`scope k-${t.k}`} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`조준경이 ${t.s.n}을(를) 겨누고 있습니다. ${t.tab}`}>
        <g className="field">
          {dots.map((d) => <circle key={d.id} cx={d.x} cy={d.y} r={2.6} className={locked && Math.hypot(d.x - cx, d.y - cy) > R ? "dim" : ""} />)}
        </g>
        <line x1={zx(0)} x2={zx(0)} y1={Y0 - 10} y2={Y1 + 8} stroke="rgba(63,211,198,.35)" strokeDasharray="3 5" />
        <line x1={zx(2)} x2={zx(2)} y1={Y0 - 10} y2={Y1 + 8} stroke="rgba(255,122,85,.35)" strokeDasharray="3 5" />
        <text x={zx(0)} y={Y1 + 30} textAnchor="middle" className="ax-t">같은 조건 수준</text>
        <text x={zx(2)} y={Y1 + 30} textAnchor="middle" className="ax-t">z = 2 →</text>
        <text x={X0} y={Y1 + 56} className="ax-t">← 낮음</text>
        <text x={X1} y={Y1 + 56} textAnchor="end" className="ax-t">높음 →</text>
        <g className="mover" style={{ transform: `translate(${cx}px, ${cy}px)` }}>
          <circle r={R} className="lens" />
          <circle r={R * 0.6} className="ring2" />
          <line x1={-R - 14} x2={-14} y1={0} y2={0} className="hair" /><line x1={14} x2={R + 14} y1={0} y2={0} className="hair" />
          <line y1={-R - 14} y2={-14} x1={0} x2={0} className="hair" /><line y1={14} y2={R + 14} x1={0} x2={0} className="hair" />
          {[-0.75, -0.5, -0.25, 0.25, 0.5, 0.75].map((f) => <line key={f} x1={f * R} x2={f * R} y1={-4} y2={4} className="tickm" />)}
          {locked && (
            <g>
              <circle r={10} className="pulse" />
              {[[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b], j) => (
                <path key={j} d={`M${a * 22},${b * 12} L${a * 22},${b * 22} L${a * 12},${b * 22}`} className="lock-c" fill="none" />
              ))}
            </g>
          )}
        </g>
        <circle cx={cx} cy={cy} r={locked ? 6 : 3.5} className="target" />
      </svg>
      {locked && (
        <a key={i} className={`read k-${t.k} ${cx > W / 2 ? "at-l" : "at-r"}`} href={`#/ship/${t.s.imo}`}>
          <span className="read-k"><ScopeIcon dot="currentColor" />{t.tab}</span>
          <div className="read-n">{t.s.n} {g && <Grade_ g={g} sm />}</div>
          <p className="read-s">{read.s}</p>
          <div className="read-v">{read.v.map(([a, b]) => <div key={b}><b>{a}</b><span>{b}</span></div>)}</div>
        </a>
      )}
      <div className="scope-ctl">
        {targets.map((x, j) => <button key={x.s.imo} className={j === i ? "on" : ""} onClick={() => setI(j)} aria-pressed={j === i}>{x.tab}</button>)}
        {!reduce && (
          <button className="pause" onClick={() => setPaused((p) => !p)} aria-label={paused ? "재생" : "일시정지"}>
            {paused ? <svg viewBox="0 0 16 16"><path d="M4 2.5v11l9-5.5z" fill="currentColor" /></svg> : <svg viewBox="0 0 16 16"><path d="M4 2.5h3v11H4zM9 2.5h3v11H9z" fill="currentColor" /></svg>}
          </button>
        )}
      </div>
      <p className="sr">{num(dots.length)}척 표본을 위치 z 기준으로 배치한 그림입니다.</p>
    </div>
  );
}
