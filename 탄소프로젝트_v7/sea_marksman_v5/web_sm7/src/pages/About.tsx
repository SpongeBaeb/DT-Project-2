// 서비스 소개: 무엇을 떼어 내는지(네 가지), 진단 화면에서 무엇을 보는지(다섯 가지), 왜 지금인지(규제 연표)
import type { Meta } from "../data";
import { num } from "../format";
import { BigTitle, Marquee, RoundBtn } from "../components/Kinetic";
import { FOUR } from "./Home7";

const SEES = [
  ["같은 급 배보다 얼마나 더 쓰나", "같은 선종·크기의 배와 바다 위 효율(항구 배출을 뺀 거리당 CO₂)을 비교합니다. 여러 해 기록으로 꾸준히 더 쓰는지도 함께 봅니다."],
  ["왜 더 쓰나", "속력, 바다에 있던 시간, EU 안팎 항로 비중, 선령·설계, 연료가 차이를 각각 얼마나 만들었는지 막대로 나눕니다."],
  ["앞으로 3년", "바다 위 효율의 예상 범위와, 해마다 CII D·E를 받을 확률을 보여 줍니다."],
  ["돈으로 얼마인가", "연료비와 EU 배출권 비용을 가격 시나리오별로 계산하고, 동급 수준으로 개선하면 얼마가 줄어드는지 보여 줍니다."],
  ["숫자를 믿어도 되나", "의심스러운 보고값, 특이한 운항 패턴, 모델이 학습하지 않은 범위인지 점검합니다."],
];

const TIMELINE = [
  ["2023", "CII 등급 시행", "5,000톤 이상 국제 항해 선박이 매년 A~E 등급을 받습니다. 기준은 2019년보다 5% 엄격."],
  ["2024", "EU ETS 해운 포함", "EU 관련 항해 배출의 40%만큼 배출권을 사서 내야 합니다."],
  ["2025", "FuelEU Maritime", "선박 연료의 온실가스 강도 규제 시작. ETS 부담은 70%로."],
  ["2026", "ETS 100% · CII 11%", "배출 전량이 배출권 대상. CII 기준은 2019년보다 11% 엄격."],
  ["2030", "CII 21.5%", "IMO가 합의한 2027~2030년 감축률의 마지막 해. 같은 배도 해마다 등급이 내려갈 수 있습니다."],
];

export default function About({ meta }: { meta: Meta }) {
  return (
    <>
      <section className="s7 dark page7-top">
        <div className="w7">
          <BigTitle lines={[["등급이 아니라", 0], ["원인을", 34], ["봅니다", 10]]} />
          <p className="lead7">CII 등급이 나쁘다는 건 알 수 있습니다. 하지만 배가 낡아서인지, 항구에서 오래 기다려서인지, 그해만 운이 나빴는지는 등급만으로 알 수 없습니다. 원인이 다르면 해야 할 일도 다릅니다. Sea Marksman은 EU에 보고된 {num(meta.n_all)}척의 기록으로 그 원인을 나눠 보여 줍니다.</p>
        </div>
      </section>

      <section className="s7 slate">
        <div className="w7">
          <p className="lbl7">떼어 내는 것</p>
          <ol className="num7">
            {FOUR.map((f, i) => (
              <li key={f.k}>
                <span className="n">{String(i + 1).padStart(2, "0")}</span>
                <div><h3>{f.t}</h3><p>{f.why}</p><p className="fix">{f.fix}</p><p className="ev">{f.sub(meta)}</p></div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <Marquee tone="slate" rows={[
        [{ t: "바다 위 효율" }, { t: "같은 조건 예측값", n: "9" }, { t: "여러 해 위치", n: "7" }, { t: "의심 신호", n: "5" }],
      ]} />

      <section className="s7 slate">
        <div className="w7">
          <p className="lbl7">진단 화면에서 보는 것</p>
          <ol className="num7">
            {SEES.map(([h, p], i) => (
              <li key={h}><span className="n">{String(i + 1).padStart(2, "0")}</span><div><h3>{h}</h3><p>{p}</p></div></li>
            ))}
          </ol>
          <RoundBtn href="#/ship/9776767" tone="light">예시 보기</RoundBtn>
        </div>
      </section>

      <section className="s7 paper">
        <div className="w7">
          <BigTitle as="h2" lines={[["기준은", 0], ["해마다", 24], ["엄격해집니다", 6]]} />
          <ol className="tl7">
            {TIMELINE.map(([y, h, p]) => <li key={y}><b>{y}</b><div><h3>{h}</h3><p>{p}</p></div></li>)}
          </ol>
          <p className="note7">CII 등급 자체에는 벌금이 없습니다. D 3년 연속 또는 E 1회면 개선 계획을 내야 하고, 용선 계약과 금융 심사에서 불리해집니다. 직접적인 비용은 EU 배출권과 FuelEU에서 생깁니다.</p>
        </div>
      </section>

      <section className="s7 dark">
        <div className="w7 not7">
          <p className="lbl7">이 서비스가 하지 않는 것</p>
          <ul>
            <li>공식 CII 등급을 대신하지 않습니다. MRV 공개 자료로 계산한 근사 등급입니다.</li>
            <li>원인을 단정하지 않습니다. 요인별 막대는 통계적 연관이며 인과가 아닙니다.</li>
            <li>보고값을 고치지 않습니다. 의심스러운 값에는 표시만 합니다.</li>
          </ul>
          <RoundBtn href="#/method" tone="light">지표와 근거</RoundBtn>
        </div>
      </section>
    </>
  );
}
