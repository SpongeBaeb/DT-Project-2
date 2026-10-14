// 관심 목록: 다시 볼 선박과 분석 메모. 이 브라우저에만 저장한다.
import type { Meta, Ship } from "../data";
import { typeKo, vsPeer } from "../data";
import { downloadCsv, setMemo, toggleCompare, toggleWatch, useCompare, useWatch } from "../store";
import { pct } from "../format";
import { verdictOf, VERDICT } from "../verdict";
import { Empty, Grade_, ListBadge, prob, Verdict } from "../components/ui";
import ShipPhoto from "../components/ShipPhoto";

export default function Watch({ ships, meta }: { ships: Ship[]; meta: Meta }) {
  const w = useWatch();
  const cmp = useCompare();
  const rows = w.map((x) => ({ x, s: ships.find((s) => s.imo === x.imo) })).filter((r) => r.s) as { x: (typeof w)[number]; s: Ship }[];
  const csv = () => downloadCsv("sea-marksman_watch.csv", [["IMO", "선박명", "선종", "판정", "CII", "동급 대비 %", `${meta.base_year + 1}년 D·E 확률`, "추가일", "메모"],
    ...rows.map(({ x, s }) => [s.imo, s.n, typeKo(s.t), VERDICT[verdictOf(s)].name, s.cii, vsPeer(s).toFixed(1), s.pde?.[0], x.added, x.memo])]);
  return (
    <div className="wrap" style={{ paddingBottom: 80 }}>
      <div className="page-h" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 16, flexWrap: "wrap" }}>
        <div><h1>관심 목록</h1><p>다시 살펴볼 선박과 분석 메모를 모아 둡니다. 이 브라우저에만 저장되며 서버로 보내지 않습니다.</p></div>
        {rows.length > 0 && <button className="btn ghost sm" onClick={csv}>CSV</button>}
      </div>
      {!rows.length ? (
        <div className="card"><Empty title="저장한 선박이 없습니다"><p>선박 진단 화면의 "관심 추가"로 선박을 담을 수 있습니다.</p><a className="btn" style={{ marginTop: 12 }} href="#/search">선박 찾기</a></Empty></div>
      ) : (
        <ul className="watch">
          {rows.map(({ x, s }) => (
            <li key={s.imo} className="card watch-row">
              <a href={`#/ship/${s.imo}`} className="art" tabIndex={-1} aria-hidden="true"><ShipPhoto type={s.t} small /></a>
              <div>
                <div className="nm"><a href={`#/ship/${s.imo}`}>{s.n}</a><Verdict k={verdictOf(s)} /><ListBadge k={s.lst} /></div>
                <div className="meta">{typeKo(s.t)} · IMO {s.imo} · CII <Grade_ g={s.cii} sm /> · 동급 대비 {pct(vsPeer(s))} · {meta.base_year + 1}년 D·E {prob(s.pde?.[0])} · 추가 {x.added}</div>
                <label className="field" style={{ marginTop: 10 }}>
                  <span>분석 메모</span>
                  <textarea rows={2} value={x.memo} onChange={(e) => setMemo(s.imo, e.target.value)} placeholder="예: 정박 배출 원인 확인 필요, 선사 미팅 시 문의" />
                </label>
              </div>
              <div className="watch-act">
                <button className="btn ghost sm" onClick={() => toggleCompare(s.imo)}>{cmp.includes(s.imo) ? "비교에서 빼기" : "비교에 추가"}</button>
                <button className="btn ghost sm" onClick={() => toggleWatch(s.imo)}>삭제</button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
