// 다음 해 리스트: 기준 연도 보고 선박 가운데 다음 해 CII 등급 전망으로 고른 영업 타깃·관찰 대상 (팀 ListRule, 결과 표 list_h1)
//   영업 타깃 = 다음 해 CII D·E 확률 ≥ 기준.  관찰 = 타깃이 아니고, 지금 A~C등급이며 다음 해 감축 요구 미달 확률 ≥ p*
import { useMemo, useState } from "react";
import type { Meta, Ship } from "../data";
import { typeKo, vsPeer } from "../data";
import { downloadCsv } from "../store";
import { num, pct } from "../format";
import { verdictOf, VERDICT } from "../verdict";
import { Empty, Grade_, Help, prob, SearchIcon, Verdict } from "../components/ui";

type Tab = "target" | "watch";
const PAGE = 25;

export default function List({ ships, meta, query }: { ships: Ship[]; meta: Meta; query: URLSearchParams }) {
  const L = meta.list;
  const by = meta.base_year;
  const [tab, setTab] = useState<Tab>((query.get("tab") as Tab) === "watch" ? "watch" : "target");
  const [type, setType] = useState<string>("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const inTab = useMemo(() => ships.filter((s) => s.lst === tab).sort((a, b) => (a.lr ?? 1e9) - (b.lr ?? 1e9)), [ships, tab]);
  const byType = useMemo(() => {
    const m = new Map<string, number>();
    for (const s of inTab) m.set(s.t, (m.get(s.t) ?? 0) + 1);
    return [...m].sort((a, b) => b[1] - a[1]);
  }, [inTab]);
  const t = q.trim().toLowerCase();
  const rows = inTab.filter((s) => (!type || s.t === type) && (!t || s.n.toLowerCase().includes(t) || String(s.imo).includes(t) || (s.co ?? "").toLowerCase().includes(t)));
  const shown = rows.slice(page * PAGE, (page + 1) * PAGE);
  const pages = Math.ceil(rows.length / PAGE);
  const illusion = inTab.filter((s) => s.sig?.length).length;
  const real = inTab.filter((s) => verdictOf(s) === "real").length;
  const set = (f: () => void) => { f(); setPage(0); };
  const csv = () => downloadCsv(`sea-marksman_list_${L.year}_${tab}.csv`, [
    ["리스트", "순위", "IMO", "선박명", "선종", "관리회사", `${by}년 CII`, `${L.year}년 D·E 확률`, `${L.year + 1}년 D·E 확률`, `${L.year + 2}년 D·E 확률`, `${L.year}년 감축 요구 미달 확률`, "해상 효율 동급 대비 %", "판정", "데이터", "모델"],
    ...rows.map((s) => [tab === "target" ? "영업 타깃" : "관찰", s.lr, s.imo, s.n, typeKo(s.t), s.co, s.cii, s.pde?.[0], s.pde?.[1], s.pde?.[2], s.pm, vsPeer(s).toFixed(1), VERDICT[verdictOf(s)].name, meta.data_hash, meta.model_version]),
  ]);

  return (
    <div className="wrap" style={{ paddingBottom: 80 }}>
      <div className="page-h">
        <h1>{L.year}년 리스트</h1>
        <p>{by}년 보고 {num(meta.n_ships)}척을 대상으로 {L.year}년 CII 등급 전망에 따라 영업 타깃과 관찰 대상을 선정합니다. 순위는 같은 리스트 안에서 {L.year}년 D·E 확률이 높은 순입니다.</p>
      </div>

      <div className="lt-tabs" role="tablist" aria-label="리스트">
        <button role="tab" aria-selected={tab === "target"} className={`lt-tab t ${tab === "target" ? "on" : ""}`} onClick={() => set(() => { setTab("target"); setType(""); })}>
          <b>{num(L.target)}<small>척</small></b><span>영업 타깃</span><em>{L.year}년 CII D·E 확률 {prob(L.de_cut)} 이상</em>
        </button>
        <button role="tab" aria-selected={tab === "watch"} className={`lt-tab w ${tab === "watch" ? "on" : ""}`} onClick={() => set(() => { setTab("watch"); setType(""); })}>
          <b>{num(L.watch)}<small>척</small></b><span>관찰</span><em>현재 {L.watch_ratings.join("·")}등급 · {L.year}년 감축 요구 미달 확률 {prob(L.p_star)} 이상</em>
        </button>
      </div>

      <p className="lt-note">
        {tab === "target"
          ? <>영업 타깃 {num(inTab.length)}척 중 착시 신호가 있는 선박 {num(illusion)}척은 등급 악화가 정박 배출·보고값 등에서 비롯되었을 수 있어 진단 확인이 필요합니다. 해상 효율이 다년 지속 초과인 선박은 {num(real)}척입니다.</>
          : <>관찰 대상은 현재 효율이 양호한 선박 중 다음 해 감축 요구를 채우지 못할 가능성이 큰 선박이며, 비효율을 의미하지 않습니다.</>}
      </p>

      <div className="lt-tools">
        <div className="sr-box"><SearchIcon /><input type="search" value={q} onChange={(e) => set(() => setQ(e.target.value))} placeholder="선박명, IMO 번호, 관리회사" aria-label="리스트 검색" /></div>
        <div className="lt-types" role="group" aria-label="선종">
          <button className={!type ? "on" : ""} onClick={() => set(() => setType(""))}>전체 {num(inTab.length)}</button>
          {byType.map(([k, n]) => <button key={k} className={type === k ? "on" : ""} onClick={() => set(() => setType(k))}>{typeKo(k)} {num(n)}</button>)}
        </div>
        <button className="btn ghost sm" onClick={csv}>CSV</button>
      </div>

      {!shown.length ? <Empty title="조건에 맞는 선박이 없습니다" /> : (
        <div className="card lt-card">
          <div className="tbl">
            <table className="t lt">
              <thead>
                <tr>
                  <th>순위</th><th>선박</th><th>{by}년 CII</th>
                  <th>{L.year}년 D·E</th><th>{L.year + 1}</th><th>{L.year + 2}</th>
                  <th>{L.year}년 미달 확률</th><th>해상 효율 동급 대비</th><th>판정</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((s) => (
                  <tr key={s.imo}>
                    <td className="rk">{num(s.lr)}</td>
                    <td><a href={`#/ship/${s.imo}`}><b>{s.n}</b></a><span className="sub">{typeKo(s.t)} · {s.co ?? "관리회사 미상"}</span></td>
                    <td><Grade_ g={s.cii} sm /></td>
                    <td><span className="pbar"><i style={{ width: `${(s.pde?.[0] ?? 0) * 100}%` }} /></span><b>{prob(s.pde?.[0])}</b></td>
                    <td>{prob(s.pde?.[1])}</td>
                    <td>{prob(s.pde?.[2])}</td>
                    <td>{prob(s.pm)}</td>
                    <td className={vsPeer(s) > 0 ? "up" : "down"}>{pct(vsPeer(s))}</td>
                    <td><Verdict k={verdictOf(s)} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pages > 1 && (
            <nav className="pager" aria-label="페이지">
              <button disabled={page === 0} onClick={() => { setPage(page - 1); window.scrollTo({ top: 0 }); }}>이전</button>
              <span>{page + 1} / {num(pages)}</span>
              <button disabled={page >= pages - 1} onClick={() => { setPage(page + 1); window.scrollTo({ top: 0 }); }}>다음</button>
            </nav>
          )}
        </div>
      )}

      <Help>
        <p>D·E 확률은 전체 효율(정박 포함 거리당 CO₂) 1~3년 분위 예측과 연도별 CII 등급 경계·감축률로 산출합니다. 감축 요구 미달은 다음 해 기준선 하락분보다 덜 줄이거나 늘어나는 경우입니다.</p>
        <p>관찰 기준 p*({prob(L.p_star)})는 학습 마지막 연도({by}) 선박들의 미달 확률 75% 분위수로, 학습 시점에 고정됩니다. 선종·기간별 검증 등급은 아직 표시하지 않습니다.</p>
      </Help>
    </div>
  );
}
