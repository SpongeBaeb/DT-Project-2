// 가격 자동 채우기: 공용 서버의 환율(Frankfurter 일별)·EUA(EEX 경매)를 가져와 입력 가격에 넣는다.
// 규칙: 사용자가 직접 입력한 항목은 덮어쓰지 않는다. 연료 가격은 공용 서버에 공급자가 없어(unavailable)
// 팀 가격 파일(config/cost_prices.csv)의 2025년 평균값을 출처와 함께 채운다. 모든 값은 기준일·출처를 같이 저장한다.
import { useSyncExternalStore } from "react";
import type { PriceKey, PriceOrigin, Prices } from "./calc";
import type { Meta } from "./data";
import { marketCarbon, marketFuel, marketFx, type MarketPoint } from "./shared";

export const PRICE_KEYS: PriceKey[] = ["fuel_usd", "eua_eur", "fx_usd", "fx_eur"];
export const PRICE_LABEL: Record<PriceKey, [string, string]> = {
  fuel_usd: ["연료 가격 (VLSFO)", "USD/t"], eua_eur: ["배출권 가격 (EUA)", "EUR/tCO₂"], fx_usd: ["환율", "원/USD"], fx_eur: ["환율", "원/EUR"],
};
const CONTRACT: Record<PriceKey, { metric: string; units: string[] }> = {
  fuel_usd: { metric: "VLSFO", units: ["USD/mt", "USD/t"] }, eua_eur: { metric: "EUA", units: ["EUR/tCO2"] },
  fx_usd: { metric: "USD/KRW", units: ["KRW per USD"] }, fx_eur: { metric: "EUR/KRW", units: ["KRW per EUR"] },
};

/** 화면에 쓸 수 있는 값인지 (상태·지표·단위가 약속과 맞고 양수) */
export function usable(key: PriceKey, p?: MarketPoint): p is MarketPoint & { value: number } {
  return !!p && ["live", "stale", "historical"].includes(p.status) && typeof p.value === "number" && Number.isFinite(p.value) && p.value > 0
    && p.metric === CONTRACT[key].metric && CONTRACT[key].units.includes(p.unit ?? "");
}
export const originOf = (p: MarketPoint): PriceOrigin => ({ origin: "auto", source: p.source, as_of: p.as_of_date, status: p.status, url: p.source_url, basis: p.price_basis });
export const isManual = (pr: Prices, k: PriceKey) => pr.src?.[k]?.origin === "manual" || (pr.src?.[k] === undefined && pr[k] !== undefined);

/** 팀 가격 파일의 2025년 값 (연료 그룹에 맞는 대표 연료) */
export function teamPrice(meta: Meta, k: PriceKey, fg?: string): { value: number; origin: PriceOrigin } | undefined {
  const name = { fuel_usd: fg === "LNG 계열" ? "LNG" : "저유황유(VLSFO)", eua_eur: "배출권(EUA)", fx_usd: "환율 USD", fx_eur: "환율 EUR" }[k];
  const row = meta.cost.prices.find((r) => r["항목"] === name);
  const v = Number(row?.["기준연도_2025"]);
  return Number.isFinite(v) && v > 0 ? { value: v, origin: { origin: "team", source: `팀 가격 파일 (${name}, 2025년 평균)`, as_of: "2025", status: "historical" } } : undefined;
}

/** 자동 값 병합. 직접 입력한 항목은 그대로 둔다 */
export function mergeMarket(cur: Prices, pts: Partial<Record<PriceKey, MarketPoint>>, meta?: Meta): Prices {
  const next: Prices = { ...cur, src: { ...cur.src } };
  for (const k of PRICE_KEYS) {
    if (isManual(cur, k)) continue;
    const p = pts[k];
    if (usable(k, p)) { next[k] = p.value; next.src![k] = originOf(p); continue; }
    const t = meta && teamPrice(meta, k);
    if (t) { next[k] = t.value; next.src![k] = t.origin; }
  }
  const dates = PRICE_KEYS.map((k) => next.src?.[k]?.as_of).filter(Boolean) as string[];
  if (!cur.date || !isManualDate(cur)) next.date = dates.length ? `자동 (${[...new Set(dates)].sort().join(" · ")})` : cur.date;
  return next;
}
const isManualDate = (p: Prices) => !!p.date && !p.date.startsWith("자동");
export const manual = (pr: Prices, k: PriceKey, v?: number): Prices => ({ ...pr, [k]: v, src: { ...pr.src, [k]: { origin: "manual", source: "직접 입력" } } });
export function applyAuto(pr: Prices, k: PriceKey, p?: MarketPoint, meta?: Meta): Prices {
  if (usable(k, p)) return { ...pr, [k]: p.value, src: { ...pr.src, [k]: originOf(p) } };
  const t = meta && teamPrice(meta, k);
  return t ? { ...pr, [k]: t.value, src: { ...pr.src, [k]: t.origin } } : pr;
}

export function originText(pr: Prices, k: PriceKey): string {
  const o = pr.src?.[k];
  if (isManual(pr, k)) return "직접 입력";
  if (!o) return "미입력";
  if (o.origin === "team") return "팀 가격 파일";
  if (o.origin === "economics") return "공용 서버 경제 지표";
  return o.status === "live" ? "일별 기준값" : o.status === "stale" ? "이전 수신값" : o.status === "historical" ? "과거 관측값" : "자동값 없음";
}
export function reasonText(p?: MarketPoint): string {
  if (!p) return "조회 전";
  if (p.reason === "licensed_provider_not_configured") return "공용 서버에 연료 가격 공급자가 연결되지 않았습니다. 팀 가격 파일 값 또는 직접 입력을 사용합니다.";
  if (p.status === "unavailable") return "공급자 자료 없음";
  if (p.status === "historical") return "저장된 과거 관측값입니다. 기준일을 확인하세요.";
  return "일별 기준값이며 장중 실시간 가격이 아닙니다.";
}

// ── 조회 상태 (앱 전체 공유) ──
interface State { loading: boolean; loaded: boolean; points: Partial<Record<PriceKey, MarketPoint>>; errors: string[]; at?: number }
let state: State = { loading: false, loaded: false, points: {}, errors: [] };
const subs = new Set<() => void>();
const publish = (s: State) => { state = s; subs.forEach((f) => f()); };
export const useMarket = () => useSyncExternalStore((f) => (subs.add(f), () => subs.delete(f)), () => state);

let pending: Promise<State> | null = null;
export function refreshMarket(force = false): Promise<State> {
  if (pending) return pending;
  if (!force && state.loaded && Date.now() - (state.at ?? 0) < 10 * 60_000) return Promise.resolve(state);
  publish({ ...state, loading: true, errors: [] });
  pending = (async () => {
    const [fx, carbon, fuel] = await Promise.allSettled([marketFx(), marketCarbon(), marketFuel()]);
    const points: State["points"] = {};
    const errors: string[] = [];
    if (fx.status === "fulfilled") { points.fx_usd = fx.value.usd_krw; points.fx_eur = fx.value.eur_krw; } else errors.push("환율을 조회하지 못했습니다.");
    if (carbon.status === "fulfilled") points.eua_eur = carbon.value.eua; else errors.push("EUA 가격을 조회하지 못했습니다.");
    if (fuel.status === "fulfilled") points.fuel_usd = fuel.value.vlsfo; else errors.push("연료 가격 상태를 조회하지 못했습니다.");
    const s: State = { loading: false, loaded: true, points, errors, at: Date.now() };
    publish(s);
    return s;
  })().finally(() => { pending = null; });
  return pending;
}
