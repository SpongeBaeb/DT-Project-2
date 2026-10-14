// 선대 보기: 선종·회사로 묶어 "더 쓰게 만든 이유"가 어디에 많은지, 운항 유형별로 꾸준히 더 쓰는 배가 어디에 많은지 본다.
import { useMemo, useState } from "react";
import type { FactorKey, Meta, Ship } from "../data";
import { isHigh, typeKo, vsPeer } from "../data";
import { num, pct } from "../format";
import { Card, Help, Reveal } from "../components/ui";

const BUCKET: { k: string; name: string; color: string; keys: FactorKey[] }[] = [
  { k: "ops", name: "운항 패턴 (속력·해상 시간·EU 역내 비중)", color: "var(--ops)", keys: ["speed", "hours", "intra"] },
  { k: "cond", name: "선박 조건 (선령·설계·내빙·크기·기타)", color: "var(--cond)", keys: ["age", "ice", "size", "other"] },
  { k: "fuel", name: "대체연료", color: "var(--fuel)", keys: ["fuel"] },
  { k: "rest", name: "미설명 잔차", color: "var(--rest)", keys: ["rest"] },
];
const median = (a: number[]) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : NaN; };

interface Row { key: string; label: string; n: number; high: number; tgt: number; vs: number; alloc: number[] }
function summarize(key: string, label: string, ss: Ship[]): Row {
  const sums = BUCKET.map((b) => ss.reduce((a, s) => a + b.keys.reduce((x, k) => x + Math.max(0, s.c[k]), 0), 0));
  const tot = sums.reduce((a, b) => a + b, 0) || 1;
  return { key, label, n: ss.length, high: ss.filter((s) => isHigh(s) && !s.sig?.length).length, tgt: ss.filter((s) => s.lst === "target").length, vs: median(ss.map(vsPeer)), alloc: sums.map((x) => x / tot) };
}

export default function Fleet({ ships, meta }: { ships: Ship[]; meta: Meta }) {
  const [mode, setMode] = useState<"type" | "co">("type");
  const [q, setQ] = useState("");
  const [min, setMin] = useState(5);

  const rows = useMemo(() => {
    const m = new Map<string, Ship[]>();
    for (const s of ships) { const k = mode === "type" ? s.t : s.co; if (k) (m.get(k) ?? m.set(k, []).get(k)!).push(s); }
    return [...m].map(([k, ss]) => summarize(k, mode === "type" ? typeKo(k) : k, ss))
      .filter((r) => mode === "type" || (r.n >= min && (!q || r.label.toLowerCase().includes(q.toLowerCase()))))
      .sort((a, b) => b.high - a.high || b.n - a.n).slice(0, mode === "type" ? 99 : 60);
  }, [ships, mode, q, min]);
  const cross = useMemo(() => {
    const cells: Ship[][][] = [0, 1, 2].map(() => [[], [], []]);
    for (const s of ships) if (s.tx && s.ta) cells[s.tx - 1][s.ta - 1].push(s);
    return cells;
  }, [ships]);
  const EXP = [1, 2, 3].map((i) => meta.type_names.exposure[String(i)]), PROF = [1, 2, 3].map((i) => meta.type_names.profile[String(i)]);
  const EXP_DESC = ["EU 역내 항해 비중이 높은 선박", "EU 항만에 정기적으로 기항하는 선박", "EU 기항이 비정기적인 선박"];
  const shareAll = meta.funnel.high / meta.funnel.all;

  return (
    <div className="wrap" style={{ paddingBottom: 80 }}>
      <div className="page-h" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 16, flexWrap: "wrap" }}>
        <div>
          <h1>선대 보기</h1>
          <p>선종·관리회사 단위로 동급 대비 차이의 요인 구성과 지속 초과 선박 분포를 집계합니다. {meta.base_year}년 보고 기준.</p>
        </div>
        <div className="seg" role="tablist">
          <button role="tab" aria-selected={mode === "type"} className={mode === "type" ? "on" : ""} onClick={() => setMode("type")}>선종별</button>
          <button role="tab" aria-selected={mode === "co"} className={mode === "co" ? "on" : ""} onClick={() => setMode("co")}>회사별</button>
        </div>
      </div>

      <section style={{ paddingTop: 32 }}>
        <Reveal className="band-h" ><h2>차이 요인 구성</h2><p>동급 대비 증가 요인(양의 기여)을 네 범주로 합산한 비중입니다. 우측 수치는 동급 대비 해상 효율 중앙값입니다.</p></Reveal>
        {mode === "co" && (
          <div className="fl-tools">
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="관리회사명" aria-label="관리회사 검색" />
            <label className="small">보유 {min}척 이상 <input type="range" min={1} max={30} value={min} onChange={(e) => setMin(Number(e.target.value))} aria-label="최소 척수" /></label>
          </div>
        )}
        <Card>
          <div className="stack-legend">{BUCKET.map((b) => <span key={b.k}><i style={{ background: b.color }} />{b.name}</span>)}</div>
          {rows.map((r) => (
            <a key={r.key} className="st-row" href={mode === "type" ? `#/search?type=${encodeURIComponent(r.key)}` : `#/search?q=${encodeURIComponent(r.key)}`}
              title={BUCKET.map((b, j) => `${b.name} ${Math.round(r.alloc[j] * 100)}%`).join(" · ")}>
              <span className="st-name">{r.label}<small>{num(r.n)}척 · 지속 초과 {num(r.high)}척 · 영업 타깃 {num(r.tgt)}척</small></span>
              <span className="st-bar">{r.alloc.map((a, j) => a > 0.005 && <span key={j} style={{ width: `${a * 100}%`, background: BUCKET[j].color }} />)}</span>
              <span className="st-v">{pct(r.vs, 1)}</span>
            </a>
          ))}
          {!rows.length && <p className="muted">조건에 맞는 관리회사가 없습니다.</p>}
        </Card>
        <Help><p>관리회사는 MRV 보고 책임 회사(최근 기준)로 선주와 다를 수 있습니다. 요인 기여는 공통잔차 모델에 따른 통계적 연관입니다.</p></Help>
      </section>

      {cross && (
        <section style={{ paddingTop: 72 }}>
          <Reveal className="band-h"><h2>선박 유형 교차표</h2><p>EU 규제 노출도(행) × 선령·설계 유형(열) 2축 K-평균 분류별 지속 초과 선박 비율입니다. 전체 평균 {(shareAll * 100).toFixed(1)}%. 설계 효율 값이 없는 선박은 제외합니다.</p></Reveal>
          <Card>
            <div className="xg">
              <span />
              {PROF.map((p) => <span key={p} className="xg-h">{p}</span>)}
              {EXP.map((e, i) => (
                <div key={e} className="xg-r">
                  <span className="xg-h xg-rh">{e}<small>{EXP_DESC[i]}</small></span>
                  {PROF.map((p, j) => {
                    const c = cross[i][j];
                    const share = c.length ? c.filter((s) => isHigh(s) && !s.sig?.length).length / c.length : 0;
                    return (
                      <div key={p} className={`xg-c ${share >= shareAll * 1.5 ? "hot" : share >= shareAll ? "warm" : ""}`}>
                        <b>{num(c.length)}척</b>
                        <span>지속 초과 {(share * 100).toFixed(1)}% · 영업 타깃 {num(c.filter((s) => s.lst === "target").length)}척</span>
                        <small>동급 대비 중앙값 {pct(median(c.map(vsPeer)))}</small>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
            <div className="xg-legend">
              <span><i style={{ background: "var(--signal-wash)" }} />전체 평균의 1.5배 이상</span><span><i style={{ background: "var(--amber-wash)" }} />전체 평균 이상</span><span><i style={{ background: "var(--rule-2)" }} />전체 평균 미만</span>
            </div>
          </Card>
        </section>
      )}
    </div>
  );
}
