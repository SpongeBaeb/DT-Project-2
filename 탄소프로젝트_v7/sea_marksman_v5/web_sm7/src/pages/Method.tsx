// 지표와 근거: 왜 CII 한 글자로는 부족한가, 무엇을 어떻게 나눠 보는가, 어떤 모델·서버·자료가 쓰였는가
import { useEffect, useState } from "react";
import type { Meta } from "../data";
import { health } from "../api";
import { clusterCoverage, clusterRuns, initialModel, sharedHealth, type ClusterCoverage, type ClusterRun, type InitialModelInfo } from "../shared";
import { num } from "../format";
import { Card, Help, prob } from "../components/ui";
import { ILLUSIONS, illusionEvidence } from "../components/Illusions";

const PARTS: Record<string, string> = {
  berth: "BerthCompare · berth_ratio, berth_z, berth_hist_z",
  cond: "PeerGroup, CommonResidualBaseline · sea_eff_expected, contrib_*",
  year: "EmpiricalBayesPosition · position_z, persist_prob",
  report: "IllusionSignals · sig_berth·short·fuel·report·special",
};
const CII_Z = [[2023, 5], [2024, 7], [2025, 9], [2026, 11], [2027, 13.625], [2028, 16.25], [2029, 18.875], [2030, 21.5]] as const;

type St = { ok: boolean | null; text: string };
export default function Method({ meta }: { meta: Meta }) {
  const [local, setLocal] = useState<St>({ ok: null, text: "확인 중" });
  const [sh, setSh] = useState<St>({ ok: null, text: "확인 중 (유휴 상태면 30초 이상)" });
  const [im, setIm] = useState<InitialModelInfo | null>(null);
  const [runs, setRuns] = useState<ClusterRun[] | null>(null);
  const [cov, setCov] = useState<ClusterCoverage | null>(null);
  const [tab, setTab] = useState<"cii" | "reg" | "srv" | "def">("cii");
  useEffect(() => {
    health().then((h) => setLocal({ ok: true, text: `연결됨 · 모델 ${h.model_version} · 데이터 ${h.data_hash}` })).catch((e) => setLocal({ ok: false, text: String(e.message) }));
    sharedHealth().then(() => setSh({ ok: true, text: "연결됨" })).catch((e) => setSh({ ok: false, text: String(e.message) }));
    initialModel().then(setIm).catch(() => undefined);
    clusterRuns().then(setRuns).catch(() => undefined);
    clusterCoverage().then(setCov).catch(() => undefined);
  }, []);
  const ev = illusionEvidence(meta);
  const v = meta.validation;
  return (
    <div className="wrap" style={{ paddingBottom: 80 }}>
      <div className="page-h">
        <h1>지표와 근거</h1>
        <p>CII 등급은 한 글자로 많은 사정을 감춥니다. Sea Marksman은 그 뒤의 원인을 네 가지 착시로 나눠 보여 주고, 판단은 사용자에게 맡깁니다.</p>
      </div>

      <div className="dtabs-wrap mtabs">
        <div className="dtabs" role="tablist" aria-label="지표와 근거">
          {([["cii", "CII와 네 가지 착시"], ["reg", "규제 배경"], ["srv", "모델·서버 상태"], ["def", "지표 정의·자료"]] as const).map(([k, l]) => (
            <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>
          ))}
        </div>
      </div>

      <div className="tabpanel" hidden={tab !== "cii"}>
      <section className="m-sec">
        <h2>CII 한 글자와 Sea Marksman</h2>
        <Card>
          <div className="tbl">
            <table className="t m-vs">
              <thead><tr><th /><th>CII</th><th>Sea Marksman</th></tr></thead>
              <tbody>
                <tr><td>결과</td><td>A~E 한 글자</td><td>바다 위 효율, 항구 배출, 같은 조건 대비 차이, 원인, 여러 해 위치, 의심 신호</td></tr>
                <tr><td>항구 배출</td><td>등급에 섞임</td><td>따로 계산해 같은 조건의 배·그 배의 예년과 비교</td></tr>
                <tr><td>비교 대상</td><td>선종별 기준선 하나</td><td>같은 선종·연도·크기의 배, 속력·항로·선령까지 맞춘 예측값</td></tr>
                <tr><td>기간</td><td>그해 한 번</td><td>최대 7년 기록을 함께 봄 (위치 z)</td></tr>
                <tr><td>보고 오류</td><td>그대로 반영</td><td>의심 신호 5종으로 표시</td></tr>
                <tr><td>해석</td><td>등급이 곧 결론</td><td>원인별 근거를 함께 제시 (통계적 연관이며 인과가 아님)</td></tr>
              </tbody>
            </table>
          </div>
        </Card>
      </section>

      <section className="m-sec">
        <h2>네 가지 착시와 해결</h2>
        <div className="m-ill">
          {ILLUSIONS.map((x) => (
            <div key={x.k} className="card m-ill-card">
              <div className="ill-h"><span className="ill-n">{x.n}</span><b>{x.name}</b></div>
              <p><span className="k">원인</span>{x.why}</p>
              <p><span className="k">근거 ({meta.base_year}년)</span>{ev[x.k]}</p>
              <p><span className="k">해결</span>{x.fix}</p>
              <p className="muted small">{PARTS[x.k]}</p>
            </div>
          ))}
        </div>
      </section>

      </div>

      <div className="tabpanel" hidden={tab !== "reg"}>
      <section className="m-sec">
        <h2>규제 배경</h2>
        <div className="two">
          <Card title="CII 감축률 (2019년 기준선 대비)">
            <div className="z-steps" role="img" aria-label={CII_Z.map(([y, z]) => `${y}년 ${z}%`).join(", ")}>
              {CII_Z.map(([y, z]) => <div key={y} className={y >= 2026 ? "f" : ""}><i style={{ height: `${(z / 21.5) * 100}px` }} /><b>{z}%</b><span>{y}</span></div>)}
            </div>
            <p className="card-foot">2023~2026년 MEPC.338(76), 2027~2030년 MEPC 83 합의. 감축률이 커질수록 같은 배도 등급이 내려갑니다.</p>
          </Card>
          <Card title="등급이 나쁠 때 따라오는 것">
            <ol className="m-steps">
              <li><b>개선 계획</b>D등급 3년 연속 또는 E등급 1회 → 선박에너지효율관리계획(SEEMP) 시정 조치 계획 제출</li>
              <li><b>계약·금융</b>용선 계약의 CII 조항(BIMCO), 금융기관의 탈탄소 정렬 평가(Poseidon Principles)</li>
              <li><b>EU 규제</b>EU ETS 배출권 제출, FuelEU Maritime 불이행 벌금·입항 제한</li>
            </ol>
            <p className="card-foot">CII 등급 자체에는 벌금이 없습니다. 벌금과 입항 제한은 EU 규제(배출권·FuelEU)의 불이익입니다. IMO는 항해 배출 기반 CII 개편을 2028년까지 검토합니다.</p>
          </Card>
        </div>
      </section>

      </div>

      <div className="tabpanel" hidden={tab !== "srv"}>
      <section className="m-sec">
        <h2>모델과 서버 상태</h2>
        <div className="two">
          <Card title="팀 모델 진단 서버 (로컬)" sub={<StatusDot s={local} />}>
            <p className="small">{local.text}</p>
            <p className="small muted" style={{ marginTop: 6 }}>결과 표·진단 화면·내 선박 진단의 기본 모델. 구성: {meta.stages.join(" → ")}</p>
            {v?.verdict && (
              <div className="tbl" style={{ marginTop: 12 }}>
                <table className="t">
                  <thead><tr><th>합격 기준</th><th>값</th><th>기준</th><th>판정</th></tr></thead>
                  <tbody>{v.verdict.map((r) => <tr key={r.criterion}><td>{r.criterion}</td><td>{r.value === null ? "–" : num(r.value, 3)}</td><td>{r.threshold}</td><td className={r.pass ? "down" : "up"}>{r.pass ? "통과" : "미달"}</td></tr>)}</tbody>
                </table>
              </div>
            )}
          </Card>
          <Card title="팀 공용 서버" sub={<StatusDot s={sh} />}>
            <p className="small">{sh.text}</p>
            <p className="small muted" style={{ marginTop: 6 }}>시장 가격(환율·EUA·에너지·운임), 군집 상세·유사 선박, 초기 모델 진단(팀 모델 서버가 꺼져 있을 때 대체).</p>
            {im && (
              <>
                <p className="small" style={{ marginTop: 10 }}>초기 모델 {im.model_version} · {im.model_kind} · 검증: {im.validation_method}</p>
                <Help label="선종별 보류 검증">
                  <div className="tbl">
                    <table className="t">
                      <thead><tr><th>선종</th><th>학습 척수</th><th>검증 척수</th><th>해상 효율 R²</th><th>MAE (중간값 기준)</th></tr></thead>
                      <tbody>{Object.entries(im.types).map(([t, x]) => <tr key={t}><td>{t}</td><td>{num(x.n_ships)}</td><td>{num(x.validation.n_test)}</td><td>{x.validation.sea?.r2?.toFixed(2) ?? "–"}</td><td>{x.validation.sea ? `${num(x.validation.sea.mae, 1)} (${num(x.validation.sea.median_baseline_mae, 1)})` : "–"}</td></tr>)}</tbody>
                    </table>
                  </div>
                  <ul>{im.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
                </Help>
              </>
            )}
          </Card>
        </div>
      </section>

      <section className="m-sec">
        <h2>군집 품질과 연결 현황</h2>
        <Card>
          {!runs ? <p className="muted small">공용 서버에서 불러오는 중…</p> : (
            <div className="tbl">
              <table className="t">
                <thead><tr><th>축</th><th>방법 · 유형 수</th><th>선박</th><th>실루엣</th><th>안정성(평균·최소)</th><th>규칙 정확도</th><th>기간</th></tr></thead>
                <tbody>{runs.map((r) => (
                  <tr key={r.axis}><td>{r.axis_name}<small className="muted" style={{ display: "block" }}>{r.variables}</small></td><td>{r.method} · {r.n_types}개</td><td>{num(r.n_ships)}</td><td>{r.silhouette.toFixed(2)}</td><td>{r.stability_mean.toFixed(2)} · {r.stability_min.toFixed(2)}</td><td>{prob(r.rule_accuracy)}</td><td>{r.window}</td></tr>
                ))}</tbody>
              </table>
            </div>
          )}
          {cov && <p className="card-foot">전체 {num(cov.ships_total)}척 중 {num(cov.matched)}척({prob(cov.matched / cov.ships_total)})이 군집에 연결됩니다. 연결되지 않은 {num(cov.ships_without_cluster)}척은 군집 기준 기간(2023~2025) 보고가 없는 선박이며, 설계 효율 값이 없어 선령·설계 프로파일이 비는 선박은 {num(cov.profile_missing)}척입니다.</p>}
          <p className="card-foot">실루엣은 유형이 서로 얼마나 분리되는지(1에 가까울수록 좋음), 안정성은 표본을 바꿔 다시 묶었을 때 같은 유형으로 남는 비율입니다.</p>
        </Card>
      </section>

      </div>

      <div className="tabpanel" hidden={tab !== "def"}>
      <section className="m-sec">
        <h2>지표 정의</h2>
        <Card>
          <dl className="m-defs">
            <dt>해상 효율</dt><dd>(CO₂ − 정박 중 CO₂) ÷ 항해 거리, kg CO₂/해리. 정박 배출이 섞이지 않은 운항 효율.</dd>
            <dt>동급</dt><dd>같은 선종·보고 연도·크기 4분위(CII 용량 기준) 선박. 동급 중간값과의 차이가 "동급 대비".</dd>
            <dt>같은 조건 예측값</dt><dd>평균 속력(대기 포함)·해상 시간·EU 역내 비중·선령·설계·내빙·대체연료를 맞춘 공통잔차 모델 예측.</dd>
            <dt>원인 막대</dt><dd>동급 대비 차이를 요인별로 나눈 값. 모든 막대의 합 = ln(실제 ÷ 동급 중간값).</dd>
            <dt>위치 z</dt><dd>같은 조건 대비 차이를 여러 해 모아 경험적 베이즈로 줄여 잡은 선종 내 표준 점수. 2 이상이면 지속 초과.</dd>
            <dt>유지 확률</dt><dd>이듬해에도 같은 조건 예측보다 10% 넘게 높을 확률 (기준 연도 평균 {prob(meta.persist.base_rate)}).</dd>
            <dt>착시 신호 5종</dt><dd>정박(같은 조건·예년 대비 2σ 이상), 짧은 구간(EU 해상 {meta.thresholds.short_sea_hours}시간 미만), 연료(연료 1톤당 CO₂ {meta.thresholds.co2_per_fuel_min} 미만), 보고 오류(평균 {meta.thresholds.min_speed_kn}노트 미만 또는 적재량 &gt; 재화중량×{meta.thresholds.cargo_dwt_ratio_max}), 특수 운항.</dd>
            <dt>CII D·E 확률</dt><dd>전체 효율(정박 포함) 1~3년 분위 예측과 연도별 등급 경계·감축률로 계산.</dd>
            <dt>CII 등급</dt><dd>MRV 자료로 계산한 근사 등급(EU 관련 항해, 내빙 보정). 공식 DCS 등급과 다를 수 있습니다.</dd>
          </dl>
        </Card>
      </section>

      <section className="m-sec">
        <h2>자료와 판</h2>
        <Card>
          <p className="small">EU THETIS-MRV 공개 보고 {meta.sources?.join(" · ")} (연도:판). 총톤수 5,000 이상, {num(meta.n_all)}척 · 기준 연도 {meta.base_year}년 {num(meta.n_ships)}척.</p>
          <p className="small" style={{ marginTop: 6 }}>시장 자료: 환율 Frankfurter(일별 기준), EUA EEX 1차 경매(저장된 과거 관측), Brent·아시아 LNG FRED, BDI 팀 제공 자료. 연료 가격 공급자는 공용 서버에 아직 연결되지 않아 팀 가격 파일(config/cost_prices.csv)을 사용합니다.</p>
          <p className="small muted" style={{ marginTop: 6 }}>모델 {meta.model_version} · 데이터 {meta.data_hash} · 결과 표 형식 {meta.result_table_version} · 생성 {meta.generated}</p>
        </Card>
      </section>
      </div>
    </div>
  );
}

const StatusDot = ({ s }: { s: St }) => <span className={`dot ${s.ok === null ? "" : s.ok ? "ok" : "bad"}`}>{s.ok === null ? "확인 중" : s.ok ? "정상" : "연결 안 됨"}</span>;
