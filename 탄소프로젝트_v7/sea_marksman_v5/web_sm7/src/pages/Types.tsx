// 선종별 현황: 13개 선종 줄 목록(마우스를 올리면 사진) → 선종 상세(등급 분포, 더 쓰는 이유, 2026 타깃)
import { useMemo, useState } from "react";
import type { FactorKey, Meta, Ship } from "../data";
import { FACTORS, GRADES, TYPE_KO, vsPeer } from "../data";
import { num } from "../format";
import { prob } from "../components/ui";
import { BigTitle, RoundBtn } from "../components/Kinetic";
import { useTypeStats } from "./Home7";

export const TYPE_DESC: Record<string, string> = {
  bulk: "석탄·곡물·철광석을 포장 없이 싣는 배", container: "규격 컨테이너를 싣고 정해진 항로를 도는 배", tanker: "원유와 석유제품을 나르는 배",
  chemical_tanker: "화학제품과 석유제품을 나르는 배", general_cargo: "여러 형태의 화물을 함께 싣는 배", vehicle_carrier: "자동차를 층층이 싣는 배",
  ro_pax: "차량과 승객을 함께 싣는 여객선", lng_carrier: "천연가스를 영하 162도로 액화해 나르는 배", gas_carrier: "LPG 등 액화가스를 나르는 배",
  ro_ro: "바퀴 달린 화물을 굴려 싣는 배", cruise: "숙박·여가 시설을 갖춘 여객선", reefer: "냉장·냉동 화물을 나르는 배", container_ro_ro: "컨테이너와 차량 화물을 함께 싣는 배",
};

const FACTOR_PLAIN: Record<FactorKey, string> = {
  size: "크기 (같은 급 안에서)", speed: "속력 (대기 포함)", hours: "바다에 있던 시간", intra: "EU 역내 항로 비중", age: "선령·설계",
  fuel: "대체연료", ice: "내빙 등급", other: "기타", rest: "설명되지 않는 부분",
};

export function Types({ ships }: { ships: Ship[] }) {
  const stats = useTypeStats(ships);
  const [hov, setHov] = useState<{ t: string; x: number; y: number } | null>(null);
  const B = import.meta.env.BASE_URL;
  return (
    <>
      <section className="s7 dark page7-top">
        <div className="w7">
          <BigTitle lines={[["선종마다", 0], ["기준이", 36], ["다릅니다", 12]]} />
          <p className="lead7">CII 기준선은 선종과 크기에 따라 다르고, 연료를 더 쓰게 되는 이유도 선종마다 다릅니다. 선종을 고르면 등급 분포와 동급보다 더 쓰는 배들의 주된 이유를 보여 줍니다.</p>
        </div>
      </section>
      <section className="s7 dark" onMouseLeave={() => setHov(null)}>
        <div className="w7">
          <div className="tl-rows">
            {stats.map((x, i) => (
              <a key={x.t} className="tr7" href={`#/types/${x.t}`} onMouseMove={(e) => setHov({ t: x.t, x: e.clientX, y: e.clientY })}>
                <span className="n">{String(i + 1).padStart(2, "0")}</span>
                <span className="h">{TYPE_KO[x.t]}</span>
                <span className="d">{TYPE_DESC[x.t]}</span>
                <span className="v"><b>{num(x.n)}</b>척</span>
                <span className="v"><b>{Math.round((x.de / x.n) * 100)}%</b>D·E</span>
              </a>
            ))}
          </div>
        </div>
        {hov && <img className="hover-img" src={`${B}types/${hov.t}-sm.webp`} alt="" style={{ left: hov.x, top: hov.y }} />}
      </section>
    </>
  );
}

export function TypeDetail({ ships, meta, t }: { ships: Ship[]; meta: Meta; t: string }) {
  const B = import.meta.env.BASE_URL;
  const mine = useMemo(() => ships.filter((s) => s.t === t), [ships, t]);
  const d = useMemo(() => {
    const g = Object.fromEntries(GRADES.map((k) => [k, 0])) as Record<string, number>;
    let graded = 0, sig = 0, high = 0;
    for (const s of mine) { if (s.cii) { g[s.cii]++; graded++; } if (s.sig?.length) sig++; if ((s.z ?? -9) >= 2) high++; }
    const worse = mine.filter((s) => vsPeer(s) > 10);
    const why = FACTORS.filter((k) => k !== "rest" && k !== "other").map((k) => ({ k, v: worse.reduce((a, s) => a + Math.max(0, s.c[k] ?? 0), 0) / Math.max(1, worse.length) }))
      .sort((a, b) => b.v - a.v).slice(0, 4);
    const ages = mine.map((s) => s.age).sort((a, b) => a - b);
    const top = mine.filter((s) => s.lst === "target").sort((a, b) => (a.lr ?? 1e9) - (b.lr ?? 1e9)).slice(0, 6);
    return { g, graded, sig, high, worse: worse.length, why, age: ages[Math.floor(ages.length / 2)], top, target: mine.filter((s) => s.lst === "target").length };
  }, [mine]);
  if (!mine.length) return <section className="s7 dark page7-top"><div className="w7"><h1 className="h2-7">선종을 찾을 수 없습니다</h1><RoundBtn href="#/types" tone="light">선종 목록</RoundBtn></div></section>;
  const maxWhy = Math.max(...d.why.map((x) => x.v), 1);
  return (
    <>
      <section className="s7 dark td7-top">
        <img className="td7-img" src={`${B}types/${t}.webp`} alt={`${TYPE_KO[t]} 대표 이미지`} />
        <div className="w7 td7-in">
          <a className="back7" href="#/types" aria-label="선종 목록으로">←</a>
          <h1 className="h1-7">{TYPE_KO[t]}</h1>
          <p className="lead7">{TYPE_DESC[t]}. {meta.base_year}년 EU에 보고한 {num(mine.length)}척 기준입니다.</p>
        </div>
      </section>
      <section className="s7 paper">
        <div className="w7">
          <div className="facts7 light">
            <div><b>{num(mine.length)}</b><p>{meta.base_year}년 보고 선박</p></div>
            <div><b>{d.graded ? Math.round(((d.g.D + d.g.E) / d.graded) * 100) : 0}%</b><p>CII D·E 비율</p></div>
            <div><b>{num(d.target)}</b><p>{meta.list.year}년 D·E 유력 (영업 타깃)</p></div>
            <div><b>{num(d.high)}</b><p>여러 해 꾸준히 더 쓴 배</p></div>
          </div>

          <h2 className="h3-7">등급 분포</h2>
          <div className="gbar7" role="img" aria-label={GRADES.map((k) => `${k} ${d.g[k]}척`).join(", ")}>
            {GRADES.map((k) => d.g[k] > 0 && (
              <div key={k} className={`g${k}`} style={{ flexGrow: d.g[k] }}><b>{k}</b><span>{Math.round((d.g[k] / Math.max(1, d.graded)) * 100)}%</span></div>
            ))}
          </div>
          <p className="note7">의심 신호가 있는 배 {num(d.sig)}척({Math.round((d.sig / mine.length) * 100)}%)은 등급을 그대로 믿기 어렵습니다.</p>

          <h2 className="h3-7">동급보다 10% 넘게 더 쓰는 {num(d.worse)}척, 주된 이유</h2>
          <div className="why7">
            {d.why.map((x) => (
              <div key={x.k}><span>{FACTOR_PLAIN[x.k]}</span><i><em style={{ width: `${(x.v / maxWhy) * 100}%` }} /></i><b>+{x.v.toFixed(1)}%p</b></div>
            ))}
          </div>
          <p className="note7">배마다 동급 대비 차이를 요인별로 나눈 값의 평균(더 쓰게 만든 쪽만). 통계적 연관이며 인과가 아닙니다.</p>

          {d.top.length > 0 && <>
            <h2 className="h3-7">{meta.list.year}년 영업 타깃 상위</h2>
            <div className="rows7">
              <div className="rows7-h"><span>순위</span><span>선박</span><span>{meta.base_year}년 등급</span><span>{meta.list.year}년 D·E 확률</span></div>
              {d.top.map((s) => (
                <a key={s.imo} className="rows7-r" href={`#/ship/${s.imo}`}>
                  <span className="mono">{s.lr}</span><span><b>{s.n}</b><small>{s.b ?? "–"}년 건조 · {s.co ?? "관리회사 미상"}</small></span><span>{s.cii ?? "–"}</span><span className="big">{prob(s.pde?.[0])}</span>
                </a>
              ))}
            </div>
          </>}
          <div className="btns7">
            <RoundBtn href={`#/search?type=${t}`}>{TYPE_KO[t]} 찾기</RoundBtn>
          </div>
          <p className="note7">대표 이미지는 선종을 보여 주기 위한 생성 이미지로, 특정 선박이 아닙니다. 선령 중간값 {d.age}년.</p>
        </div>
      </section>
    </>
  );
}
