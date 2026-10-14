// 비용 계산: ① 팀 비용 표(가격 시나리오 낮음·기준·높음, 2026~2028) ② 입력 가격으로 개선 시나리오·순현재가치·회수 기간
// ③ 전년 대비 비용 변화 분해(LMDI). 가격은 이 브라우저에만 저장한다.
import { useEffect, useMemo, useState } from "react";
import type { HistRow, Meta, Scenario, Ship, ShipCost } from "../data";
import { loadCost, loadHist, SIZE_Q, typeKo, vsPeer } from "../data";
import { annualCost, applyAssumption, decompose, DECOMP_NAME, etsPhase, missingPrices, NO_ASSUMPTION, npvOf, pricesReady, speedFactor,
  type Assumption, type DecompKey, type Operation, type Prices, type Project } from "../calc";
import { setPrices, usePrices } from "../store";
import { krw, num, pct, tonnes } from "../format";
import { Help, Reveal, SearchIcon } from "../components/ui";
import MarketPanel from "../components/MarketPanel";
import EconomicsPanel from "../components/EconomicsPanel";
import { manual, originText, PRICE_KEYS } from "../market";
import ShipPhoto from "../components/ShipPhoto";
import { useShipFinder } from "./Home";
import { Decomp as ShareDecomp, eok } from "./Diagnosis";

/** 팀 가격 파일(config/cost_prices.csv)의 시나리오 가격 → 입력 가격. 연료는 연료 그룹에 맞는 대표 연료 */
function scenarioPrices(meta: Meta, sc: Scenario | "기준연도_2025", fg?: string): Prices {
  const row = (k: string) => meta.cost.prices.find((r) => r["항목"] === k);
  const v = (k: string) => Number(row(k)?.[sc]);
  const fuel = fg === "LNG 계열" ? "LNG" : "저유황유(VLSFO)";
  const o = { origin: "team" as const, source: sc === "기준연도_2025" ? "팀 가격 파일 2025 평균" : `팀 가격 파일 ${sc} 시나리오`, as_of: sc === "기준연도_2025" ? "2025" : "2026~2028" };
  return { fuel_usd: v(fuel), eua_eur: v("배출권(EUA)"), fx_usd: v("환율 USD"), fx_eur: v("환율 EUR"), date: o.source, src: { fuel_usd: o, eua_eur: o, fx_usd: o, fx_eur: o } };
}

const n = (v: string) => (v.trim() === "" ? undefined : Number(v.replace(/,/g, "")));

function NumField({ label, value, onChange, hint, unit, placeholder }: { label: string; value?: number; onChange: (v?: number) => void; hint?: string; unit?: string; placeholder?: string }) {
  const [s, setS] = useState(value === undefined ? "" : String(value));
  useEffect(() => { if (n(s) !== value) setS(value === undefined ? "" : String(value)); }, [value]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <label className="field">
      <span>{label}{unit && <span className="u"> {unit}</span>}</span>
      <input inputMode="decimal" type="number" step="any" value={s} placeholder={placeholder} onChange={(e) => { setS(e.target.value); onChange(n(e.target.value)); }} />
      {hint && <span className="hint">{hint}</span>}
    </label>
  );
}

export default function Cost({ ships, meta, imo, onPrices }: { ships: Ship[]; meta: Meta; imo?: number; onPrices: () => void }) {
  const s = imo ? ships.find((x) => x.imo === imo) : undefined;
  const by = meta.base_year;
  const prices = usePrices();
  const [prev, setPrev] = useState<Prices>({});
  const [as, setAs] = useState<Assumption>({ ...NO_ASSUMPTION, main_share: (s && meta.main_engine_share[s.t]) || NO_ASSUMPTION.main_share });
  const [sc, setSc] = useState<Scenario>("기준");
  const [tc, setTc] = useState<ShipCost | null | undefined>(undefined);
  useEffect(() => { if (s) loadCost().then((c) => setTc(c[String(s.imo)] ?? null)).catch(() => setTc(null)); }, [s]);
  const [tab, setTab] = useState<"out" | "econ" | "calc" | "dec" | "mkt">("out");
  const [pr, setPr] = useState<Project>({ days: 14, years: 10, discount_pct: 8 });
  const [hist, setHist] = useState<HistRow[] | null>(null);
  const [q, setQ] = useState("");
  const found = useShipFinder(ships, q, 6);
  useEffect(() => { if (s) loadHist().then((h) => setHist(h[String(s.imo)] ?? [])); }, [s]);

  const base: Operation | undefined = s && { sea: s.sea, dist: s.dist, berth: s.bt, cpf: s.cpf ?? 3.114, ets: s.ets ?? 0, phase: etsPhase(by) };
  const after = base && applyAssumption(base, as);
  const now = base && annualCost(base, prices), nowAfter = after && annualCost(after, prices);
  const fut = useMemo(() => {
    if (!s?.fc || !base) return undefined;
    return s.fc.map((f, i) => {
      const y = by + 1 + i;
      const at = (sea: number, a: Assumption) => annualCost(applyAssumption({ ...base, sea, phase: etsPhase(y) }, a), prices);
      return { y, p10: at(f[1], NO_ASSUMPTION), p50: at(f[0], NO_ASSUMPTION), p90: at(f[2], NO_ASSUMPTION), a50: at(f[0], as) };
    });
  }, [s, base?.sea, prices, as, by]); // eslint-disable-line react-hooks/exhaustive-deps
  const savings = fut ? fut.map((r) => (r.p50.total ?? 0) - (r.a50.total ?? 0)) : now && nowAfter ? [(now.total ?? 0) - (nowAfter.total ?? 0)] : [];
  const npv = npvOf(savings, pr);
  const hasAs = !!(as.eff_pct || as.berth_pct || as.speed_pct);
  const dec = useMemo(() => {
    if (!s || !hist || !base) return undefined;
    const h0 = hist.find((r) => r[0] === by - 1);
    if (!h0) return undefined;
    return decompose({ ...base, sea: h0[1], berth: h0[3], dist: h0[7], phase: etsPhase(by - 1) }, base, prev, prices);
  }, [s, hist, prev, prices, by]); // eslint-disable-line react-hooks/exhaustive-deps
  const P = (k: (typeof PRICE_KEYS)[number]) => (v?: number) => setPrices(manual(prices, k, v));
  const srcHint = (k: (typeof PRICE_KEYS)[number]) => { const o = prices.src?.[k]; return `${originText(prices, k)}${o?.as_of ? ` · ${o.as_of}` : ""}`; };

  return (
    <div className="wrap">
      <div className="page-h">
        <h1>비용 계산</h1>
        <p>팀 비용 모델의 가격 시나리오별 1~3년 비용을 제시하고, 입력 가격으로 개선 시나리오의 절감액·순현재가치·회수 기간을 산출합니다.</p>
      </div>
      <div className="pick">
        {s ? (
          <>
            <ShipPhoto type={s.t} seed={s.imo % 97} small />
            <div>
              <h3><a href={`#/ship/${s.imo}`} style={{ color: "var(--ink)" }}>{s.n}</a></h3>
              <p className="small muted">{typeKo(s.t)} · 크기 {SIZE_Q[s.sq]} · 해상 효율 {num(s.sea)} kg/해리 (동급 대비 {pct(vsPeer(s))}) · 정박 배출 {tonnes(s.bt)}/년</p>
            </div>
            <a className="btn ghost sm" href="#/cost">선박 변경</a>
          </>
        ) : (
          <>
            <div><h3>선박 선택</h3><p className="small muted">선박 진단 화면의 "비용 계산"에서 진입하면 자동으로 선택됩니다.</p></div>
            <div className="sr-box">
              <SearchIcon />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="선박명 또는 IMO 번호" aria-label="선박 검색" />
              {found.length > 0 && <ul className="sugg">{found.map(({ s: x }) => <li key={x.imo}><a href={`#/cost?imo=${x.imo}`}><b>{x.n}</b><span className="muted small">{typeKo(x.t)} · IMO {x.imo}</span></a></li>)}</ul>}
            </div>
          </>
        )}
      </div>

      {s && (
        <div className="dtabs-wrap ctabs">
          <div className="dtabs" role="tablist" aria-label="비용 계산 항목">
            {([["out", "비용 전망"], ["econ", "공용 서버 경제 계산"], ["calc", "가격·시나리오 계산"], ["dec", "전년 대비 변화"], ["mkt", "시장 지표"]] as const).map(([k, l]) => (
              <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>
            ))}
          </div>
        </div>
      )}
      <div className="tabpanel" hidden={!!s && tab !== "out"}>
      {s && (
        <section className="tc">
          <div className="tc-h">
            <div>
              <h2>{by + 1}~{by + 3}년 비용 전망</h2>
              <p>연료 그룹별 연료 가격과 EU ETS 배출권 가격 시나리오를 1~3년 전체 효율 예측(정박 포함)에 적용한 팀 비용 모델 결과입니다. 단위 억 원.</p>
            </div>
            <div className="seg" role="tablist" aria-label="가격 시나리오">
              {(["낮음", "기준", "높음"] as Scenario[]).map((k) => <button key={k} role="tab" aria-selected={sc === k} className={sc === k ? "on" : ""} onClick={() => setSc(k)}>{k}</button>)}
            </div>
          </div>
          {tc === undefined ? <p className="muted">불러오는 중…</p> : !tc || !tc.s ? (
            <p className="notice">{s.ly !== by ? `${by}년 보고가 없어 비용 표가 산출되지 않았습니다` : tc?.k ? `비용 표 미산출: ${tc.k}` : "예측값이 없어 비용 표가 산출되지 않았습니다"}. 아래에서 가격을 입력해 산정하십시오.</p>
          ) : (
            <div className="tc-grid">
              <div className="card">
                <div className="tbl">
                  <table className="t">
                    <thead><tr><th>연도</th><th>연료비</th><th>탄소 비용</th><th>합계</th><th>80% 구간</th><th>연료 배분 B</th><th>동급 기준 대비</th></tr></thead>
                    <tbody>
                      <tr className="muted"><td>{by} 실적</td><td>{eok(tc.b[0])}</td><td>{eok(tc.b[1])}</td><td>{eok(tc.b[2])}</td><td>–</td><td>–</td><td>{pct(tc.pg, 1)}</td></tr>
                      {tc.s[sc].map((r, i) => <tr key={i}><td>{by + 1 + i}</td><td>{eok(r[3])}</td><td>{eok(r[4])}</td><td><b>{eok(r[0])}</b></td><td>{eok(r[1], 0)}~{eok(r[2], 0)}</td><td>{eok(r[11])}</td><td className={r[5] > 0 ? "up" : "down"}>{r[5] >= 0 ? "+" : ""}{eok(r[5])}</td></tr>)}
                    </tbody>
                  </table>
                </div>
                <p className="card-foot">연료 그룹 {tc.fg ?? "–"}{tc.k ? ` · ${tc.k}` : ""}. 연료 배분 B는 석유계 잔사유를 중유(HSFO)로 본 경우. 동급 기준 = 동급 중간 해상 효율 + 이 선박의 정박 배출({by}년 실적 행은 거리당 연료 차이 %).</p>
              </div>
              <div className="card">
                <h3 style={{ marginBottom: 12 }}>{by}→{by + 1}년 변화 분해 · {sc}</h3>
                <ShareDecomp parts={[["효율", tc.s[sc][0][7]], ["규제 (ETS 부과율·CH₄·N₂O)", tc.s[sc][0][8]], ["연료 가격", tc.s[sc][0][9]], ["배출권 가격", tc.s[sc][0][10]]]} total={tc.s[sc][0][6]} />
                <p className="card-foot">효율 몫은 전체 효율(정박 포함) 예측 변화로, 정박 변동이 포함됩니다. 겹치는 몫은 요인 간 균등 배분(샤플리).</p>
              </div>
            </div>
          )}
          <Help label="가격·설정">
            <div className="tbl">
              <table className="t">
                <thead><tr><th>항목</th><th>단위</th><th>2025</th><th>낮음</th><th>기준</th><th>높음</th></tr></thead>
                <tbody>{meta.cost.prices.map((r) => <tr key={String(r["항목"])}><td>{r["항목"]}</td><td>{r["단위"]}</td><td>{num(Number(r["기준연도_2025"]), 1)}</td><td>{num(Number(r["낮음"]), 1)}</td><td>{num(Number(r["기준"]), 1)}</td><td>{num(Number(r["높음"]), 1)}</td></tr>)}</tbody>
              </table>
            </div>
            <p style={{ marginTop: 10 }}>확정되지 않은 설정:</p>
            <ul>{meta.cost.settings.map(([k, st, note]) => <li key={k}><b>{st}</b> · {note || k}</li>)}</ul>
          </Help>
        </section>
      )}

      </div>

      <div className="tabpanel" hidden={!!s && tab !== "econ"}>
      {s && <EconomicsPanel ship={s} ours={tc} by={by} sc={sc} />}
      </div>

      <div className="tabpanel" hidden={!!s && tab !== "calc"}>
      <div className="cost-grid">
        <div>
          <div className="in-card">
            <h3>가격</h3>
            <p>환율·배출권 가격은 공용 서버의 시장 조회값으로 자동으로 채웁니다(일별 기준·과거 관측값). 위 '공용 서버 경제 계산'에서 팀 시나리오 가격을 적용할 수도 있습니다. 직접 수정한 값은 유지되며 이 브라우저에만 저장됩니다.</p>
            <div className="dh-act" style={{ margin: "0 0 12px" }}>
              <button className="btn ghost sm" onClick={onPrices}>출처·기준일 보기</button>
              <button className="btn ghost sm" onClick={() => setPrices(scenarioPrices(meta, "기준", s?.fg))}>팀 기준 시나리오 가격 적용</button>
              <button className="btn ghost sm" onClick={() => setPrev(scenarioPrices(meta, "기준연도_2025", s?.fg))}>2025 실적 가격을 전년 가격으로</button>
            </div>
            <div className="grid2">
              <NumField label="연료 가격" unit="USD/t" value={prices.fuel_usd} onChange={P("fuel_usd")} hint={srcHint("fuel_usd")} />
              <NumField label="배출권 가격" unit="EUR/t" value={prices.eua_eur} onChange={P("eua_eur")} hint={srcHint("eua_eur")} />
              <NumField label="환율" unit="원/USD" value={prices.fx_usd} onChange={P("fx_usd")} hint={srcHint("fx_usd")} />
              <NumField label="환율" unit="원/EUR" value={prices.fx_eur} onChange={P("fx_eur")} hint={srcHint("fx_eur")} />
              <label className="field full"><span>가격 기준일 (보고서 표기용)</span><input type="text" value={prices.date ?? ""} placeholder="예: 2026-10-13" onChange={(e) => setPrices({ ...prices, date: e.target.value || undefined })} /></label>
            </div>
          </div>
          <div className="in-card">
            <h3>개선 시나리오</h3>
            <p>속력 변경은 모델 계수가 아닌 물리 규칙(주기관 연료 ∝ 속력², 보조기관 ∝ 시간)으로 산정합니다.</p>
            <div className="grid2">
              <NumField label="해상 효율 개선" unit="%" value={as.eff_pct} onChange={(v) => setAs({ ...as, eff_pct: v ?? 0 })} hint="예: 선체 클리닝 3%" />
              <NumField label="정박 배출 감축" unit="%" value={as.berth_pct} onChange={(v) => setAs({ ...as, berth_pct: v ?? 0 })} hint="예: 육상전원(AMP) 50%" />
              <NumField label="속력 변경" unit="%" value={as.speed_pct} onChange={(v) => setAs({ ...as, speed_pct: v ?? 0 })} hint="−10 = 10% 감속" />
              <NumField label="주기관 연료 비중" value={as.main_share} onChange={(v) => setAs({ ...as, main_share: v ?? 0.8 })} hint={s && meta.main_engine_share[s.t] ? `0~1, ${typeKo(s.t)} 기본값 ${meta.main_engine_share[s.t]}` : "0~1, 선종 기본값 미정 (0.8 적용)"} />
            </div>
            {as.speed_pct !== 0 && <p className="small muted" style={{ marginTop: 10 }}>속력 {pct(as.speed_pct)} → 해상 효율 ×{speedFactor(as.speed_pct / 100, as.main_share).toFixed(3)} (물리 규칙 기반 추정)</p>}
          </div>
          <div className="in-card">
            <h3>공사</h3>
            <p>공사비 입력 시 순현재가치와 회수 기간을 산출합니다.</p>
            <div className="grid2">
              <NumField label="공사비" unit="억 원" placeholder="견적가" value={pr.capex_krw === undefined ? undefined : pr.capex_krw / 1e8} onChange={(v) => setPr({ ...pr, capex_krw: v === undefined ? undefined : v * 1e8 })} />
              <NumField label="공사 기간" unit="일" value={pr.days} onChange={(v) => setPr({ ...pr, days: v ?? 0 })} />
              <NumField label="일일 운항 손실" unit="만 원" placeholder="용선료 등" value={pr.daily_loss_krw === undefined ? undefined : pr.daily_loss_krw / 1e4} onChange={(v) => setPr({ ...pr, daily_loss_krw: v === undefined ? undefined : v * 1e4 })} />
              <NumField label="효과 기간" unit="년" value={pr.years} onChange={(v) => setPr({ ...pr, years: Math.max(1, Math.round(v ?? 1)) })} />
              <NumField label="할인율" unit="%/년" value={pr.discount_pct} onChange={(v) => setPr({ ...pr, discount_pct: v ?? 0 })} />
            </div>
          </div>
          <div className="in-card">
            <h3>전년 가격 (선택)</h3>
            <p>입력 시 전년 대비 비용 변화 분해에 가격 효과가 반영됩니다.</p>
            <div className="grid2">
              <NumField label="연료 가격" unit="USD/t" value={prev.fuel_usd} onChange={(v) => setPrev({ ...prev, fuel_usd: v })} />
              <NumField label="배출권 가격" unit="EUR/t" value={prev.eua_eur} onChange={(v) => setPrev({ ...prev, eua_eur: v })} />
              <NumField label="환율" unit="원/USD" value={prev.fx_usd} onChange={(v) => setPrev({ ...prev, fx_usd: v })} />
              <NumField label="환율" unit="원/EUR" value={prev.fx_eur} onChange={(v) => setPrev({ ...prev, fx_eur: v })} />
            </div>
          </div>
        </div>

        <div className="result" aria-live="polite">
          {!s ? <p className="wait">선박을 선택하세요.</p> : !pricesReady(prices) ? (
            <>
              <span className="r-l">{by}년 연간 CO₂</span>
              <div className="r-big">{tonnes(now!.co2)}</div>
              <span className="r-sub">해상 {tonnes((s.sea * s.dist) / 1000)} + 정박 {tonnes(s.bt)} · 연료 약 {tonnes(now!.fuel)}</span>
              <p className="notice" style={{ marginTop: 18 }}>가격 입력 시 금액으로 환산합니다. 미입력: {missingPrices(prices).join(", ")}</p>
            </>
          ) : (
            <>
              <span className="r-l">{by}년 운항 기준 연간 비용</span>
              <div className="r-big">{krw(now!.total)}</div>
              <span className="r-sub">가격 기준일 {prices.date ?? "미입력"} · 연료 {num(prices.fuel_usd)} USD/t · 배출권 {num(prices.eua_eur)} EUR/t</span>
              <div className="r3">
                <div><span className="r-l">연료비</span><b>{krw(now!.fuelKrw)}</b></div>
                <div><span className="r-l">배출권</span><b>{krw(now!.etsKrw)}</b></div>
                <div><span className="r-l">시나리오 적용</span><b>{hasAs ? krw(nowAfter!.total) : "–"}</b></div>
              </div>
              {hasAs && <p className="r-sub" style={{ marginTop: 6 }}>연간 절감액 {krw((now!.total ?? 0) - (nowAfter!.total ?? 0))}</p>}

              <div className="blk">
                <h3>{by + 1}~{by + 3}년 비용 (입력 가격, 해상 효율 예측 적용)</h3>
                {fut ? (
                  <table>
                    <thead><tr><th>연도</th><th>중앙값</th><th>80% 구간</th>{hasAs ? <th>시나리오 적용</th> : null}</tr></thead>
                    <tbody>{fut.map((r) => <tr key={r.y}><td>{r.y}</td><td><b>{krw(r.p50.total)}</b></td><td>{krw(r.p10.total)} ~ {krw(r.p90.total)}</td>{hasAs ? <td>{krw(r.a50.total)}</td> : null}</tr>)}</tbody>
                  </table>
                ) : <p className="r-sub">1~3년 전망 미산출 선박입니다.</p>}
              </div>

              <div className="blk">
                <h3>투자 회수</h3>
                {!hasAs ? <p className="wait">개선 시나리오를 입력하세요.</p> : npv.upfront === undefined ? <p className="wait">공사비 입력 시 산출합니다.</p> : (
                  <>
                    <div className="r3" style={{ marginTop: 0 }}>
                      <div><span className="r-l">회수 기간</span><b>{npv.payback_years === undefined ? `${pr.years}년 내 미회수` : `${npv.payback_years.toFixed(1)}년`}</b></div>
                      <div><span className="r-l">투자액</span><b>{krw(npv.upfront)}</b></div>
                      <div><span className="r-l">첫해 절감액</span><b>{krw(savings[0])}</b></div>
                    </div>
                    <span className="r-l" style={{ display: "block", marginTop: 14 }}>순현재가치 ({pr.years}년, 할인율 {pr.discount_pct}%)</span>
                    <div className={`npv ${(npv.npv ?? 0) < 0 ? "neg" : ""}`}>{krw(npv.npv)}</div>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      </div>

      <div className="tabpanel" hidden={!!s && tab !== "dec"}>
      {s && !pricesReady(prices) && <p className="notice" style={{ marginTop: 18 }}>가격을 입력하면 전년 대비 변화 분해를 표시합니다. '가격·시나리오 계산' 탭에서 입력하세요.</p>}
      {s && pricesReady(prices) && (
        <section style={{ paddingBottom: 72 }}>
          <Reveal className="band-h" ><h2>전년 대비 비용 변화 분해</h2><p>{by - 1}→{by}년 비용 변화를 운항량·효율·정박·연료·가격·부과율 효과로 분해했습니다(LMDI). 각 효과의 합은 총 변화와 일치합니다.</p></Reveal>
          <div className="card">{!dec ? <p className="muted">{by - 1}년 보고가 없어 분해하지 않았습니다.</p> : <Decomp d={dec} />}</div>
          <Help><p>{by - 1}년의 연료 1톤당 CO₂와 ETS 대상 비율은 {by}년과 동일하다고 가정했습니다. 배출권 부과율은 {by - 1}년 {Math.round(etsPhase(by - 1) * 100)}%, {by}년 {Math.round(etsPhase(by) * 100)}%. 전년 가격 미입력 시 가격 효과는 0입니다.</p></Help>
        </section>
      )}
      </div>

      <div className="tabpanel" hidden={!!s && tab !== "mkt"}>
        <MarketPanel />
      </div>
    </div>
  );
}

const PLAIN_DEC: Partial<Record<DecompKey, string>> = { dist: "운항량(거리)", eff: "해상 효율", berth: "정박 배출", fuelkind: "연료 종류", fuelprice: "연료 가격", route: "ETS 대상 비율", phase: "배출권 부과율", euaprice: "배출권 가격" };

function Decomp({ d }: { d: { total: number; parts: Record<DecompKey, number> } }) {
  const ks = (Object.keys(d.parts) as DecompKey[]).filter((k) => Math.abs(d.parts[k]) > Math.abs(d.total) * 0.001 || Math.abs(d.parts[k]) > 1);
  const m = Math.max(...ks.map((k) => Math.abs(d.parts[k])), Math.abs(d.total)) || 1;
  const bar = (v: number, c: string) => (
    <div className="dc-track"><span className="z" />
      <span className="f" style={{ background: c, borderRadius: v >= 0 ? "0 4px 4px 0" : "4px 0 0 4px", left: v >= 0 ? "50%" : `${50 - (Math.abs(v) / m) * 50}%`, width: `${(Math.abs(v) / m) * 50}%` }} />
    </div>
  );
  return (
    <div>
      {ks.map((k) => <div key={k} className="dc-row"><span>{PLAIN_DEC[k] ?? DECOMP_NAME[k]}</span>{bar(d.parts[k], d.parts[k] >= 0 ? "var(--signal)" : "var(--base)")}<span className="dc-v">{d.parts[k] >= 0 ? "+" : ""}{krw(d.parts[k])}</span></div>)}
      <div className="dc-row"><span>합계</span>{bar(d.total, "var(--ink)")}<span className="dc-v">{d.total >= 0 ? "+" : ""}{krw(d.total)}</span></div>
    </div>
  );
}
