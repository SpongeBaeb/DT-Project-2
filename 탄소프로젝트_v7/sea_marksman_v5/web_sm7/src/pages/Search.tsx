// 배 찾기: 이름·IMO·옛 이름·회사로 찾고, 종류·크기·선령·연료·유형·착시 사정·꾸준함으로 거른다.
// 검색어·필터·정렬·페이지·스크롤 위치는 이 탭(sessionStorage)에 남겨, 진단을 보고 돌아와도 그대로 둔다.
// 주소에 조건(?type= 등)이 있으면 그 조건으로 새로 시작한다.
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Meta, Ship, SignalKey } from "../data";
import { exposureName, isHigh, LIST_NAME, profileName, SIGNALS, SIZE_Q, typeKo, vsPeer } from "../data";
import { downloadCsv, go, toggleCompare, useCompare } from "../store";
import { num, pct, times } from "../format";
import { verdictOf, VERDICT, type VerdictKey } from "../verdict";
import { Empty, Grade_, ListBadge, prob, SearchIcon, SIGNAL_PLAIN, Signals, Verdict } from "../components/ui";
import Reticle from "../components/Reticle";
import ShipPhoto from "../components/ShipPhoto";

type Step = "all" | "clean" | "high";
type SortKey = "vs" | "z" | "de" | "br" | "age" | "name";
const SORTS: { k: SortKey; label: string }[] = [
  { k: "vs", label: "동급 대비 순" }, { k: "z", label: "위치 z 순" }, { k: "de", label: "D·E 확률 순" }, { k: "br", label: "정박 배출 순" }, { k: "age", label: "선령 순" }, { k: "name", label: "이름순" },
];
const PAGE = 20;
const FUEL_GROUPS = ["석유계", "LNG 계열", "LPG 추정", "기타 대체연료", "대체연료(구분 불가)"];
const VK: VerdictKey[] = ["real", "year", "berth", "check", "same", "good"];

const SAVE = "sm.search.v7";
interface Saved { step: Step; q: string; sel: Sel; age: [string, string]; sort: SortKey; page: number; y: number }
const loadSaved = (): Saved | null => { try { const v = sessionStorage.getItem(SAVE); return v ? (JSON.parse(v) as Saved) : null; } catch { return null; } };

interface Sel { type: string[]; size: number[]; fuel: string[]; sig: SignalKey[]; exp: number[]; prof: number[]; vd: VerdictKey[]; lst: string[]; oo: string[]; yr: string[] }
const EMPTY_SEL: Sel = { type: [], size: [], fuel: [], sig: [], exp: [], prof: [], vd: [], lst: [], oo: [], yr: [] };

function Group({ title, children, note, open = false }: { title: string; children: ReactNode; note?: ReactNode; open?: boolean }) {
  return <details className="fg" open={open}><summary><h4>{title}</h4></summary>{children}{note && <p>{note}</p>}</details>;
}

export default function Search({ ships, meta, query }: { ships: Ship[]; meta: Meta; query: URLSearchParams }) {
  const by = meta.base_year;
  const [saved] = useState(() => ([...query.keys()].length ? null : loadSaved()));
  const qStep = (query.get("step") as Step) || "all";
  const [step, setStep] = useState<Step>(saved?.step ?? qStep);
  const [q, setQ] = useState(saved?.q ?? query.get("q") ?? "");
  const [sel, setSel] = useState<Sel>(saved ? { ...EMPTY_SEL, ...saved.sel } : { ...EMPTY_SEL, type: query.get("type") ? [query.get("type")!] : [], yr: query.get("q") ? [] : ["cur"] });
  const [age, setAge] = useState<[string, string]>(saved?.age ?? ["", ""]);
  const [sort, setSort] = useState<SortKey>(saved?.sort ?? (qStep === "high" ? "z" : "vs"));
  const [page, setPage] = useState(saved?.page ?? 0);
  const [open, setOpen] = useState(false);
  // 조건이 바뀌면 첫 페이지로. 복원 직후(StrictMode 이중 실행 포함)에는 바꾸지 않는다
  const cond = JSON.stringify([step, q, sel, age, sort]);
  const prevCond = useRef(cond);
  useEffect(() => { if (prevCond.current !== cond) { prevCond.current = cond; setPage(0); } }, [cond]);
  useEffect(() => {
    const put = () => { if (!window.location.hash.startsWith("#/search")) return; try { sessionStorage.setItem(SAVE, JSON.stringify({ step, q, sel, age, sort, page, y: window.scrollY } satisfies Saved)); } catch { /* 저장 실패 시 복원만 안 됨 */ } };
    put();
    window.addEventListener("scroll", put, { passive: true });
    return () => window.removeEventListener("scroll", put);
  }, [step, q, sel, age, sort, page]);
  // App이 화면 전환 때 맨 위로 올린 뒤에 복원한다
  useEffect(() => { if (saved?.y) { const t = window.setTimeout(() => window.scrollTo(0, saved.y), 60); return () => window.clearTimeout(t); } }, [saved]);
  const cmp = useCompare();
  const yrOf = (s: Ship) => (s.ly === by ? "cur" : "old");
  const vOf = useMemo(() => new Map(ships.map((s) => [s.imo, verdictOf(s)])), [ships]);

  const text = q.trim().toLowerCase();
  const pass = (s: Ship, skip?: keyof Sel) => {
    if (text && !(s.n.toLowerCase().includes(text) || String(s.imo).includes(text) || (s.co ?? "").toLowerCase().includes(text) || s.on?.some((n) => n.toLowerCase().includes(text)))) return false;
    if (skip !== "type" && sel.type.length && !sel.type.includes(s.t)) return false;
    if (skip !== "size" && sel.size.length && !sel.size.includes(s.sq)) return false;
    if (age[0] !== "" && s.age < Number(age[0])) return false;
    if (age[1] !== "" && s.age > Number(age[1])) return false;
    if (skip !== "fuel" && sel.fuel.length && !sel.fuel.includes(s.fg ?? "")) return false;
    if (skip !== "lst" && sel.lst.length && !sel.lst.includes(s.lst ?? "none")) return false;
    if (skip !== "oo" && sel.oo.length && !sel.oo.includes(s.oo ? "y" : "n")) return false;
    if (skip !== "yr" && sel.yr.length && !sel.yr.includes(yrOf(s))) return false;
    if (skip !== "sig" && sel.sig.length && !sel.sig.some((k) => s.sig?.includes(k))) return false;
    if (skip !== "vd" && sel.vd.length && !sel.vd.includes(vOf.get(s.imo)!)) return false;
    if (skip !== "exp" && sel.exp.length && !(s.tx !== undefined && sel.exp.includes(s.tx))) return false;
    if (skip !== "prof" && sel.prof.length && !(s.ta !== undefined && sel.prof.includes(s.ta))) return false;
    return true;
  };
  const base = useMemo(() => ships.filter((s) => pass(s)), [ships, text, sel, age]); // eslint-disable-line react-hooks/exhaustive-deps
  const counts = useMemo(() => {
    const c = (k: keyof Sel, key: (s: Ship) => (string | number | undefined)[]) => {
      const m = new Map<string, number>();
      for (const s of ships) if (pass(s, k)) for (const v of key(s)) if (v !== undefined) m.set(String(v), (m.get(String(v)) ?? 0) + 1);
      return m;
    };
    return {
      type: c("type", (s) => [s.t]), size: c("size", (s) => [s.sq]), fuel: c("fuel", (s) => [s.fg]), sig: c("sig", (s) => s.sig ?? []),
      vd: c("vd", (s) => [vOf.get(s.imo)]), exp: c("exp", (s) => [s.tx]), prof: c("prof", (s) => [s.ta]),
      lst: c("lst", (s) => [s.lst ?? "none"]), oo: c("oo", (s) => [s.oo ? "y" : "n"]), yr: c("yr", (s) => [yrOf(s)]),
    };
  }, [ships, text, sel, age]); // eslint-disable-line react-hooks/exhaustive-deps

  const clean = base.filter((s) => !s.sig?.length);
  const high = clean.filter(isHigh);
  const list = step === "all" ? base : step === "clean" ? clean : high;
  const sorted = useMemo(() => {
    const key: Record<SortKey, (s: Ship) => number | string> = { vs: vsPeer, z: (s) => s.z ?? -99, de: (s) => s.pde?.[0] ?? -1, br: (s) => s.br ?? -1, age: (s) => s.age, name: (s) => s.n };
    const f = key[sort];
    return [...list].sort((a, b) => { const x = f(a), y = f(b); return typeof x === "string" ? x.localeCompare(y as string) : (y as number) - (x as number); });
  }, [list, sort]);
  const shown = sorted.slice(page * PAGE, (page + 1) * PAGE);
  const pages = Math.ceil(sorted.length / PAGE);

  const typeList = Object.keys(meta.types).sort((a, b) => meta.types[b].ships - meta.types[a].ships);
  const expIds = Object.keys(meta.type_names.exposure).map(Number), profIds = Object.keys(meta.type_names.profile).map(Number);
  const toggle = <K extends keyof Sel>(k: K, v: Sel[K][number]) =>
    setSel((p) => ({ ...p, [k]: (p[k] as unknown[]).includes(v) ? (p[k] as unknown[]).filter((x) => x !== v) : [...(p[k] as unknown[]), v] }));
  const nOn = Object.values(sel).reduce((a, v) => a + v.length, 0) + (age[0] !== "" || age[1] !== "" ? 1 : 0) + (step !== "all" ? 1 : 0);
  const reset = () => { setSel(EMPTY_SEL); setAge(["", ""]); setStep("all"); };
  const opt = <K extends keyof Sel>(k: K, v: Sel[K][number], name: ReactNode, desc?: ReactNode) => {
    const n = counts[k].get(String(v)) ?? 0;
    const on = (sel[k] as unknown[]).includes(v);
    return (
      <label key={String(v)} className={`fo ${n === 0 && !on ? "dim" : ""}`}>
        <input type="checkbox" checked={on} onChange={() => toggle(k, v)} />
        <span>{name}{desc && <small>{desc}</small>}</span>
        <span className="n">{num(n)}</span>
      </label>
    );
  };
  const csv = () => downloadCsv(`sea-marksman_${step}.csv`, [
    ["IMO", "선박명", "구 선명", "선종", "크기", "건조연도", "선령", "관리회사", "진단 연도", "판정", "해상 효율(kg/해리)", "동급 중간값", "같은 조건 예측값", "동급 대비 %", "위치 z", "정박 배출 배수", "착시 신호", "이상 운항", "CII 등급", "다음 해 D·E 확률", "다음 해 리스트", "유지 확률", "3년 뒤 해상 효율 중앙값", "연료 그룹", "노출도 유형", "선령·설계 유형", "데이터", "모델"],
    ...sorted.map((s) => [s.imo, s.n, s.on?.join(" / "), typeKo(s.t), SIZE_Q[s.sq], s.b, s.age, s.co, s.ly, VERDICT[vOf.get(s.imo)!].name, s.sea, s.peer, s.exp, vsPeer(s).toFixed(1), s.z, s.br, s.sig?.map((k) => SIGNAL_PLAIN[k][0]).join(" "), s.oo ? "Y" : "", s.cii, s.pde?.[0], s.lst ? LIST_NAME[s.lst] : "", s.pp, s.fc?.[2][0], s.fg, exposureName(meta, s.tx), profileName(meta, s.ta), meta.data_hash, meta.model_version]),
  ]);

  return (
    <>
      <section className="sr-top">
        <div className="wrap">
          <div className="sr-line">
            <p className="sr-note">같은 선종·연도·크기의 배보다 항해 1해리에 CO₂를 얼마나 더 내는지로 줄을 세웁니다. 기본은 {by}년 보고 선박입니다.</p>
            <div className="sr-box"><SearchIcon /><input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="선박명, IMO 번호, 구 선명, 관리회사" aria-label="선박 검색" /></div>
          </div>
        </div>
      </section>

      <div className="wrap sr-body">
        <aside className={`flt ${open ? "open" : ""}`} aria-label="필터">
          <div className="flt-h"><b>필터</b>{nOn > 0 ? <button className="link" onClick={reset}>초기화 ({nOn})</button> : <span className="muted small">조건 없음</span>}</div>
          <Group open title="판정">{VK.map((k) => opt("vd", k, VERDICT[k].name, VERDICT[k].line))}</Group>
          <Group open title={`${by + 1}년 리스트`} note={<><a href="#/table">리스트 표</a>에서 순위를 확인합니다.</>}>{opt("lst", "target", "영업 타깃", "다음 해 CII D·E 확률 기준 이상")}{opt("lst", "watch", "관찰", "A~C등급 · 감축 요구 미달 가능성 높음")}{opt("lst", "none", "해당 없음")}</Group>
          <Group title="착시 신호" note="하나 이상 해당하는 선박을 표시합니다.">{SIGNALS.map((k) => opt("sig", k, SIGNAL_PLAIN[k][0], SIGNAL_PLAIN[k][1]))}</Group>
          <Group open title="선종">{typeList.map((t) => opt("type", t, typeKo(t)))}</Group>
          <Group title="크기 (선종 내 4분위)">{SIZE_Q.map((l, i) => opt("size", i, l))}</Group>
          <Group title="선령 (년)">
            <div className="range2">
              <input type="number" min={0} value={age[0]} onChange={(e) => setAge([e.target.value, age[1]])} placeholder="부터" aria-label="선령 최소" />
              <span className="muted">~</span>
              <input type="number" min={0} value={age[1]} onChange={(e) => setAge([age[0], e.target.value])} placeholder="까지" aria-label="선령 최대" />
            </div>
          </Group>
          <Group title="연료 그룹" note="연료 1톤당 CO₂와 CH₄·N₂O 보고값 기준 추정">{FUEL_GROUPS.map((g) => opt("fuel", g, g))}</Group>
          <Group title="선박 유형" note={<>EU 규제 노출도 × 선령·설계 2축 K-평균 분류. <a href="#/fleet">교차표</a></>}>
            {expIds.map((id) => opt("exp", id, exposureName(meta, id)))}
            <div style={{ height: 6 }} />
            {profIds.map((id) => opt("prof", id, profileName(meta, id)))}
          </Group>
          <Group title="운항 패턴">{opt("oo", "y", "이상 운항", "선종별 운항 군집에서 먼 상위 2.5%")}{opt("oo", "n", "일반")}</Group>
          <Group title="보고 연도">{opt("yr", "cur", `${by}년 보고`)}{opt("yr", "old", "이전 연도에 보고 종료", "마지막 보고 연도 기준 진단")}</Group>
        </aside>

        <section aria-label="검색 결과">
          <div className="res-bar">
            <span className="res-n"><b>{num(sorted.length)}</b>척</span>
            <button className="btn ghost sm only-m" onClick={() => setOpen((o) => !o)}>필터{nOn ? ` (${nOn})` : ""}</button>
            <div className="sorts" role="tablist" aria-label="정렬">
              {SORTS.map((s) => <button key={s.k} role="tab" aria-selected={sort === s.k} className={sort === s.k ? "on" : ""} onClick={() => setSort(s.k)}>{s.label}</button>)}
            </div>
            <button className="btn ghost sm" onClick={csv}>CSV</button>
          </div>
          {nOn > 0 && (
            <div className="chips">
              {step !== "all" && <button className="chip" onClick={() => setStep("all")}>{step === "clean" ? "착시 신호 없음" : "착시 신호 없음 · 지속 초과"} ×</button>}
              {sel.vd.map((v) => <button key={`v${v}`} className="chip" onClick={() => toggle("vd", v)}>{VERDICT[v].name} ×</button>)}
              {sel.type.map((v) => <button key={`t${v}`} className="chip" onClick={() => toggle("type", v)}>{typeKo(v)} ×</button>)}
              {sel.size.map((v) => <button key={`s${v}`} className="chip" onClick={() => toggle("size", v)}>크기 {SIZE_Q[v]} ×</button>)}
              {sel.fuel.map((v) => <button key={`f${v}`} className="chip" onClick={() => toggle("fuel", v)}>{v} ×</button>)}
              {sel.lst.map((v) => <button key={`l${v}`} className="chip" onClick={() => toggle("lst", v)}>{v === "none" ? "리스트 해당 없음" : LIST_NAME[v as "target"]} ×</button>)}
              {sel.oo.map((v) => <button key={`o${v}`} className="chip" onClick={() => toggle("oo", v)}>{v === "y" ? "이상 운항" : "일반 운항"} ×</button>)}
              {sel.yr.map((v) => <button key={`y${v}`} className="chip" onClick={() => toggle("yr", v)}>{v === "cur" ? `${by}년 보고` : "이전 연도 보고 종료"} ×</button>)}
              {sel.sig.map((v) => <button key={`g${v}`} className="chip" onClick={() => toggle("sig", v)}>{SIGNAL_PLAIN[v][0]} ×</button>)}
              {sel.exp.map((v) => <button key={`e${v}`} className="chip" onClick={() => toggle("exp", v)}>{exposureName(meta, v)} ×</button>)}
              {sel.prof.map((v) => <button key={`p${v}`} className="chip" onClick={() => toggle("prof", v)}>{profileName(meta, v)} ×</button>)}
              {(age[0] !== "" || age[1] !== "") && <button className="chip" onClick={() => setAge(["", ""])}>선령 {age[0] || "0"}~{age[1]}년 ×</button>}
            </div>
          )}
          {!shown.length ? (
            <Empty title="조건에 맞는 선박이 없습니다"><p>필터 조건을 줄여 보세요.</p><button className="btn" style={{ marginTop: 12 }} onClick={() => { reset(); setQ(""); }}>필터 초기화</button></Empty>
          ) : (
            <ol className="ships">
              {shown.map((s) => {
                const d = vsPeer(s);
                return (
                  <li key={s.imo} className="ship-row">
                    <a className="art" href={`#/ship/${s.imo}`} tabIndex={-1} aria-hidden="true">
                      <ShipPhoto type={s.t} seed={s.imo % 97} small />
                    </a>
                    <div>
                      <div className="nm"><a href={`#/ship/${s.imo}`}>{s.n}</a><Verdict k={vOf.get(s.imo)!} /><ListBadge k={s.lst} /><Signals sig={s.sig} none="" /></div>
                      <div className="meta">{typeKo(s.t)} · 크기 {SIZE_Q[s.sq]} · {s.b ?? "–"}년 건조 · {s.dwt ? `${num(s.dwt)} DWT` : s.gt ? `${num(s.gt)} GT` : ""}{s.ly !== by ? ` · ${s.ly}년 보고 기준` : ""}</div>
                      <div className="meta m2">{s.co ?? "관리회사 정보 없음"}{s.on?.length ? ` · 구 선명 ${s.on[s.on.length - 1]}` : ""} · 정박 배출 예측값의 {times(s.br)}</div>
                    </div>
                    <div className="nums">
                      <div className={`big ${d > 0 ? "up" : "down"}`}>{pct(d)}</div>
                      <div className="cap">동급 대비 · {num(s.sea)} / {num(s.peer)} kg/해리</div>
                      <div style={{ marginTop: 4 }}><Reticle sea={s.sea} peer={s.peer} compact /></div>
                    </div>
                    <div className="act">
                      <span className="line2">CII <Grade_ g={s.cii} sm />{s.pde ? <span className="muted small"> D·E {prob(s.pde[0])}</span> : null}</span>
                      <span className="line2">위치 z <b className={isHigh(s) ? "up" : ""}>{s.z === undefined ? "–" : s.z.toFixed(1)}</b></span>
                      <button className="btn sm" onClick={() => go(`/ship/${s.imo}`)}>진단 보기</button>
                      <button className={`btn ghost sm ${cmp.includes(s.imo) ? "on" : ""}`} aria-pressed={cmp.includes(s.imo)} onClick={() => toggleCompare(s.imo)}>{cmp.includes(s.imo) ? "비교 중" : "비교"}</button>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
          {pages > 1 && (
            <nav className="pager" aria-label="페이지">
              <button disabled={page === 0} onClick={() => { setPage(page - 1); window.scrollTo({ top: 0 }); }}>이전</button>
              <span>{page + 1} / {num(pages)}</span>
              <button disabled={page >= pages - 1} onClick={() => { setPage(page + 1); window.scrollTo({ top: 0 }); }}>다음</button>
            </nav>
          )}
        </section>
      </div>
    </>
  );
}
