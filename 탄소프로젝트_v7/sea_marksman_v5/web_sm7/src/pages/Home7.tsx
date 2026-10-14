// 홈: 같은 E등급이라도 이유는 배마다 다르다.
//   배가 도는 첫 화면 → 서비스 한 문단 → 흐르는 띠 → TIGANI 사례 → 등급을 흐리는 네 가지 → 걸러 내기 → 13개 선종 → 2026 리스트 → 도구 → 검증
import { useEffect, useMemo, useRef, useState } from "react";
import type { HistRow, Meta, Ship } from "../data";
import { loadHist, typeKo, TYPE_KO } from "../data";
import { num } from "../format";
import { prob } from "../components/ui";
import { BigTitle, Marquee, RoundBtn } from "../components/Kinetic";
import { gsap, reduced, useGsap } from "../motion";

const TYPE_ORDER = ["bulk", "container", "tanker", "chemical_tanker", "general_cargo", "vehicle_carrier", "ro_pax", "lng_carrier", "gas_carrier", "ro_ro", "cruise", "reefer", "container_ro_ro"];

export function useTypeStats(ships: Ship[]) {
  return useMemo(() => {
    const m = new Map<string, { n: number; de: number; target: number }>();
    for (const s of ships) {
      const x = m.get(s.t) ?? { n: 0, de: 0, target: 0 };
      x.n++; if (s.cii === "D" || s.cii === "E") x.de++; if (s.lst === "target") x.target++;
      m.set(s.t, x);
    }
    return TYPE_ORDER.filter((t) => m.has(t)).map((t) => ({ t, ...m.get(t)! }));
  }, [ships]);
}

function Hero({ meta }: { meta: Meta }) {
  const ref = useRef<HTMLElement>(null);
  useGsap(ref, () => {
    if (reduced()) return;
    const stage = ref.current!.querySelector<HTMLElement>(".h7-stage")!;
    const lines = gsap.utils.toArray<HTMLElement>(".h7-li");
    const sb = stage.getBoundingClientRect();
    const cx = sb.left + sb.width / 2;
    // 처음엔 제목이 가운데 모였다가 제자리로 흩어지고, 배는 가로에서 비스듬히 돈다
    const intro = gsap.timeline({ defaults: { ease: "power3.inOut" } });
    intro.fromTo(".h7-ship", { rotate: -53, scale: 0.62, autoAlpha: 0 }, { rotate: 0, scale: 1, autoAlpha: 1, duration: 1.9 }, 0);
    lines.forEach((el, i) => {
      const r = el.getBoundingClientRect();
      intro.fromTo(el, { x: cx - (r.left + r.width / 2), yPercent: 60, autoAlpha: 0 }, { yPercent: 0, autoAlpha: 1, duration: 0.7, ease: "power3.out" }, 0.1 + i * 0.08);
      intro.to(el, { x: 0, duration: 1.2 }, 0.95);
    });
    intro.fromTo([".h7-meta", ".h7-cue"], { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.6 }, 1.7);
    // 스크롤: 배는 위로 빠져나가고 제목은 양옆으로 흩어지며, 서비스 문단이 남는다
    const st = gsap.timeline({ scrollTrigger: { trigger: ref.current, start: "top top", end: "+=105%", scrub: 0.6, pin: stage } });
    st.to(".h7-shipwrap", { yPercent: -150, rotate: 6, ease: "none", duration: 1 }, 0)
      .to(".h7-l", { x: (i) => (i % 2 ? -1 : 1) * window.innerWidth * 0.5, autoAlpha: 0, ease: "power1.in", duration: 0.55 }, 0)
      .to([".h7-meta", ".h7-cue"], { autoAlpha: 0, duration: 0.15 }, 0)
      .fromTo(".h7-intro", { autoAlpha: 0, y: 60 }, { autoAlpha: 1, y: 0, duration: 0.35 }, 0.45);
  });
  return (
    <section ref={ref} className="h7-hero">
      <div className="h7-stage">
        <div className="h7-shipwrap"><img className="h7-ship" src={`${import.meta.env.BASE_URL}hero-ship.webp`} alt="" /></div>
        <h1 className="h7-title" aria-label="같은 E등급, 이유는 배마다 다릅니다">
          {[["같은 E등급,", "a"], ["이유는", "b"], ["배마다", "c"], ["다릅니다", "d"]].map(([t, k]) => (
            <span key={k} className={`h7-l ${k}`} aria-hidden="true"><span className="h7-li">{t}</span></span>
          ))}
        </h1>
        <div className="h7-intro">
          <p>CII는 배가 1년 동안 낸 CO₂를 크기와 항해 거리로 나눠 A~E 한 글자로 매깁니다. 그런데 항구에서 기다린 시간, 느리게 달린 항로, 운이 나빴던 한 해, 잘못 적힌 보고값도 모두 이 한 글자에 들어갑니다.</p>
          <p>Sea Marksman은 이것들을 하나씩 떼어 내고, <b>배 자체가 정말 연료를 더 쓰는지</b> 보여 드립니다.</p>
        </div>
        <p className="h7-meta">EU MRV 공개 보고 2018–{meta.base_year} · 선박 {num(meta.n_all)}척</p>
        <span className="h7-cue">스크롤</span>
      </div>
    </section>
  );
}

function Tigani({ s, meta }: { s: Ship; meta: Meta }) {
  const [h, setH] = useState<HistRow[] | null>(null);
  useEffect(() => { loadHist().then((x) => setH(x[String(s.imo)] ?? null)).catch(() => undefined); }, [s.imo]);
  const rows = (h ?? []).filter((r) => r[10]);
  const exBerth = s.ciir && s.bs ? s.ciir * (1 - s.bs) : undefined;
  const good = rows.slice(0, -1).filter((r) => r[10] === "A" || r[10] === "B").length;
  return (
    <section className="s7 dark tg7">
      <div className="w7">
        <p className="lbl7">사례 · 유조선 {s.n} · IMO {s.imo} · {s.b}년 건조</p>
        <div className="tg7-grades" aria-label={rows.map((r) => `${r[0]}년 ${r[10]}`).join(", ")}>
          {rows.map((r, i) => (
            <div key={r[0]} className={`tg7-g ${i === rows.length - 1 ? "last" : ""}`}><b>{r[10]}</b><span>{r[0]}</span></div>
          ))}
        </div>
        <h2 className="tg7-h">{good}년 동안 A·B였던 배가 {meta.base_year}년에 E를 받았습니다.</h2>
        <div className="facts7">
          <div><b>{Math.round((s.bs ?? 0) * 100)}%</b><p>{meta.base_year}년 CO₂ 중 항구에 서 있는 동안 나온 양. 비슷한 조건의 배라면 예상되는 양의 {Math.round(s.br)}배입니다.</p></div>
          <div><b>{s.ciir?.toFixed(2)} → {exBerth?.toFixed(2)}</b><p>항구 배출을 빼고 다시 계산한 CII 비율. 1.00 이하면 2026년 기준선 안쪽입니다.</p></div>
          <div><b>{s.z !== undefined ? (s.z < 0 ? "−" : "+") + Math.abs(s.z).toFixed(1) : "–"}</b><p>{s.zy}년 기록으로 본 바다 위 효율의 위치. 0 근처면 같은 조건의 배와 비슷하고, 2 이상이면 꾸준히 더 씁니다.</p></div>
        </div>
        <p className="tg7-c">이 E등급은 “배를 바꿔야 한다”는 신호가 아니라 “항구에서 무슨 일이 있었는지 확인하라”는 신호였습니다.</p>
        <RoundBtn href={`#/ship/${s.imo}`} tone="light">진단 보기</RoundBtn>
      </div>
    </section>
  );
}

export const FOUR = [
  { k: "berth", t: "항구에서 기다린 시간", stat: (m: Meta) => "5척 중 1척", sub: (m: Meta) => `CII 최하위 ${num(m.illusions.berth.n_worst)}척 중 ${m.illusions.berth.worst}%는 항구 배출이 비정상적으로 많았습니다. 중간 등급 배는 ${m.illusions.berth.mid}%.`,
    why: "항구에서 태운 연료는 CO₂에는 더해지지만 항해 거리는 늘리지 않습니다. 대기만 길어져도 등급이 떨어집니다.", fix: "바다 위 효율과 항구 배출을 따로 계산합니다." },
  { k: "cond", t: "조건이 다른 배와의 비교", stat: (m: Meta) => `${Math.round(m.illusions.speed.slow_de)}% vs ${Math.round(m.illusions.speed.other_de)}%`, sub: (m: Meta) => `같은 선종에서 가장 느린 4분의 1은 D·E 비율이 ${m.illusions.speed.slow_de}%, 나머지는 ${m.illusions.speed.other_de}%입니다.`,
    why: "크기·속력·선령이 다른 배가 같은 잣대로 평가됩니다. 느린 속력에는 입항 대기 같은 운항 사정이 섞여 있습니다.", fix: "크기·속력·선령·항로가 비슷한 배라면 얼마를 썼을지 계산하고, 그 값과 비교합니다." },
  { k: "year", t: "그해만 나빴던 기록", stat: () => "절반", sub: (m: Meta) => `효율이 전년보다 20% 넘게 나빠진 ${num(m.illusions.year.n_jump)}건 중 ${m.illusions.year.reverted}%가 이듬해 절반 이상 회복했습니다.`,
    why: "한 해 값은 항로·날씨·화물에 따라 크게 흔들립니다. 한 번 나빴다고 나쁜 배는 아닙니다.", fix: "최대 7년 기록을 함께 보고, 꾸준히 더 쓰는 배만 ‘지속 초과’로 표시합니다." },
  { k: "report", t: "잘못 적힌 보고값", stat: (m: Meta) => `${m.illusions.report.best}%`, sub: (m: Meta) => `CII가 가장 좋은 2.5%의 ${m.illusions.report.best}%에 의심 신호가 있습니다. 중간 등급 배는 ${m.illusions.report.mid}%.`,
    why: "단위 실수, 화석연료로는 나올 수 없는 연료 계수, 아주 짧은 EU 구간, 셔틀 탱커 같은 특수 운항이 숫자에 섞입니다. 좋은 등급에도 섞입니다.", fix: "의심스러운 값에 표시를 붙입니다. 값을 지우거나 고치지는 않습니다." },
];

function Four({ meta }: { meta: Meta }) {
  const [on, setOn] = useState(0);
  const x = FOUR[on];
  return (
    <section className="s7 slate four7">
      <div className="w7">
        <BigTitle as="h2" lines={[["등급을", 0], ["흐리는", 22], ["네 가지", 6]]} />
        <div className="four7-grid">
          <ol className="four7-list">
            {FOUR.map((f, i) => (
              <li key={f.k}>
                <button className={i === on ? "on" : ""} onMouseEnter={() => setOn(i)} onFocus={() => setOn(i)} onClick={() => setOn(i)} aria-expanded={i === on}>
                  <span className="n">{String(i + 1).padStart(2, "0")}</span><span className="t">{f.t}</span>
                </button>
              </li>
            ))}
          </ol>
          <div className="four7-panel" key={x.k} aria-live="polite">
            <b className="four7-stat">{x.stat(meta)}</b>
            <p className="four7-sub">{x.sub(meta)}</p>
            <p className="four7-why">{x.why}</p>
            <p className="four7-fix"><span>Sea Marksman은</span>{x.fix}</p>
          </div>
        </div>
      </div>
    </section>
  );
}

function Sieve({ meta }: { meta: Meta }) {
  const f = meta.funnel;
  return (
    <section className="s7 slate sieve7">
      <div className="w7">
        <h2 className="h2-7">{num(f.all)}척 중 정말 손볼 배는 {num(f.high)}척</h2>
        {([
          ["", f.all, `${meta.base_year}년 EU에 배출량을 보고한 배`, 100],
          ["?step=clean", f.clean, `의심 신호가 있는 ${num(f.all - f.clean)}척을 뺀 배`, (f.clean / f.all) * 100],
          ["?step=high", f.high, "여러 해 꾸준히 같은 조건의 배보다 연료를 더 쓴 배", 3],
        ] as const).map(([q, n, l, w]) => (
          <a key={l} className="sv7" href={`#/search${q}`}>
            <b>{num(n)}</b><span className="sv7-bar"><i style={{ width: `${w}%` }} /></span><span className="sv7-l">{l}</span>
          </a>
        ))}
      </div>
    </section>
  );
}

function Fly({ ships }: { ships: Ship[] }) {
  const ref = useRef<HTMLElement>(null);
  const stats = useTypeStats(ships);
  const [flat, setFlat] = useState(() => reduced() || window.innerWidth < 760);
  useEffect(() => { const f = () => setFlat(reduced() || window.innerWidth < 760); window.addEventListener("resize", f); return () => window.removeEventListener("resize", f); }, []);
  useGsap(ref, () => {
    if (flat) return;
    const cards = gsap.utils.toArray<HTMLElement>(".fly-c");
    const N = cards.length, DEPTH = 3600;
    const pos = cards.map((_, i) => {
      const a = i * 2.4 + 0.6, R = 0.2 + ((i * 37) % 17) / 17 * 0.2;
      return { x: Math.cos(a) * R * window.innerWidth, y: Math.sin(a) * R * window.innerHeight * 0.9, z0: -DEPTH + (i / N) * (DEPTH - 300) };
    });
    const draw = (p: number) => cards.forEach((c, i) => {
      const z = pos[i].z0 + p * DEPTH * 1.05;
      const op = Math.max(0, Math.min(1, (z + DEPTH) / 700, (700 - z) / 500));
      c.style.transform = `translate3d(calc(-50% + ${pos[i].x}px), calc(-50% + ${pos[i].y}px), ${z}px)`;
      c.style.opacity = String(op);
      c.style.pointerEvents = op > 0.6 ? "auto" : "none";
    });
    draw(0);
    gsap.timeline({ scrollTrigger: { trigger: ref.current, start: "top top", end: "+=170%", scrub: 0.5, pin: ".fly-stage", onUpdate: (st) => draw(st.progress) } });
  }, [flat]);
  return (
    <section ref={ref} className={`s7 dark fly ${flat ? "flat" : ""}`}>
      <div className="fly-stage">
        <h2 className="fly-t">13개 선종</h2>
        <p className="fly-s">선종마다 기준이 다릅니다. 같은 선종, 같은 크기끼리 비교합니다.</p>
        <div className="fly-cards">
          {stats.map((x) => (
            <a key={x.t} className="fly-c" href={`#/types/${x.t}`}>
              <img src={`${import.meta.env.BASE_URL}types/${x.t}-sm.webp`} alt="" loading="lazy" />
              <span><b>{TYPE_KO[x.t]}</b> {num(x.n)}척 · D·E {Math.round((x.de / x.n) * 100)}%</span>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}

function ListTeaser({ ships, meta }: { ships: Ship[]; meta: Meta }) {
  const L = meta.list;
  const top = useMemo(() => ships.filter((s) => s.lst === "target").sort((a, b) => (a.lr ?? 1e9) - (b.lr ?? 1e9)).slice(0, 6), [ships]);
  return (
    <section className="s7 paper">
      <div className="w7">
        <BigTitle as="h2" lines={[[`${L.year}년에`, 0], ["D·E가", 30], ["유력한 배", 10]]} />
        <div className="two7">
          <div><b>{num(L.target)}<small>척</small></b><p><em>영업 타깃</em> {L.year}년 CII가 D 또는 E일 확률이 {prob(L.de_cut)} 이상인 배</p></div>
          <div><b>{num(L.watch)}<small>척</small></b><p><em>관찰</em> 지금은 A~C지만 {L.year}년 강화된 기준을 못 맞출 가능성이 큰 배</p></div>
        </div>
        <div className="rows7">
          <div className="rows7-h"><span>순위</span><span>선박</span><span>{meta.base_year}년 등급</span><span>{L.year}년 D·E 확률</span></div>
          {top.map((s) => (
            <a key={s.imo} className="rows7-r" href={`#/ship/${s.imo}`}>
              <span className="mono">{String(s.lr ?? "").padStart(2, "0")}</span>
              <span><b>{s.n}</b><small>{typeKo(s.t)} · {s.b ?? "–"}년 건조</small></span>
              <span>{s.cii ?? "–"}</span>
              <span className="big">{prob(s.pde?.[0])}</span>
            </a>
          ))}
        </div>
        <RoundBtn href="#/list">전체 리스트</RoundBtn>
      </div>
    </section>
  );
}

function Tools() {
  const B = import.meta.env.BASE_URL;
  return (
    <section className="s7 paper tools7">
      <div className="w7">
        <div className="tool7">
          <BigTitle as="h2" lines={[["한 척씩", 0], ["끝까지", 26], ["진단", 8]]} />
          <div className="tool7-b">
            <p>선박명이나 IMO 번호를 넣으면 등급 뒤의 원인, 같은 조건 배와의 차이, 앞으로 3년 전망, 연료비·탄소 비용을 한 화면에 보여 줍니다.</p>
            <a className="ul7" href="#/search">선박 찾기</a>
          </div>
          <img className="shot7" src={`${B}shots/diag.webp`} alt="선박 진단 화면" loading="lazy" />
        </div>
        <div className="tool7">
          <BigTitle as="h2" lines={[["연료비와", 0], ["탄소 비용을", 18], ["미리", 40]]} />
          <div className="tool7-b">
            <p>유가·환율·EU 배출권 가격을 바꿔 가며 {2026}~{2028}년 비용을 계산합니다. 환율과 배출권 가격은 자동으로 채워지고, 직접 넣은 값은 그대로 둡니다.</p>
            <a className="ul7" href="#/cost">비용 계산</a>
          </div>
          <img className="shot7" src={`${B}shots/cost.webp`} alt="비용 계산 화면" loading="lazy" />
        </div>
      </div>
    </section>
  );
}

function Proof({ meta }: { meta: Meta }) {
  const v = meta.validation?.position;
  if (!v || !Number.isFinite(v.retention_model)) return null;
  const P = (x: number) => Math.round(x * 100);
  return (
    <section className="s7 dark proof7">
      <div className="w7">
        <b className="proof7-n">{P(v.retention_model)}%</b>
        <p className="proof7-p">{v.select_until ?? 2023}년까지의 기록으로 ‘꾸준히 더 쓴다’고 고른 {num(v.n_selected)}척 중 {P(v.retention_model)}%가 다음 2년에도 같은 조건의 배보다 10% 이상 더 썼습니다.</p>
        <div className="proof7-bars">
          {([["여러 해 기록으로 고른 경우", v.retention_model, true], ["한 해 값으로 고른 경우", v.retention_single_year, false], ["무작위로 고른 경우", v.retention_random, false]] as const).map(([l, x, m]) => (
            <div key={l} className={m ? "m" : ""}><span>{l}</span><i><em style={{ width: `${x * 100}%` }} /></i><b>{P(x)}%</b></div>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function Home7({ ships, meta }: { ships: Ship[]; meta: Meta }) {
  const tigani = ships.find((s) => s.n === "TIGANI");
  const f = meta.funnel;
  return (
    <>
      <Hero meta={meta} />
      <Marquee rows={[
        [{ t: "항구 배출 분리" }, { t: "같은 조건 비교", n: "13" }, { t: "7년 기록", n: "7" }, { t: "보고값 점검", n: "5" }],
        [{ t: `${num(f.all)}척` }, { t: "비용 시나리오", n: "3" }, { t: `${meta.list.year} 리스트` }, { t: "3년 전망", n: "3" }],
      ]} />
      {tigani && <Tigani s={tigani} meta={meta} />}
      <Four meta={meta} />
      <Sieve meta={meta} />
      <Fly ships={ships} />
      <ListTeaser ships={ships} meta={meta} />
      <Tools />
      <Proof meta={meta} />
    </>
  );
}
