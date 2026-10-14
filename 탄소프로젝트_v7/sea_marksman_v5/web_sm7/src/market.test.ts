// 가격 자동 채우기 규칙: 직접 입력은 지키고, 약속(지표·단위·상태)이 맞는 조회값만 쓰며, 연료는 팀 가격 파일로 채운다.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { Meta } from "./data";
import { isManual, manual, mergeMarket, usable } from "./market";
import type { MarketPoint } from "./shared";

const meta = JSON.parse(readFileSync(new URL("../public/data/meta.json", import.meta.url), "utf-8")) as Meta;
const pt = (metric: string, value: number | null, unit: string, status: MarketPoint["status"] = "live"): MarketPoint =>
  ({ metric, value, unit, status, as_of_date: "2026-10-13", fetched_at: "", source: "test" });
const pts = {
  fx_usd: pt("USD/KRW", 1336.68, "KRW per USD"), fx_eur: pt("EUR/KRW", 1497.5, "KRW per EUR"),
  eua_eur: pt("EUA", 84.6, "EUR/tCO2", "historical"), fuel_usd: pt("VLSFO", null, "USD/mt", "unavailable"),
};

describe("가격 자동 채우기", () => {
  it("조회값과 연료 대체값을 출처와 함께 채운다", () => {
    const p = mergeMarket({}, pts, meta);
    expect(p.fx_usd).toBe(1336.68);
    expect(p.eua_eur).toBe(84.6);
    expect(p.src?.eua_eur?.status).toBe("historical");
    expect(p.src?.fuel_usd?.origin).toBe("team");
    expect(p.fuel_usd).toBeGreaterThan(0);
  });
  it("직접 입력한 값은 덮어쓰지 않는다", () => {
    const p = mergeMarket(manual({}, "fx_usd", 1400), pts, meta);
    expect(p.fx_usd).toBe(1400);
    expect(isManual(p, "fx_usd")).toBe(true);
  });
  it("지표·단위가 다르거나 값이 없으면 쓰지 않는다", () => {
    expect(usable("fx_usd", pt("USD/KRW", 1336, "KRW per EUR"))).toBe(false);
    expect(usable("eua_eur", pt("EUA", null, "EUR/tCO2"))).toBe(false);
    expect(usable("eua_eur", pt("EUA", 80, "EUR/tCO2", "mock"))).toBe(false);
  });
});
