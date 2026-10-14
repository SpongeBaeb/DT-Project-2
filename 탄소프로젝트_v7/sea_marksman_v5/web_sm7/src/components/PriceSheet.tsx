// 가격·환율 창: 항목마다 값, 출처, 기준일, 상태를 보여 주고 직접 수정하거나 조회값으로 되돌린다.
import { useEffect, useRef } from "react";
import type { PriceKey, Prices } from "../calc";
import type { Meta } from "../data";
import { isManual, manual, mergeMarket, originText, PRICE_KEYS, PRICE_LABEL, reasonText, refreshMarket, teamPrice, applyAuto, useMarket } from "../market";
import { setPrices, usePrices } from "../store";
import { num } from "../format";

export default function PriceSheet({ open, onClose, meta }: { open: boolean; onClose: () => void; meta: Meta }) {
  const prices = usePrices();
  const m = useMarket();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    ref.current?.querySelector<HTMLElement>("input,button")?.focus();
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  const refresh = async () => { const s = await refreshMarket(true); setPrices(mergeMarket(prices, s.points, meta)); };
  const resetAll = () => {
    let p: Prices = { ...prices, src: {}, date: undefined };
    for (const k of PRICE_KEYS) p = applyAuto(p, k, m.points[k], meta);
    setPrices(mergeMarket(p, m.points, meta));
  };
  const row = (k: PriceKey) => {
    const o = prices.src?.[k];
    const pt = m.points[k];
    const canAuto = (pt && pt.status !== "unavailable") || !!teamPrice(meta, k);
    return (
      <div key={k} className="ps-row">
        <label className="field">
          <span>{PRICE_LABEL[k][0]} <span className="u">{PRICE_LABEL[k][1]}</span></span>
          <input type="number" step="any" value={prices[k] ?? ""} onChange={(e) => setPrices(manual(prices, k, e.target.value === "" ? undefined : Number(e.target.value)))} />
        </label>
        <div className="ps-meta">
          <b className={`ps-tag ${isManual(prices, k) ? "man" : o?.origin ?? "none"}`}>{originText(prices, k)}</b>
          <span>{o ? `${o.source}${o.as_of ? ` · 기준일 ${o.as_of}` : ""}` : "출처 없음"}</span>
          {k === "fuel_usd" && pt && pt.status === "unavailable" && <small>{reasonText(pt)}</small>}
          {o?.basis && <small>{o.basis}</small>}
          {isManual(prices, k) && canAuto && <button className="link" onClick={() => setPrices(applyAuto(prices, k, pt, meta))}>조회값 사용</button>}
        </div>
      </div>
    );
  };
  return (
    <div className="ps-scrim" role="presentation" onClick={onClose}>
      <div className="ps" role="dialog" aria-modal="true" aria-label="가격·환율" ref={ref} onClick={(e) => e.stopPropagation()}>
        <div className="ps-h">
          <div><h2>가격 · 환율</h2><p>환율과 배출권 가격은 공용 서버에서 자동으로 채웁니다. 직접 수정한 항목은 자동 조회가 덮어쓰지 않습니다. 이 브라우저에만 저장됩니다.</p></div>
          <button className="ps-x" onClick={onClose} aria-label="닫기">×</button>
        </div>
        {PRICE_KEYS.map(row)}
        <label className="field" style={{ marginTop: 6 }}><span>가격 기준일 (보고서 표기용)</span><input type="text" value={prices.date ?? ""} placeholder="예: 2026-10-13" onChange={(e) => setPrices({ ...prices, date: e.target.value || undefined })} /></label>
        {m.errors.length > 0 && <p className="notice">{m.errors.join(" ")} 공용 서버가 유휴 상태면 첫 응답에 30초 이상 걸릴 수 있습니다.</p>}
        <div className="ps-act">
          <button className="btn ghost sm" onClick={refresh} disabled={m.loading}>{m.loading ? "조회 중…" : "다시 조회"}</button>
          <button className="btn ghost sm" onClick={resetAll}>모두 조회값으로</button>
          <button className="btn sm" onClick={onClose}>닫기</button>
        </div>
        <p className="ps-foot">환율: Frankfurter 일별 기준 환율(장중 실시간 아님). EUA: EEX 1차 경매 가중 평균(저장된 과거 관측). 연료: 공용 서버 공급자 미연결 시 팀 가격 파일 2025년 평균. 원/EUR {num(prices.fx_eur)} · 원/USD {num(prices.fx_usd)}</p>
      </div>
    </div>
  );
}
