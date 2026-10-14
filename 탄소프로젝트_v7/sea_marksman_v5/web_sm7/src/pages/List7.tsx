// 2026 리스트 (소개 화면): 영업 타깃·관찰 상위 20척을 줄 목록으로. 전체 표·필터·CSV는 서비스 화면(#/table)
import { useMemo } from "react";
import type { Meta, Ship } from "../data";
import { typeKo } from "../data";
import { num } from "../format";
import { prob } from "../components/ui";
import { BigTitle, RoundBtn } from "../components/Kinetic";

export default function List7({ ships, meta, query }: { ships: Ship[]; meta: Meta; query: URLSearchParams }) {
  const L = meta.list;
  const tab = query.get("tab") === "watch" ? "watch" : "target";
  const rows = useMemo(() => ships.filter((s) => s.lst === tab).sort((a, b) => (a.lr ?? 1e9) - (b.lr ?? 1e9)).slice(0, 20), [ships, tab]);
  return (
    <>
      <section className="s7 paper page7-top">
        <div className="w7">
          <BigTitle lines={[[`${L.year}년`, 0], ["리스트", 28]]} />
          <p className="lead7">{meta.base_year}년 기록으로 {L.year}년 등급을 예측해 고른 배입니다. 영업 타깃은 D·E가 거의 확실한 배, 관찰 대상은 지금 등급은 괜찮지만 강화되는 기준에 걸릴 수 있는 배입니다.</p>
          <div className="tabs7" role="tablist">
            <a role="tab" aria-selected={tab === "target"} className={tab === "target" ? "on" : ""} href="#/list?tab=target"><b>{num(L.target)}</b>영업 타깃</a>
            <a role="tab" aria-selected={tab === "watch"} className={tab === "watch" ? "on" : ""} href="#/list?tab=watch"><b>{num(L.watch)}</b>관찰</a>
          </div>
          <p className="note7">{tab === "target" ? `${L.year}년 CII D·E 확률 ${prob(L.de_cut)} 이상.` : `${meta.base_year}년 A~C등급이고, ${L.year}년 감축 기준을 못 맞출 확률 ${prob(L.p_star)} 이상.`} 순위는 확률이 높은 순입니다.</p>
          <div className="rows7">
            <div className="rows7-h"><span>순위</span><span>선박</span><span>{meta.base_year}년 등급</span><span>{tab === "target" ? `${L.year}년 D·E 확률` : `${L.year}년 기준 미달 확률`}</span></div>
            {rows.map((s) => (
              <a key={s.imo} className="rows7-r" href={`#/ship/${s.imo}`}>
                <span className="mono">{String(s.lr ?? "").padStart(2, "0")}</span>
                <span><b>{s.n}</b><small>{typeKo(s.t)} · {s.b ?? "–"}년 건조 · {s.co ?? "관리회사 미상"}</small></span>
                <span>{s.cii ?? "–"}</span>
                <span className="big">{prob(tab === "target" ? s.pde?.[0] : s.pm)}</span>
              </a>
            ))}
          </div>
          <div className="btns7"><RoundBtn href={`#/table?tab=${tab}`}>전체 표</RoundBtn></div>
          <p className="note7">전체 표에서 선종·관리회사로 거르고 CSV로 내려받을 수 있습니다.</p>
        </div>
      </section>
    </>
  );
}
