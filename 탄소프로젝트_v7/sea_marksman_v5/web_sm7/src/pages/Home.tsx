// 홈 (발표 A 파트 흐름): CII 한 글자 → 네 가지 착시와 해결(TIGANI) → 규제 배경 → 선별 → 진단 항목 → 다음 해 리스트 → 검증 → 바로가기
import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { FactorKey, HistRow, Meta, Ship } from "../data";
import { FACTORS, loadHist, typeKo, vsExp, vsPeer } from "../data";
import { CiiYears, illusionEvidence, ILLUSIONS, type IllusionKey } from "../components/Illusions";
import { go } from "../store";
import { num, pct, times, tonnes } from "../format";
import { prob, Reveal, SearchIcon } from "../components/ui";
import Scope from "../components/Scope";

export function useShipFinder(ships: Ship[], q: string, limit = 8) {
  return useMemo(() => {
    const t = q.trim().toLowerCase();
    if (t.length < 2) return [];
    const out: { s: Ship; via?: string }[] = [];
    for (const s of ships) {
      if (String(s.imo).startsWith(t) || s.n.toLowerCase().includes(t)) out.push({ s });
      else { const o = s.on?.find((n) => n.toLowerCase().includes(t)); if (o) out.push({ s, via: o }); }
      if (out.length >= limit) break;
    }
    return out;
  }, [ships, q, limit]);
}

export function FindBox({ ships, placeholder = "선박명, IMO 번호, 구 선명 (예: TIGANI)" }: { ships: Ship[]; placeholder?: string }) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const found = useShipFinder(ships, q, 6);
  return (
    <form className="find" role="search" onSubmit={(e) => { e.preventDefault(); if (found[sel]) go(`/ship/${found[sel].s.imo}`); else if (q.trim()) go(`/search?q=${encodeURIComponent(q.trim())}`); }}>
      <SearchIcon />
      <input value={q} onChange={(e) => { setQ(e.target.value); setSel(0); }} placeholder={placeholder} aria-label="선박 검색" autoComplete="off"
        onKeyDown={(e) => { if (e.key === "ArrowDown") { e.preventDefault(); setSel((x) => Math.min(x + 1, found.length - 1)); } if (e.key === "ArrowUp") { e.preventDefault(); setSel((x) => Math.max(0, x - 1)); } }} />
      {found.length > 0 && (
        <ul className="sugg" role="listbox">
          {found.map(({ s, via }, i) => (
            <li key={s.imo}><a href={`#/ship/${s.imo}`} className={i === sel ? "on" : ""}>
              <span><b>{s.n}</b> <span className="muted small">{via ? `구 선명 ${via} · ` : ""}IMO {s.imo}</span></span>
              <span className="muted small">{typeKo(s.t)} · {s.b ?? "–"}년</span>
            </a></li>
          ))}
        </ul>
      )}
    </form>
  );
}

export const FACTOR_NAME: Record<FactorKey, string> = {
  size: "선박 크기", speed: "평균 속력(대기 포함)", intra: "EU 역내 비중", hours: "해상 시간", age: "선령·설계", fuel: "대체연료", ice: "내빙 등급", other: "기타 보정", rest: "미설명 잔차",
};

export default function Home({ ships, all, meta }: { ships: Ship[]; all: Ship[]; meta: Meta }) {
  const by = meta.base_year;
  const f = meta.funnel;
  const [th, setTh] = useState<HistRow[] | null>(null);
  const tigani = ships.find((s) => s.n === "TIGANI");
  useEffect(() => { if (tigani) loadHist().then((h) => setTh(h[String(tigani.imo)] ?? null)).catch(() => undefined); }, [tigani]);
  const nexus = ships.find((s) => s.n === "NEXUS" && s.sig?.includes("report"));
  const oscar = ships.find((s) => s.n === "MSC OSCAR");
  // ③ 예시: 올해 같은 조건 대비 크게 높지만 여러 해 위치는 통상 범위인 배 (없으면 조건에 맞는 배 중 CO₂가 큰 배)
  const vega = useMemo(() => ships.find((s) => s.n === "MSC VEGA" && (s.z ?? 9) < 1) ?? ships
    .filter((s) => !s.sig?.length && s.z !== undefined && Math.abs(s.z) < 1 && vsExp(s) > 25 && s.zy >= 5 && (s.cii === "D" || s.cii === "E"))
    .sort((a, b) => b.co2 - a.co2)[0], [ships]);
  const v = meta.validation?.position;
  const ex = tigani;
  const exTop = ex ? FACTORS.filter((k) => ex.c[k] > 0).sort((a, b) => ex.c[b] - ex.c[a])[0] : undefined;
  const L = meta.list;
  const topTargets = useMemo(() => ships.filter((s) => s.lst === "target").sort((a, b) => (a.lr ?? 1e9) - (b.lr ?? 1e9)).slice(0, 5), [ships]);
  const ev = illusionEvidence(meta);
  const egs: Record<IllusionKey, ReactNode> = {
    berth: tigani && <a href={`#/ship/${tigani.imo}`}>{tigani.n}: CO₂의 {Math.round((tigani.bs ?? 0) * 100)}%가 정박, 예측의 {times(tigani.br)}{tigani.ciir && tigani.bs ? ` · 정박을 빼면 CII 비율 ${tigani.ciir.toFixed(2)} → 약 ${(tigani.ciir * (1 - tigani.bs)).toFixed(2)}` : ""}</a>,
    cond: oscar && <a href={`#/ship/${oscar.imo}`}>{oscar.n}: 동급 대비 {pct(vsPeer(oscar))}, 같은 조건 대비 {pct(vsExp(oscar))}</a>,
    year: vega && <a href={`#/ship/${vega.imo}`}>{vega.n}: 올해 같은 조건 대비 {pct(vsExp(vega))}, {vega.zy}년 위치 z {vega.z?.toFixed(1)}</a>,
    report: nexus && <a href={`#/ship/${nexus.imo}`}>{nexus.n}: CII {nexus.cii}등급이나 보고값이 물리 범위 밖</a>,
  };
  const exBerth = tigani?.ciir && tigani.bs ? tigani.ciir * (1 - tigani.bs) : undefined;

  return (
    <>
      <section className="hero">
        <div className="wrap hero-grid">
          <div>
            <h1>CII 한 글자 뒤의<br />진짜 원인을 나눠 봅니다</h1>
            <p className="hero-sub">CII 등급은 정박 배출, 비교 조건, 한 해의 출렁임, 보고 오류를 한 글자에 섞습니다. EU MRV {by}년 보고 {num(f.all)}척을 같은 조건의 선박과 비교해 착시를 걷어 내고, 판단할 근거를 나눠 보여 줍니다.</p>
            <FindBox ships={all} />
            <div className="hero-links">
              <a href="#/ship/9776767">예시: TIGANI 진단</a><span>·</span>
              <a href="#/list">{L.year}년 영업 타깃 {num(L.target)}척</a><span>·</span>
              <a href="#/my">내 선박 진단</a>
            </div>
          </div>
          <Scope ships={ships} meta={meta} />
        </div>
      </section>

      <section className="band deep">
        <div className="wrap">
          <Reveal className="band-h">
            <h2>CII 한 글자, 네 가지 착시</h2>
            <p>CII = CO₂ ÷ (크기 × 거리). 매년 A~E 한 글자로 매겨지지만, 그 글자는 무엇을·누구와·언제·어떤 데이터로 비교했는지를 구분하지 못합니다.</p>
          </Reveal>
          {tigani && (
            <Reveal className="tg">
              <div className="tg-chart">{th ? <CiiYears hist={th} height={190} /> : <p className="muted">불러오는 중…</p>}</div>
              <div className="tg-txt">
                <span className="k">유조선 {tigani.n} · 연도별 CII 등급</span>
                <h3>5년 A, 2024년 B, {by}년 E. 정말 나쁜 배일까?</h3>
                <p>{by}년 CO₂의 <b>{Math.round((tigani.bs ?? 0) * 100)}%</b>가 정박 중에 나왔습니다. 정박을 빼면 CII 비율은 {tigani.ciir?.toFixed(2)}에서 약 <b>{exBerth?.toFixed(2)}</b>로, 예년 수준입니다. 한 글자 E 뒤에는 정박 급증과 해상 효율의 완만한 악화(동급 대비 {pct(vsPeer(tigani))})라는 두 이야기가 있습니다.</p>
                <a className="btn light" href={`#/ship/${tigani.imo}`}>{tigani.n} 진단 보기</a>
              </div>
            </Reveal>
          )}
          <div className="ill4">
            {ILLUSIONS.map((x) => (
              <Reveal key={x.k} className="ill4-card">
                <div className="ill-h"><span className="ill-n">{x.n}</span><b>{x.name}</b></div>
                <p className="ill4-ev">{ev[x.k]}</p>
                <p className="ill4-fix"><span>해결</span>{x.fix}</p>
                {egs[x.k] && <p className="ill4-eg">{egs[x.k]}</p>}
              </Reveal>
            ))}
          </div>
          <p className="ill4-note">근거는 {by}년 보고 선박 기준이며 CII 등급은 MRV 자료로 계산한 근사 등급입니다. <a href="#/method">지표와 근거</a></p>
        </div>
      </section>

      <section className="band white">
        <div className="wrap reg">
          <Reveal className="band-h">
            <h2>기준은 강해지고, 대가는 무겁습니다</h2>
            <p>CII 감축률은 2026년 11%에서 2030년 21.5%로 커집니다. 같은 배도 해마다 등급이 내려갈 수 있습니다.</p>
          </Reveal>
          <ol className="reg-steps">
            <li><b>개선 계획</b><span>D등급 3년 연속 또는 E등급 1회이면 시정 조치 계획(SEEMP) 제출</span></li>
            <li><b>계약 · 금융</b><span>용선 계약의 CII 조항, 금융기관의 탈탄소 정렬 평가</span></li>
            <li><b>EU 규제</b><span>EU ETS 배출권 비용, FuelEU Maritime 불이행 벌금·입항 제한</span></li>
          </ol>
          <p className="muted small">CII 등급 자체에는 벌금이 없습니다. 벌금과 입항 제한은 EU 규제(배출권·FuelEU)의 불이익입니다. 그래서 등급이 왜 나빠졌는지 정확히 아는 것이 먼저입니다.</p>
        </div>
      </section>

      <section className="band">
        <div className="wrap">
          <Reveal className="band-h">
            <h2>착시를 걷어 내면 {num(f.all)}척 중 {num(f.high)}척</h2>
            <p>착시 신호가 있는 선박을 제외한 뒤, 같은 조건 대비 여러 해 지속적으로 높은 선박(위치 z ≥ 2)을 선별합니다.</p>
          </Reveal>
          <Reveal className="sieve">
            {([
              ["", f.all, "전체 보고 선박", 100],
              ["?step=clean", f.clean, `착시 신호 ${num(f.all - f.clean)}척 제외`, (f.clean / f.all) * 100],
              ["?step=high", f.high, "다년 지속 초과 (z ≥ 2)", 2],
            ] as const).map(([q, n, l, w]) => (
              <a key={l} className="sieve-row" href={`#/search${q}`}>
                <span className="sieve-n">{num(n)}<small>척</small></span>
                <span className="sieve-bar" style={{ width: `${w}%` }}><span>{l}</span></span>
              </a>
            ))}
          </Reveal>
          <p className="sieve-note">해상 효율 = (CO₂ − 정박 중 CO₂) ÷ 항해 거리. 같은 조건 = 선종·크기·연도에 평균 속력·해상 시간·EU 역내 비중·선령·설계·내빙·연료를 맞춘 모델 예측값. {by}년 보고 기준.</p>
        </div>
      </section>

      <section className="band white">
        <div className="wrap">
          <Reveal className="band-h">
            <h2>선박별 진단 항목</h2>
            <p>선박 한 척의 CII 등급을 네 가지 착시로 나눠 점검한 뒤, 다섯 가지 핵심 질문의 근거를 한 화면에 제시합니다.{ex && <> 예시: {ex.n}.</>}</p>
          </Reveal>
          <ol className="qlist">
            <li><b>동급 대비 해상 효율</b><p>같은 선종·연도·크기 4분위 선박과의 차이, 다년 지속성(위치 z)</p>{ex && <span className="eg">{ex.n}: <b>{pct(vsPeer(ex))}</b></span>}</li>
            <li><b>차이 요인 분해</b><p>속력·해상 시간·선령·설계 등 요인별 기여와 정박 배출 비교</p>{ex && exTop && <span className="eg">{ex.n}: 주요 요인 {FACTOR_NAME[exTop]}</span>}</li>
            <li><b>1~3년 전망</b><p>해상 효율 중앙값과 80% 구간, CII D·E 등급 확률</p>{ex && <span className="eg">{ex.n}: {ex.pde ? `${by + 1}년 D·E 확률 ${prob(ex.pde[0])}` : "미산출"}</span>}</li>
            <li><b>연간 비용</b><p>가격 시나리오별 연료비·탄소 비용, 변화 분해, 개선 시나리오의 회수 기간</p>{ex && <span className="eg">{ex.n}: 연간 CO₂ {tonnes(ex.co2)}</span>}</li>
            <li><b>데이터 점검</b><p>착시 신호 5종, 이상 운항, 모델 적용 범위(외삽)</p>{ex && <span className="eg">{ex.n}: 정박 배출 예측값의 <b>{times(ex.br)}</b></span>}</li>
          </ol>
          {ex && <p style={{ marginTop: 22 }}><a className="btn" href={`#/ship/${ex.imo}`}>{ex.n} 진단 보기</a></p>}
        </div>
      </section>

      <section className="band">
        <div className="wrap">
          <Reveal className="band-h">
            <h2>{L.year}년 리스트</h2>
            <p>{by}년 보고 {num(f.all)}척 가운데 {L.year}년 CII D·E 확률이 {prob(L.de_cut)} 이상인 영업 타깃과, 현재 A~C등급이나 감축 요구 미달 확률이 높은 관찰 대상을 선정합니다.</p>
          </Reveal>
          <div className="list-split">
            <a className="ls-card t" href="#/list?tab=target"><b>{num(L.target)}<small>척</small></b><span>영업 타깃</span><em>{L.year}년 D·E 확률 {prob(L.de_cut)} 이상</em></a>
            <a className="ls-card w" href="#/list?tab=watch"><b>{num(L.watch)}<small>척</small></b><span>관찰</span><em>현재 A~C등급 · 미달 확률 {prob(L.p_star)} 이상</em></a>
            <ol className="ls-top">
              {topTargets.map((s) => <li key={s.imo}><a href={`#/ship/${s.imo}`}><b>{s.n}</b><span>{typeKo(s.t)} · CII {s.cii ?? "–"}</span><span>{prob(s.pde?.[0])}</span></a></li>)}
            </ol>
          </div>
        </div>
      </section>

      {v && Number.isFinite(v.retention_model) && (
        <section className="band white">
          <div className="wrap proof">
            <Reveal>
              <div className="big-stat">{Math.round(v.retention_model * 100)}%</div>
              <h2 style={{ marginTop: 16 }}>선별 결과의 유지율</h2>
              <p style={{ marginTop: 12, fontSize: 18, color: "var(--ink-2)" }}>{v.select_until ?? 2023}년까지의 자료로 지속 초과(위치 z ≥ 2)로 선별한 {num(v.n_selected)}척 중 {Math.round(v.retention_model * 100)}%가 이후 2개 연도에도 같은 조건 대비 10% 이상 높았습니다. 한 해 값으로 고르면 {Math.round(v.retention_single_year * 100)}%입니다.</p>
            </Reveal>
            <Reveal className="proof-bars">
              {([["다년 위치(z) 기준", v.retention_model, true], ["단년 기준", v.retention_single_year, false], ["무작위 선택", v.retention_random, false]] as const).map(([l, x, main]) => (
                <div key={l} className={`pb ${main ? "main" : ""}`}><span>{l}</span><span className="pb-t"><i style={{ width: `${x * 100}%` }} /></span><b>{Math.round(x * 100)}%</b></div>
              ))}
            </Reveal>
          </div>
        </section>
      )}

      <section className="band">
        <div className="wrap">
          <div className="go-cards">
            <a className="go-card" href="#/search?step=high"><b>지속 초과 선박</b><span>착시 신호가 없고 다년 지속 초과로 분류된 {num(f.high)}척</span><em>선박 찾기</em></a>
            <a className="go-card" href="#/list"><b>{L.year}년 리스트</b><span>영업 타깃 {num(L.target)}척, 관찰 {num(L.watch)}척의 순위와 CII D·E 확률</span><em>다음 해 리스트</em></a>
            <a className="go-card" href="#/my"><b>내 선박 진단</b><span>데이터에 없는 선박, 당해 연도 값, 신조선 계획값 입력</span><em>내 선박 진단</em></a>
            <a className="go-card" href="#/fleet"><b>선대 분석</b><span>선종·관리회사별 차이 요인 구성과 운항 유형 교차표</span><em>선대 보기</em></a>
            <a className="go-card" href="#/method"><b>지표와 근거</b><span>CII와 Sea Marksman의 차이, 네 가지 착시, 모델 검증과 서버 상태</span><em>지표와 근거</em></a>
          </div>
        </div>
      </section>
    </>
  );
}
