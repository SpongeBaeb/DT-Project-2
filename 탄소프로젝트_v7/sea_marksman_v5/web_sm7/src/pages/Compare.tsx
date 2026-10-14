// 선박 비교: 최대 4척을 같은 항목으로 나란히 본다. 선종·크기가 다르면 동급 대비·같은 조건 대비 값으로만 견준다.
import { useEffect, useState, type ReactNode } from "react";
import type { Meta, Ship, ShipCost } from "../data";
import { exposureName, LIST_NAME, loadCost, profileName, SIZE_Q, typeKo, vsExp, vsPeer } from "../data";
import { clearCompare, COMPARE_MAX, downloadCsv, toggleCompare, useCompare } from "../store";
import { num, pct, times, tonnes } from "../format";
import { verdictOf, VERDICT } from "../verdict";
import { Empty, Grade_, ListBadge, prob, SearchIcon, SIGNAL_PLAIN, Verdict } from "../components/ui";
import ShipPhoto from "../components/ShipPhoto";
import { illusionCards, ILLUSIONS } from "../components/Illusions";
import { useShipFinder } from "./Home";
import { eok } from "./Diagnosis";

export default function Compare({ ships, meta }: { ships: Ship[]; meta: Meta }) {
  const ids = useCompare();
  const sel = ids.map((i) => ships.find((s) => s.imo === i)).filter(Boolean) as Ship[];
  const [cost, setCost] = useState<Record<string, ShipCost> | null>(null);
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState("");
  const found = useShipFinder(ships, q, 6);
  useEffect(() => { if (sel.length) loadCost().then(setCost).catch(() => setCost({})); }, [sel.length]);
  const types = new Set(sel.map((s) => s.t));
  const add = (imo: number) => { if (!toggleCompare(imo)) setMsg(`최대 ${COMPARE_MAX}척까지 비교합니다.`); else { setMsg(""); setQ(""); } };

  const rows: [string, (s: Ship) => ReactNode, ((s: Ship) => number | string | undefined)?][] = [
    ["선종 · 크기", (s) => `${typeKo(s.t)} · ${SIZE_Q[s.sq]}`, (s) => typeKo(s.t)],
    ["건조연도 · 재화중량", (s) => `${s.b ?? "–"} · ${s.dwt ? num(s.dwt) : "–"} DWT`, (s) => s.b],
    ["진단 연도", (s) => s.ly, (s) => s.ly],
    ["판정", (s) => <Verdict k={verdictOf(s)} />, (s) => VERDICT[verdictOf(s)].name],
    ["CII 등급", (s) => <Grade_ g={s.cii} sm />, (s) => s.cii],
    ["해상 효율 (kg/해리)", (s) => num(s.sea), (s) => s.sea],
    ["동급 대비", (s) => <span className={vsPeer(s) > 0 ? "up" : "down"}>{pct(vsPeer(s))}</span>, (s) => +vsPeer(s).toFixed(1)],
    ["같은 조건 대비", (s) => <span className={vsExp(s) > 0 ? "up" : "down"}>{pct(vsExp(s))}</span>, (s) => +vsExp(s).toFixed(1)],
    ["위치 z", (s) => (s.z === undefined ? "–" : s.z.toFixed(1)), (s) => s.z],
    ["정박 배출 (예측 대비)", (s) => `${tonnes(s.bt)} (${times(s.br)})`, (s) => s.br],
    ["정박 비중", (s) => `${Math.round((s.bs ?? 0) * 100)}%`, (s) => s.bs],
    ["착시 신호", (s) => (s.sig?.length ? s.sig.map((k) => SIGNAL_PLAIN[k][0]).join(" · ") : "없음") + (s.oo ? " · 이상 운항" : ""), (s) => s.sig?.join(" ")],
    [`${meta.base_year + 1}년 CII D·E 확률`, (s) => prob(s.pde?.[0]), (s) => s.pde?.[0]],
    [`${meta.base_year + 1}년 리스트`, (s) => (s.lst ? <ListBadge k={s.lst} /> : "–"), (s) => (s.lst ? LIST_NAME[s.lst] : "")],
    [`${meta.base_year + 1}년 비용 (기준)`, (s) => eok(cost?.[String(s.imo)]?.s?.["기준"][0][0]), (s) => cost?.[String(s.imo)]?.s?.["기준"][0][0]],
    ["연간 CO₂", (s) => tonnes(s.co2), (s) => s.co2],
    ["평균 속력 · 해상 시간", (s) => `${s.spd.toFixed(1)}노트 · ${num(s.hrs)}h`, (s) => s.spd],
    ["연료 그룹", (s) => s.fg ?? "–", (s) => s.fg],
    ["유형", (s) => `${exposureName(meta, s.tx) ?? "–"} · ${profileName(meta, s.ta) ?? "–"}`, (s) => exposureName(meta, s.tx)],
    ["관리회사", (s) => s.co ?? "–", (s) => s.co],
  ];
  const csv = () => downloadCsv("sea-marksman_compare.csv", [["항목", ...sel.map((s) => `${s.n} (${s.imo})`)], ...rows.map(([l, , v]) => [l, ...sel.map((s) => v?.(s))])]);

  return (
    <div className="wrap" style={{ paddingBottom: 80 }}>
      <div className="page-h">
        <h1>선박 비교</h1>
        <p>최대 {COMPARE_MAX}척을 같은 항목으로 나란히 봅니다. 선종·크기가 다른 선박은 원래 값이 아니라 동급 대비·같은 조건 대비 값으로 견주십시오. 비교 목록은 이 브라우저에만 저장됩니다.</p>
      </div>
      <div className="cmp-add">
        <div className="sr-box">
          <SearchIcon />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`선박명 또는 IMO로 추가 (${sel.length}/${COMPARE_MAX})`} aria-label="비교할 선박 검색" />
          {found.length > 0 && <ul className="sugg">{found.map(({ s }) => <li key={s.imo}><button className="sugg-b" onClick={() => add(s.imo)}><b>{s.n}</b><span className="muted small">{typeKo(s.t)} · IMO {s.imo}{ids.includes(s.imo) ? " · 추가됨" : ""}</span></button></li>)}</ul>}
        </div>
        {sel.length > 0 && <><button className="btn ghost sm" onClick={csv}>CSV</button><button className="btn ghost sm" onClick={clearCompare}>모두 빼기</button></>}
      </div>
      {msg && <p className="notice">{msg}</p>}
      {types.size > 1 && <p className="notice">선종이 서로 다른 선박이 섞여 있습니다. 해상 효율·연간 CO₂ 원래 값으로 우열을 판단하지 마십시오.</p>}
      {!sel.length ? (
        <div className="card"><Empty title="비교할 선박을 추가하세요"><p>위 검색창이나 선박 진단 화면의 "비교에 추가"로 선박을 담을 수 있습니다.</p></Empty></div>
      ) : (
        <div className="card cmp-card">
          <div className="tbl">
            <table className="t cmp" style={{ ["--n" as string]: sel.length }}>
              <thead>
                <tr>
                  <th />
                  {sel.map((s) => (
                    <th key={s.imo}>
                      <ShipPhoto type={s.t} small />
                      <a href={`#/ship/${s.imo}`}><b>{s.n}</b></a>
                      <span className="sub">IMO {s.imo}</span>
                      <button className="link" onClick={() => toggleCompare(s.imo)}>빼기</button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map(([l, f]) => <tr key={l}><td>{l}</td>{sel.map((s) => <td key={s.imo}>{f(s)}</td>)}</tr>)}
                <tr className="cmp-sec"><td colSpan={sel.length + 1}>네 가지 착시 점검</td></tr>
                {ILLUSIONS.map((x) => (
                  <tr key={x.k}><td>{x.n} {x.name}</td>{sel.map((s) => { const c = illusionCards(s, meta)[x.k]; return <td key={s.imo}><span className={`ill-tag ${c.on ? "on" : ""}`}>{c.on ? "해당" : "해당 없음"}</span></td>; })}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
