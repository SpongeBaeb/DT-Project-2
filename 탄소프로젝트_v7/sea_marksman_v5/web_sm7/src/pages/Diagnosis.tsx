// 선박 진단: 위쪽에 판정과 핵심 지표 5개, 아래는 탭으로 나눠 한 화면에 한 묶음만 보여 준다.
//   탭 이름은 영업 담당자가 묻는 질문 순서: 등급 해석 → 더 쓰는 이유 → 내년 등급 → 비용 → 비교 선박·자료 → 검증
//   탭마다 맨 위에 '결론'과 '영업에 쓰는 법'을 먼저 둔다.
import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { FactorKey, Grade, HistRow, Meta, Ship, ShipCost } from "../data";
import { exposureName, FACTORS, GRADES, isHigh, LIST_NAME, loadCost, loadHist, profileName, sistersOf, SIZE_Q, typeKo, vsExp, vsPeer } from "../data";
import { num, pct, times, tonnes } from "../format";
import { verdictOf, VERDICT } from "../verdict";
import { Card, CheckIcon, Empty, Grade_, Help, ListBadge, prob, SIGNAL_PLAIN, Verdict } from "../components/ui";
import Reticle from "../components/Reticle";
import ShipPhoto from "../components/ShipPhoto";
import ShipMap from "../components/ShipMap";
import ServerValues from "../components/ServerValues";
import { BerthChart, CauseBars, FanChart, TrendChart } from "../components/charts";
import { IllusionCheck } from "../components/Illusions";
import { clusterOf, type ClusterDetail } from "../shared";
import { toggleCompare, toggleWatch, useCompare, useWatch } from "../store";
import { FACTOR_NAME } from "./Home";

/** 백만 원 → 억 원 표기 */
export const eok = (m?: number | null, d = 1) => (m === undefined || m === null || !Number.isFinite(m) ? "–" : `${m < 0 ? "−" : ""}${(Math.abs(m) / 100).toLocaleString("ko-KR", { maximumFractionDigits: d, minimumFractionDigits: d })}억 원`);

type TabKey = "ill" | "eff" | "fc" | "cost" | "chk" | "srv";
const TABS: [TabKey, string, string][] = [
  ["ill", "등급 해석", "이 등급, 배 성능 탓인가"],
  ["eff", "더 쓰는 이유", "어디서 연료를 더 쓰나"],
  ["fc", "내년 등급", "그대로 두면 어떻게 되나"],
  ["cost", "비용", "내년에 얼마 드나"],
  ["chk", "비교 선박·자료", "누구와 비교하고, 믿을 만한가"],
  ["srv", "검증", "다른 계산과 맞나"],
];
const FN: Record<FactorKey, string> = { ...FACTOR_NAME, rest: "설명 안 되는 차이" };

/** 탭 맨 위: 이 선박에 대한 결론과 영업에 쓰는 법 */
function Decide({ a, use }: { a: ReactNode; use: ReactNode }) {
  return (
    <div className="decide">
      <div><span className="k">결론</span><p className="a">{a}</p></div>
      <div><span className="k">영업에 쓰는 법</span><p>{use}</p></div>
    </div>
  );
}
const initTab = (): TabKey => {
  const q = new URLSearchParams(window.location.hash.split("?")[1] ?? "").get("tab");
  return TABS.some(([k]) => k === q) ? (q as TabKey) : "ill";
};

export default function Diagnosis({ ships, meta, imo }: { ships: Ship[]; meta: Meta; imo: number }) {
  const s = ships.find((x) => x.imo === imo);
  const [hist, setHist] = useState<HistRow[] | null>(null);
  const [cost, setCost] = useState<ShipCost | null | undefined>(undefined);
  useEffect(() => { loadHist().then((h) => setHist(h[String(imo)] ?? [])).catch(() => setHist([])); }, [imo]);
  useEffect(() => { loadCost().then((c) => setCost(c[String(imo)] ?? null)).catch(() => setCost(null)); }, [imo]);
  const [cl, setCl] = useState<ClusterDetail | null | undefined>(undefined);
  useEffect(() => { clusterOf(imo).then(setCl).catch(() => setCl(null)); }, [imo]);
  const cmp = useCompare(), watch = useWatch();
  const [cmpMsg, setCmpMsg] = useState("");
  const [tab, setTab] = useState<TabKey>(initTab);
  const [seen, setSeen] = useState<Set<TabKey>>(() => new Set([initTab()]));
  const pick = (t: TabKey, scroll = false) => {
    setTab(t);
    setSeen((x) => new Set(x).add(t));
    window.history.replaceState(null, "", `#/ship/${imo}${t === "ill" ? "" : `?tab=${t}`}`);
    if (scroll) document.getElementById("dtabs")?.scrollIntoView({ block: "start", behavior: "smooth" });
  };
  const sis = useMemo(() => (s ? sistersOf(s, ships) : []), [s, ships]);
  const sisGrades = useMemo(() => {
    const cnt: Record<Grade, number> = { A: 0, B: 0, C: 0, D: 0, E: 0 };
    for (const x of sis) if (x.cii) cnt[x.cii]++;
    return cnt;
  }, [sis]);
  if (!s) return <div className="wrap pad"><Empty title={`IMO ${imo} 선박이 데이터에 없습니다`}><a href="#/search">선박 찾기</a></Empty></div>;

  const y = s.ly;
  const old = y !== meta.base_year;
  const k = verdictOf(s);
  const vs = vsPeer(s);
  const berthSig = !!s.sig?.includes("berth");
  const trend = (hist ?? []).map((r) => ({ y: r[0], v: (r[1] / r[2] - 1) * 100 }));
  const berthRows = (hist ?? []).map((r) => ({ y: r[0], ratio: r[3] > 0 && r[4] > 0 ? r[3] / r[4] : null }));
  const speedWait = meta.types[s.t]?.speed_is_wait ?? false;
  const f1 = s.fc?.[0], f3 = s.fc?.[2];
  const ups = trend.slice(1).filter((r, i) => r.v > trend[i].v).length;
  const reasons = FACTORS.filter((x) => s.c[x] > 0.5).sort((a, b) => s.c[b] - s.c[a]);
  const helps = FACTORS.filter((x) => s.c[x] < -0.5).sort((a, b) => s.c[a] - s.c[b]);
  const posSum = reasons.reduce((a, x) => a + s.c[x], 0);
  const sisBetter = sis.filter((x) => vsPeer(x) < vs).length;
  const otherSig = (s.sig ?? []).filter((x) => x !== "berth");
  const showPersist = s.pp !== undefined && (isHigh(s) || vsExp(s) > 10);
  const base = cost?.s?.["기준"];
  const ext = (s.w ?? []).filter((w) => w.includes("외삽"));
  const otherW = (s.w ?? []).filter((w) => !w.includes("외삽"));

  const chkNames = [...(s.sig ?? []).map((x) => SIGNAL_PLAIN[x][0]), ...(s.oo ? ["이상 운항"] : []), ...(ext.length ? ["학습 범위 밖 입력"] : [])];
  const nChk = chkNames.length;
  const top = reasons[0];
  const sigNames = otherSig.map((x) => SIGNAL_PLAIN[x][0]).join("·");

  // ── 탭별 결론과 쓰는 법 ──
  const illDecide: Record<typeof k, [ReactNode, ReactNode]> = {
    berth: [<>{s.cii ?? ""}등급의 원인은 <b>항구 정박</b>입니다. 정박을 빼면 항해 중 연료는 동급 대비 {pct(vs)}입니다.</>,
      <>선체·엔진 개조보다 정박 중 연료(보일러·발전기·육상전원)를 줄이는 제안이 먼저입니다. 정박을 빼면 CII 비율이 어떻게 바뀌는지 아래 ①에서 보여 줄 수 있습니다.</>],
    real: [<>여러 해 동안 같은 조건의 배보다 연료를 <b>꾸준히 더</b> 썼습니다. 배 자체 성능 문제일 가능성이 높습니다.</>,
      <>에너지 절감 장치·선체 개조·엔진 조정 제안의 우선 대상입니다. 근거는 '더 쓰는 이유' 탭의 원인 막대입니다.</>],
    year: [<>올해 한 해 나빴지만 여러 해로 보면 <b>통상 범위</b>입니다.</>,
      <>지금 개조를 권할 근거는 약합니다. 관심 목록에 넣고 다음 해 보고를 보고 판단하세요.</>],
    check: [<>보고값에 이상 신호({sigNames})가 있어 <b>등급과 비교를 그대로 믿기 어렵습니다</b>.</>,
      <>수치를 인용하기 전에 선주에게 보고값부터 확인하세요. 확인 전에는 제안 근거로 쓰지 않는 것이 안전합니다.</>],
    same: [<>동급과 <b>비슷한 수준</b>입니다. 성능 문제로 보기 어렵습니다.</>,
      <>성능 개선 영업 여지는 작습니다. 기준 강화로 등급이 떨어지는지는 '내년 등급' 탭에서 보세요.</>],
    good: [<>동급보다 연료를 <b>덜 씁니다</b>.</>, <>개조 영업 우선순위는 낮습니다. 동급 우수 사례로 다른 배 제안에 인용할 수 있습니다.</>],
  };
  const effUse: Record<FactorKey, ReactNode> = {
    rest: <>공개 자료(속력·크기·선령 등)로 설명되지 않는 차이입니다. 선체 오손·프로펠러·엔진 상태가 원인일 수 있어 선체 청소·프로펠러 연마·엔진 점검 제안이 맞습니다.</>,
    speed: speedWait ? <>대기·저속 운항이 섞인 결과입니다. 배 성능보다 항만 대기 관리(적시 입항) 제안이 맞습니다.</> : <>속력 운용 차이입니다. 감속 운항·항로 최적화 제안이 맞습니다.</>,
    age: <>선령·설계에서 오는 차이입니다. 에너지 절감 장치 개조나 대체 신조 제안 대상입니다.</>,
    hours: <>해상 시간(운항 패턴) 차이입니다. 배 성능 문제로 단정하기 어렵습니다.</>,
    intra: <>EU 역내 단거리 운항 비중에서 오는 차이입니다. 배 성능 문제로 단정하기 어렵습니다.</>,
    size: <>크기 차이에서 오는 몫입니다. 성능 문제가 아닙니다.</>,
    fuel: <>연료 종류에서 오는 차이입니다. 연료 전환 검토 대상입니다.</>,
    ice: <>내빙 설계에서 오는 차이입니다. 개조로 줄이기 어렵습니다.</>,
    other: <>기타 선박 조건에서 오는 차이입니다. 성능 문제로 보기 어렵습니다.</>,
  };
  const fcUse = !s.pde ? <>CII 등급 산정 대상이 아니어서 등급 전망이 없습니다. 해상 효율 예측만 참고하세요.</>
    : s.pde[0] >= meta.list.de_cut ? <>D·E가 거의 확실합니다. E 1년 또는 D 3년 연속이면 시정 계획을 내야 하므로, 선주가 개선책을 찾는 지금이 접촉 시점입니다.</>
    : s.pde[0] >= 0.5 ? <>D·E 가능성이 절반을 넘습니다. 관심 목록에 넣고 선제 제안을 검토하세요.</>
    : s.pm !== undefined && meta.list.p_star !== null && s.pm >= meta.list.p_star ? <>등급은 버티지만 강화되는 기준을 못 맞출 가능성이 큽니다. 중기 개선 제안 대상입니다.</>
    : <>당장 D·E 위험은 낮습니다. 영업 우선순위는 낮습니다.</>;
  const costParts: [string, number][] = base ? [["효율 변화", base[0][7]], ["규제 강화", base[0][8]], ["연료 가격", base[0][9]], ["배출권 가격", base[0][10]]] : [];
  const costTop = costParts.slice().sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))[0];
  const ok10 = base ? base[0][0] * 0.1 : 0;

  const summary: Record<typeof k, ReactNode> = {
    check: <>{otherSig.map((x) => SIGNAL_PLAIN[x][0]).join("·")} 신호가 확인되어, 아래 비교 결과는 보고값 검증 후 해석해야 합니다.</>,
    berth: <>{y}년 CII {s.cii ?? ""}등급의 주원인은 정박 배출입니다. 정박 배출이 같은 조건 예측값의 {times(s.br)}{s.brp ? <>로, 예년 범위({times(s.brp[0])}~{times(s.brp[1])})를 크게 벗어났습니다</> : <>입니다</>}. 정박을 제외한 해상 효율은 동급 대비 {pct(vs)}입니다.</>,
    real: <>해상 효율이 동급 대비 {pct(vs)}이며, 다년 기준으로도 같은 조건 대비 지속적으로 높습니다 (위치 z {s.z?.toFixed(1)}).{s.pp !== undefined ? <> 이듬해에도 같은 조건 대비 10% 초과할 확률은 {prob(s.pp)}입니다.</> : null}</>,
    year: <>{y}년 해상 효율은 동급 대비 {pct(vs)}이나, 다년 기준 위치 z {s.z?.toFixed(1) ?? "–"}로 지속성은 확인되지 않습니다.</>,
    good: <>해상 효율이 동급 대비 {pct(vs)}로 우수합니다.</>,
    same: <>해상 효율이 동급 대비 {pct(vs)}로 동급 수준입니다.</>,
  };

  // [질문, 값, 보조 문구, 크기, 이동할 탭]
  const tiles: [string, ReactNode, ReactNode, string | undefined, TabKey][] = [
    ["동급보다 연료를", <span className={vs > 0 ? "up" : "down"}>{pct(vs)}</span>, `1해리당 CO₂ ${num(s.sea)} kg · 동급 ${num(s.peer)} kg`, undefined, "eff"],
    ["더 쓰는 가장 큰 이유", <span className="sm">{reasons[0] ? FN[reasons[0]] : "뚜렷한 이유 없음"}</span>, reasons[0] ? `${reasons[0] === "rest" ? "선체·엔진 상태 등 · " : ""}늘어난 몫의 ${Math.round((s.c[reasons[0]] / Math.max(1e-9, posSum)) * 100)}%` : "", "sm", "eff"],
    [`${y + 1}년 D·E 등급 확률`, s.pde ? <span className={s.pde[0] >= 0.5 ? "up" : "down"}>{prob(s.pde[0])}</span> : <span className="sm">미산출</span>, s.pde ? `지금 ${s.cii ?? "–"}등급${s.lst ? ` · ${LIST_NAME[s.lst]}` : ""}` : "CII 등급 산정 대상 아님", s.pde ? undefined : "sm", "fc"],
    [`${y + 1}년 연료비+탄소 비용`, base ? eok(base[0][0]) : <span className="sm">미산출</span>, base ? `범위 ${(base[0][1] / 100).toFixed(0)}~${eok(base[0][2], 0)}` : old ? `${meta.base_year}년 미보고 선박` : "비용 표 대상 아님", base ? undefined : "sm", "cost"],
    ["자료 확인 필요", <span className="sm">{nChk ? `${nChk}건` : "없음"}</span>, chkNames.length ? chkNames.join(" · ") : "보고값 이상 신호 없음", "sm", "chk"],
  ];

  return (
    <>
      <section className="dh">
        <div className="wrap">
          <div className="dh-grid">
            <div className="dh-art">
              <ShipPhoto type={s.t} seed={s.imo % 97} className="ship" alt={`${typeKo(s.t)} 사진`} />
              <div className={`lk k-${k}`} aria-hidden="true"><i className="tl" /><i className="tr" /><i className="bl" /><i className="br" /><b>{VERDICT[k].name}</b></div>
            </div>
            <ShipMap imo={s.imo} name={s.n} />
            <div className="dh-text">
              <div className="dh-badges"><Verdict k={k} lg /><ListBadge k={s.lst} /></div>
              <h1 className="dh-name">{s.n}</h1>
              <p className="dh-meta">{typeKo(s.t)} · {s.dwt ? `${num(s.dwt)} DWT` : s.gt ? `${num(s.gt)} GT` : ""} · {s.b ?? "–"}년 건조 · IMO {s.imo}{s.on?.length ? ` · 구 선명 ${s.on[s.on.length - 1]}` : ""}{s.co ? ` · ${s.co}` : ""}</p>
              {old && <p className="notice" style={{ margin: "8px 0 0" }}>{meta.base_year}년 보고가 없어 마지막 보고 연도({y}년) 기준으로 진단했습니다. 비용 표와 다음 해 리스트 대상이 아닙니다.</p>}
              <p className="dh-say">{summary[k]}</p>
              <div className="dh-act">
                <a className="btn target sm" href={`#/cost?imo=${s.imo}`}>비용 계산</a>
                <a className="btn ghost sm" href={`#/my?imo=${s.imo}`}>입력값 수정 진단</a>
                <button className={`btn ghost sm ${watch.some((x) => x.imo === s.imo) ? "on" : ""}`} onClick={() => toggleWatch(s.imo)} aria-pressed={watch.some((x) => x.imo === s.imo)}>{watch.some((x) => x.imo === s.imo) ? "관심 해제" : "관심 추가"}</button>
                <button className={`btn ghost sm ${cmp.includes(s.imo) ? "on" : ""}`} onClick={() => setCmpMsg(toggleCompare(s.imo) ? "" : "비교 목록이 가득 찼습니다 (최대 4척).")} aria-pressed={cmp.includes(s.imo)}>{cmp.includes(s.imo) ? "비교에서 빼기" : "비교에 추가"}</button>
                <button className="btn ghost sm" onClick={() => window.print()}>보고서 인쇄</button>
              </div>
              {cmpMsg && <p className="small muted" style={{ marginTop: 8 }}>{cmpMsg} <a href="#/compare">비교 보기</a></p>}
            </div>
          </div>
          <nav className="answers" aria-label="진단 요약">
            {tiles.map(([q, a, sub, cls, to]) => (
              <button key={q} className="ans-tile" onClick={() => pick(to, true)}>
                <span className="ans-q">{q}</span><span className={`ans-a ${cls ?? ""}`}>{a}</span><span className="ans-s">{sub}</span>
              </button>
            ))}
          </nav>
        </div>
      </section>

      <div className="dtabs-wrap" id="dtabs">
        <div className="wrap">
          <div className="dtabs" role="tablist" aria-label="진단 항목">
            {TABS.map(([key, label, q]) => <button key={key} role="tab" id={`tab-${key}`} aria-selected={tab === key} aria-controls={`panel-${key}`} className={tab === key ? "on" : ""} onClick={() => pick(key)}><b>{label}</b><small>{q}</small></button>)}
          </div>
        </div>
      </div>

      <div className="wrap dpanels">
        <div role="tabpanel" id="panel-ill" aria-labelledby="tab-ill" hidden={tab !== "ill"} className="dpanel">
          <Decide a={illDecide[k][0]} use={illDecide[k][1]} />
          <IllusionCheck s={s} meta={meta} hist={hist} />
        </div>

        <div role="tabpanel" id="panel-eff" aria-labelledby="tab-eff" hidden={tab !== "eff"} className="dpanel">
          <Decide
            a={vs > 0
              ? <>같은 선종·연도·크기의 배보다 1해리에 CO₂를 <b>{pct(vs)}</b> 더 냅니다.{top ? <> 가장 큰 이유는 <b>{FN[top]}</b>입니다.</> : <> 뚜렷하게 더 쓰는 이유는 없습니다.</>}{berthSig ? <> 정박 배출은 이와 별도로 예측의 {times(s.br)}입니다.</> : null}</>
              : <>같은 선종·연도·크기의 배보다 1해리에 CO₂를 <b>{pct(vs)}</b> 덜 냅니다.{berthSig ? <> 다만 정박 배출이 예측의 {times(s.br)}입니다.</> : null}</>}
            use={vs > 0 && top ? effUse[top] : berthSig ? <>항해 성능 개선 여지는 작고, 정박 중 연료 절감 제안이 맞습니다.</> : <>항해 성능 개선 여지는 작습니다.</>}
          />
          <div className="two">
            <Card title="항해 중 연료, 동급과 비교" sub={`${typeKo(s.t)} · 크기 ${SIZE_Q[s.sq]} · ${y}년`}>
              <p className="lead sm">항해 중 1해리당 CO₂(정박 제외) <b>{num(s.sea)} kg</b>, 동급 중간값 {num(s.peer)} kg 대비 <b>{pct(vs)}</b>입니다.</p>
              <div className="vs">
                <div><div className="k">같은 조건 예측값</div><div className="v">{num(s.exp)}</div><div className="d">속력·운항 시간·선령 등 조건이 같은 배라면 이 값이 정상. 실제는 {pct(vsExp(s))}</div></div>
                <div><div className="k">여러 해 꾸준함 (위치 z)</div><div className="v">{s.z === undefined ? "–" : s.z.toFixed(1)}</div><div className="d">{s.z === undefined ? "보고 연수 부족으로 미산출" : `${s.zy}개 연도 종합. 2 이상이면 꾸준히 더 쓰는 배`}</div></div>
              </div>
              <div style={{ marginTop: 12, maxWidth: 640 }}><Reticle sea={s.sea} peer={s.peer} exp={s.exp} /></div>
              {s.z !== undefined && (
                <div className="zbar" role="img" aria-label={`위치 z ${s.z.toFixed(1)}, 2 이상이면 지속 초과`}>
                  <span className="meter"><span className="cut" style={{ left: `${(5 / 8) * 100}%` }} /><i style={{ left: `${((Math.max(-3, Math.min(5, s.z)) + 3) / 8) * 100}%` }} /></span>
                  <span className="zl"><span>덜 씀</span><span style={{ left: `${(3 / 8) * 100}%` }}>0 보통</span><span style={{ left: `${(5 / 8) * 100}%` }}>2 꾸준히 더 씀</span></span>
                </div>
              )}
              {showPersist && (
                <div className="persist">
                  <div><span className="k">이듬해 유지 확률</span><b>{prob(s.pp)}</b><span className="muted small">전체 평균 {prob(meta.persist.base_rate)}</span></div>
                  <p>이듬해에도 같은 조건 예측값보다 10% 넘게 높을 확률입니다.{s.pup && <> 확률을 높이는 요인은 <b>{s.pup}</b>{s.pdn ? <>, 낮추는 요인은 <b>{s.pdn}</b></> : null}입니다.</>}</p>
                </div>
              )}
            </Card>
            <Card title="무엇이 차이를 만드나" sub="동급 대비 차이를 요인별로 나눔">
              <p className="lead sm">
                {reasons.length
                  ? <>빨간 막대가 연료를 더 쓰게 한 요인입니다. 가장 큰 것은 <b>{FN[reasons[0]]}</b>{reasons[1] ? <>, 다음은 {FN[reasons[1]]}</> : null}입니다.{helps[0] ? <> {FN[helps[0]]}은(는) 오히려 줄였습니다.</> : null}</>
                  : <>뚜렷하게 더 쓰게 한 요인이 없습니다.</>}
              </p>
              <div className="chart-box"><CauseBars c={s.c} names={FN} speedWait={speedWait} /></div>
              <Help>
                <p>공통잔차 모델(선종 간 기울기 공유)로 산출한 요인별 기여입니다. 모든 막대의 합은 ln(실제 ÷ 동급 중간값)과 일치합니다. '설명 안 되는 차이'(미설명 잔차)에는 선체 오손, 프로펠러·엔진 상태, 기상 등 공개 자료에 없는 요인이 함께 들어 있어 원인을 하나로 특정하지 않습니다.</p>
                {speedWait && <p>이 선종은 평균 속력이 낮을수록 배출이 높게 추정됩니다(속력 탄력성 {meta.types[s.t]?.speed_elasticity}). 평균 속력에 대기·저속 운항이 포함되기 때문이며, 감속 효과 추정에는 사용하지 않습니다.</p>}
                {meta.types[s.t] && <p>{typeKo(s.t)} 모델: 학습 {num(meta.types[s.t].n)}건({num(meta.types[s.t].ships)}척), 설명력 R² {meta.types[s.t].r2.toFixed(2)}.</p>}
              </Help>
            </Card>
          </div>
          <div className="two" style={{ marginTop: 16 }}>
            <Card title="해마다 동급 대비" sub={trend.length >= 2 ? `${trend.length - 1}번 중 ${ups}번 나빠짐` : undefined}>
              {hist === null ? <p className="muted">불러오는 중…</p> : <TrendChart rows={trend} />}
            </Card>
            <Card title="정박 배출" sub={`같은 조건 예측의 ${times(s.br)}`}>
              <p className="small" style={{ marginBottom: 8, color: "var(--ink-2)" }}>
                {berthSig
                  ? <>{y}년 정박 배출 {num(s.bt)}톤은 같은 조건 예측값 {num(s.be)}톤의 <b>{times(s.br)}</b>{s.brp ? <>로 예년 범위({times(s.brp[0])}~{times(s.brp[1])})를 크게 벗어났습니다</> : null}. 연간 CO₂의 {Math.round((s.bs ?? 0) * 100)}%가 정박 중 발생했습니다.</>
                  : <>{y}년 정박 배출 {num(s.bt)}톤, 같은 조건 예측값의 {times(s.br)}로 정상 범위입니다.</>}
              </p>
              {hist === null ? <p className="muted">불러오는 중…</p> : <BerthChart rows={berthRows} />}
            </Card>
          </div>
        </div>

        <div role="tabpanel" id="panel-fc" aria-labelledby="tab-fc" hidden={tab !== "fc"} className="dpanel">
          <Decide
            a={s.pde
              ? <>지금처럼 운항하면 {y + 1}년 D·E 등급 확률 <b>{prob(s.pde[0])}</b>, {y + 3}년 {prob(s.pde[2])}입니다.{f1 ? <> 1해리당 CO₂는 {y + 1}년 {num(f1[0])} kg({pct((f1[0] / s.sea - 1) * 100)})로 예상됩니다.</> : null}</>
              : f1 && f3 ? <>지금처럼 운항하면 1해리당 CO₂는 {y + 1}년 {num(f1[0])} kg, {y + 3}년 {num(f3[0])} kg으로 예상됩니다.</>
              : <>보고 연수나 크기 조건이 부족해 예측하지 않았습니다.</>}
            use={fcUse}
          />
          {s.fc && hist && (
            <div className="two" style={{ gridTemplateColumns: "1.3fr 1fr" }}>
              <Card title="1해리당 CO₂ 전망" sub="점선 = 예상값, 붉은 띠 = 80% 범위"><FanChart hist={hist.map((r) => ({ y: r[0], v: r[1] }))} fc={s.fc} peer={s.peer} base={y} /></Card>
              <Card title="연도별 예측">
                <div className="tbl">
                  <table className="t">
                    <thead><tr><th>연도</th><th>항해 중</th><th>80% 범위</th><th>정박 포함</th><th>D·E 확률</th></tr></thead>
                    <tbody>{s.fc.map((f, i) => <tr key={i}><td>{y + 1 + i}</td><td><b>{num(f[0])}</b></td><td>{num(f[1])}~{num(f[2])}</td><td>{s.fct ? num(s.fct[i][0]) : "–"}</td><td>{s.pde ? prob(s.pde[i]) : "–"}</td></tr>)}</tbody>
                  </table>
                </div>
                <p className="card-foot">단위 kg CO₂/해리. 등급과 비용은 정박 포함 값으로 계산합니다. 분위 회귀(p10·p50·p90).</p>
              </Card>
            </div>
          )}
          {s.pde && (
            <Card title="D·E 등급 확률" style={{ marginTop: 16 }}>
              <div className="cii-row">
                <div className="cii-now">
                  <span className="k">{y}년 등급</span><Grade_ g={s.cii} />
                  <span className="k" style={{ marginTop: 10 }}>2026년 기준선 적용</span><Grade_ g={s.cii26} sm />
                  {s.ciir !== undefined && <span className="muted small">기준선 대비 {s.ciir.toFixed(2)}배</span>}
                </div>
                <div className="de-bars" role="img" aria-label={`CII D·E 확률 ${s.pde.map((p, i) => `${y + 1 + i}년 ${prob(p)}`).join(", ")}`}>
                  {s.pde.map((p, i) => (
                    <div key={i} className="de"><span className="de-y">{y + 1 + i}년</span><span className="de-t"><i style={{ width: `${p * 100}%` }} className={p >= meta.list.de_cut ? "hi" : ""} /><span className="de-cut" style={{ left: `${meta.list.de_cut * 100}%` }} /></span><b>{prob(p)}</b></div>
                  ))}
                  <p className="muted small">세로선을 넘으면 영업 타깃({prob(meta.list.de_cut)} 이상).{s.pm !== undefined && <> {y + 1}년 강화 기준을 못 맞출 확률 {prob(s.pm)}.</>}</p>
                </div>
              </div>
              {s.lst && (
                <p className="list-note"><ListBadge k={s.lst} />
                  {s.lst === "target"
                    ? <> {meta.list.year}년 CII D·E 확률이 {prob(meta.list.de_cut)} 이상으로 {meta.list.year}년 리스트의 영업 타깃입니다 (순위 {num(s.lr)}).</>
                    : <> 현재 {s.cii}등급이나 {meta.list.year}년 감축 요구 미달 확률이 기준 {prob(meta.list.p_star)} 이상으로 관찰 대상입니다 (순위 {num(s.lr)}).</>}
                  {" "}<a href={`#/table?tab=${s.lst}`}>리스트 보기</a>
                </p>
              )}
            </Card>
          )}
        </div>

        <div role="tabpanel" id="panel-cost" aria-labelledby="tab-cost" hidden={tab !== "cost"} className="dpanel">
          {base && cost ? (
            <Decide
              a={<>{y + 1}년 연료비+탄소 비용은 약 <b>{eok(base[0][0])}</b>(범위 {eok(base[0][1], 0)}~{eok(base[0][2], 0)})입니다. {y}년보다 {eok(Math.abs(base[0][6]))} {base[0][6] >= 0 ? "늘고" : "줄고"}, 가장 큰 이유는 {costTop[0]}({costTop[1] >= 0 ? "+" : ""}{eok(costTop[1])})입니다.</>}
              use={<>연료를 10% 줄이면 연 약 <b>{eok(ok10)}</b>를 아낍니다(단순 비례). 개조비를 넣어 회수 기간을 계산하려면 <a href={`#/cost?imo=${s.imo}`}>비용 계산</a>으로 가세요.</>}
            />
          ) : (
            <p className="lead">
              {cost === undefined ? <>불러오는 중…</>
                : <>{old ? `${meta.base_year}년 보고가 없어 비용 표가 산출되지 않았습니다` : cost?.k ? `비용 표 미산출: ${cost.k}` : "연료 그룹 또는 예측값이 없어 비용 표가 산출되지 않았습니다"}. 비용 계산 화면에서 가격을 입력해 산정할 수 있습니다.</>}
            </p>
          )}
          {base && cost && (
            <div className="costband inline">
              <div className="cb-grid">
                <div className="cb-card">
                  <span className="muted small">{y + 1}년 연료비+탄소 비용 · 기준 가격</span>
                  <div className="cb-big">{eok(base[0][0])}</div>
                  <dl className="cb-rows">
                    <dt>연료비 ({cost.fg ?? "연료 그룹 미상"})</dt><dd>{eok(base[0][3])}</dd>
                    <dt>탄소 비용 (EU ETS, 부과율 {Math.round((meta.cost.ets_share[String(y + 1)] ?? 1) * 100)}%)</dt><dd>{eok(base[0][4])}</dd>
                    <dt>{y}년 실적 (연료비 + 탄소 비용)</dt><dd>{eok(cost.b[2])}</dd>
                    <dt>{y}년 1해리당 연료, 동급 대비</dt><dd className={(cost.pg ?? 0) > 0 ? "up" : "down"}>{pct(cost.pg, 1)}</dd>
                  </dl>
                  {cost.k && <p className="muted small" style={{ marginTop: 8 }}>{cost.k}</p>}
                </div>
                <div className="cb-card">
                  <h3>{y}→{y + 1}년 비용이 바뀌는 이유</h3>
                  <Decomp parts={[["효율 변화", base[0][7]], ["규제 강화 (ETS 부과율 등)", base[0][8]], ["연료 가격", base[0][9]], ["배출권 가격", base[0][10]]]} total={base[0][6]} />
                  <table className="cb-tbl">
                    <thead><tr><th>연도</th><th>가격 낮음</th><th>기준</th><th>가격 높음</th></tr></thead>
                    <tbody>{[0, 1, 2].map((i) => <tr key={i}><td>{y + 1 + i}</td><td>{eok(cost.s!["낮음"][i][0], 0)}</td><td><b>{eok(cost.s!["기준"][i][0], 0)}</b></td><td>{eok(cost.s!["높음"][i][0], 0)}</td></tr>)}</tbody>
                  </table>
                  <div className="dh-act" style={{ marginTop: 14 }}>
                    <a className="btn light sm" href={`#/cost?imo=${s.imo}`}>개선 시나리오 계산</a>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <div role="tabpanel" id="panel-chk" aria-labelledby="tab-chk" hidden={tab !== "chk"} className="dpanel">
          <Decide
            a={<>{nChk ? <>자료에서 확인할 항목이 <b>{nChk}건</b>({chkNames.join(", ")}) 있습니다.</> : <>보고값에 이상 신호가 <b>없습니다</b>.</>}{sis.length ? <> 같은 설계의 동형선 {num(sis.length)}척 중 {num(sisBetter)}척이 이 배보다 연료를 덜 씁니다.</> : null}</>}
            use={<>{nChk ? "확인 항목은 수치를 인용하기 전에 선주에게 물어보세요. " : ""}{sisBetter ? "같은 설계로 더 잘하는 동형선은 '같은 배로도 줄일 수 있다'는 제안 근거가 됩니다." : "동형선 중 이 배가 가장 좋은 편이라 개선 근거로 쓰기 어렵습니다."}</>}
          />
          <div className="two">
            <Card title={`동형선 ${num(sis.length)}척`} sub="같은 선종, 건조연도 ±1년, 재화중량 ±3%, 길이 ±2%">
              {sis.length ? (
                <>
                  <div className="sis-bars" role="img" aria-label={`동형선 CII 등급 분포 ${GRADES.map((g) => `${g} ${sisGrades[g]}척`).join(", ")}`}>
                    {GRADES.map((g) => (
                      <div key={g} className={g === s.cii ? "me" : ""}><span>{sisGrades[g]}</span><i className={`g${g}`} style={{ height: `${(sisGrades[g] / Math.max(1, ...Object.values(sisGrades))) * 70}px` }} /><b>{g}</b></div>
                    ))}
                  </div>
                  <p className="card-foot">동형선 {y}년 CII 등급 분포. 해상 효율이 이 선박보다 우수한 동형선 {num(sisBetter)}척.</p>
                  <ul className="peers">
                    {sis.slice().sort((a, b) => vsPeer(a) - vsPeer(b)).slice(0, 3).map((x) => (
                      <li key={x.imo}><a href={`#/ship/${x.imo}`}>{x.n}</a><span>동급 대비 {pct(vsPeer(x))}</span><span>CII {x.cii ?? "–"}</span></li>
                    ))}
                  </ul>
                </>
              ) : <p className="muted">조건에 맞는 동형선이 없습니다.</p>}
            </Card>

            <Card title="운항·설계가 비슷한 배" sub="공용 서버 군집">
              {cl === undefined ? <p className="muted small">공용 서버에서 불러오는 중… (유휴 상태면 30초 이상)</p> : !cl ? <p className="muted small">공용 서버에 이 선박의 군집 결과가 없거나 연결되지 않았습니다.</p> : (
                <div className="cl">
                  <div className="cl-ax">
                    <div><span className="k">{cl.exposure.axis_name}</span><b>{cl.exposure.type_name}</b><span className="muted small">소속 확률 {prob(cl.ship.exposure_prob_max)}{cl.ship.exposure_prob_max < 0.6 ? " · 경계" : ""} · 전체의 {cl.exposure.share_pct}%</span><p className="small">{cl.exposure.description}</p></div>
                    {cl.profile && <div><span className="k">{cl.profile.axis_name}</span><b>{cl.profile.type_name}</b><span className="muted small">소속 확률 {prob(cl.ship.profile_prob_max)}{(cl.ship.profile_prob_max ?? 1) < 0.6 ? " · 경계" : ""}{cl.ship.design_level ? ` · 설계 효율 ${cl.ship.design_level}` : ""}</span><p className="small">{cl.profile.description}</p></div>}
                  </div>
                  {cl.similar.length > 0 && (
                    <>
                      <h4 className="cl-h">비슷한 배</h4>
                      <ul className="peers">
                        {cl.similar.map((x) => {
                          const o = ships.find((z) => z.imo === x.similar_imo);
                          return <li key={x.similar_imo}>{o ? <a href={`#/ship/${x.similar_imo}`}>{x.name}</a> : <span>{x.name}</span>}<span>{o ? `동급 대비 ${pct(vsPeer(o))}` : "–"}</span><span>{x.profile_name ?? ""}{x.age !== undefined ? ` · 선령 ${x.age}년` : ""}</span><span>CII {o?.cii ?? "–"}</span></li>;
                        })}
                      </ul>
                    </>
                  )}
                  <p className="card-foot">공용 서버의 기존 군집({cl.ship.cluster_run ?? ""}) 기준으로, 팀 모델 유형과 기준 기간이 다를 수 있습니다.</p>
                </div>
              )}
            </Card>
          </div>
          <div className="two" style={{ marginTop: 16 }}>
            <Card title="자료 점검">
              <ul className="checks">
                <li><CheckIcon ok={!berthSig} /><span>정박 배출<small>{SIGNAL_PLAIN.berth[1]}이면 해당</small></span><span className="val">예측값의 {times(s.br)}</span></li>
                <li><CheckIcon ok={!s.sig?.includes("short")} /><span>EU 해상 시간<small>{meta.thresholds.short_sea_hours}시간 미만이면 연간 값 변동이 큼</small></span><span className="val">{num(s.hrs)}시간</span></li>
                <li><CheckIcon ok={!s.sig?.includes("fuel")} /><span>연료 종류<small>연료 1톤당 CO₂ {meta.thresholds.co2_per_fuel_min} 미만이면 화석연료 범위 밖</small></span><span className="val">{s.cpf?.toFixed(2) ?? "–"}{s.fg ? ` · ${s.fg}` : ""}</span></li>
                <li><CheckIcon ok={!s.sig?.includes("report")} /><span>보고값 물리 범위<small>평균 속력 {meta.thresholds.min_speed_kn}노트 이상, 적재량 ≤ 재화중량 × {meta.thresholds.cargo_dwt_ratio_max}</small></span><span className="val">평균 {s.spd.toFixed(1)}노트</span></li>
                <li><CheckIcon ok={!s.sig?.includes("special")} /><span>특수 운항<small>셔틀 탱커 운영사 등 운항 형태가 다른 집단</small></span><span className="val">{s.co ? "" : "회사 정보 없음"}</span></li>
                <li><CheckIcon ok={!s.oo} /><span>운항 패턴<small>선종별 운항 지표 군집에서 가장 먼 상위 2.5%이면 이상 운항</small></span><span className="val">{s.oo ? "이상 운항" : "정상"}</span></li>
                <li><CheckIcon ok={!ext.length} /><span>모델 적용 범위<small>값이 학습 자료의 1~99% 범위 밖이면 예측 신뢰도 낮음</small></span><span className="val">{ext.length ? `외삽 ${ext.length}건` : "범위 내"}</span></li>
              </ul>
              {(ext.length > 0 || otherW.length > 0) && <ul className="warn-list">{[...ext, ...otherW].map((w) => <li key={w}>{warnText(w)}</li>)}</ul>}
            </Card>
            <Card title="제원·유형">
              <dl className="specs">
                <Spec k="선종 · 크기" v={`${typeKo(s.t)} · 선종 내 ${SIZE_Q[s.sq]}`} />
                <Spec k="건조연도 · 선령" v={`${s.b ?? "–"}년 · ${s.age}년`} />
                <Spec k="재화중량 · 총톤수" v={`${s.dwt ? num(s.dwt) : "–"} DWT · ${s.gt ? num(s.gt) : "–"} GT`} />
                <Spec k="전장" v={s.loa ? `${num(s.loa, 1)} m` : "–"} />
                <Spec k="내빙 등급 · 설계 효율 지표" v={`${s.ice ?? "없음"} · ${s.ek ? `${s.ek}${s.ev ? ` ${s.ev}` : ""}` : "없음"}`} />
                <Spec k="연간 운항" v={`${num(s.hrs)} h · ${num(s.dist)} 해리 · 평균 ${s.spd.toFixed(1)}노트`} />
                <Spec k="연간 CO₂ (정박)" v={`${tonnes(s.co2)} (${tonnes(s.bt)})`} />
                <Spec k="EU 역내 비중 · ETS 대상" v={`${s.intra !== undefined ? `${Math.round(s.intra * 100)}%` : "–"} · ${s.ets !== undefined ? `${Math.round(s.ets * 100)}%` : "–"}`} />
                <Spec k="연료 그룹" v={s.fg ?? "–"} />
                <Spec k="EU 규제 노출도 유형" v={s.tx ? `${exposureName(meta, s.tx)}${s.txp !== undefined && s.txp < 0.6 ? ` (경계, 소속 확률 ${prob(s.txp)})` : ""}` : "–"} />
                <Spec k="선령·설계 유형" v={s.ta ? `${profileName(meta, s.ta)}${s.tap !== undefined && s.tap < 0.6 ? ` (경계, 소속 확률 ${prob(s.tap)})` : ""}` : "설계 효율 값 없음"} />
                <Spec k="관리회사 (최근)" v={s.co ?? "–"} />
              </dl>
            </Card>
          </div>
        </div>

        <div role="tabpanel" id="panel-srv" aria-labelledby="tab-srv" hidden={tab !== "srv"} className="dpanel">
          <Decide
            a={<>팀 공용 서버가 같은 EU MRV 원자료로 <b>따로 계산한 값</b>입니다. 위 진단 결과를 바꾸지 않습니다.</>}
            use={<>등급이 '일치'면 보고서에 그대로 인용해도 됩니다. '다름'이면 인용 전에 기준선 연도와 선종 분류를 확인하세요.</>}
          />
          {seen.has("srv") && <ServerValues s={s} cl={cl} />}
        </div>
      </div>
    </>
  );
}

// "학습 범위 밖(외삽): berth_share=0.54 (선종 1~99%: 0~0.35)" → 읽기 쉬운 한국어
const W_NAME: Record<string, [string, (v: number) => string]> = {
  age: ["선령", (v) => `${v.toFixed(0)}년`], avg_speed_kn: ["평균 속력", (v) => `${v.toFixed(1)}노트`],
  berth_share: ["정박 배출 비중", (v) => `${Math.round(v * 100)}%`], eu_share: ["EU 역내 비중", (v) => `${Math.round(v * 100)}%`],
  ln_dwt: ["재화중량", (v) => `${num(Math.exp(v))} DWT`], ln_sea_hours: ["해상 시간", (v) => `${num(Math.exp(v))}시간`],
};
export function warnText(w: string) {
  const m = w.match(/외삽\): ([a-z_]+)=([-\d.e]+) \(선종 1~99%: ([-\d.e]+)~([-\d.e]+)\)/);
  const d = m && W_NAME[m[1]];
  if (!m || !d) return w;
  const [name, f] = d;
  return `${name} ${f(+m[2])}: 이 선종 학습 자료 범위(${f(+m[3])}~${f(+m[4])}) 밖이라 예측 신뢰도가 낮습니다.`;
}

const Spec = ({ k, v }: { k: string; v: string }) => <div><dt>{k}</dt><dd>{v}</dd></div>;

/** 비용 변화 분해 막대 (백만 원). 몫의 합 = 총변화 */
export function Decomp({ parts, total }: { parts: [string, number][]; total: number }) {
  const m = Math.max(...parts.map(([, v]) => Math.abs(v)), Math.abs(total)) || 1;
  const bar = (v: number, c: string) => (
    <div className="dc-track"><span className="z" />
      <span className="f" style={{ background: c, borderRadius: v >= 0 ? "0 4px 4px 0" : "4px 0 0 4px", left: v >= 0 ? "50%" : `${50 - (Math.abs(v) / m) * 50}%`, width: `${(Math.abs(v) / m) * 50}%` }} />
    </div>
  );
  return (
    <div>
      {parts.map(([l, v]) => <div key={l} className="dc-row"><span>{l}</span>{bar(v, v >= 0 ? "var(--signal)" : "var(--base)")}<span className="dc-v">{v >= 0 ? "+" : ""}{eok(v)}</span></div>)}
      <div className="dc-row"><span>합계</span>{bar(total, "var(--ink)")}<span className="dc-v">{total >= 0 ? "+" : ""}{eok(total)}</span></div>
    </div>
  );
}
