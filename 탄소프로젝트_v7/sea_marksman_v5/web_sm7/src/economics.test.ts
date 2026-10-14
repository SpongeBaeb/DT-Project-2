// 공용 서버 경제 지표 → 입력 가격 변환
import { describe, expect, it } from "vitest";
import { economicsPrices, paramNum, type EconParams, type EconShip } from "./economics";

const meta = { data_source: "sqlite", calculation_mode: "provided_precomputed", price_date: "2026-10-09", economic_mrv_version: "v61", current_mrv_versions: ["v62"], warnings: [] };
const params: EconParams = {
  ...meta,
  items: [
    { key: "eua_price_eur_per_t_low", value: 65 }, { key: "eua_price_eur_per_t_base", value: 86 }, { key: "eua_price_eur_per_t_high", value: 92 },
    { key: "fx_krw_per_usd", value: 1356 }, { key: "fx_krw_per_eur", value: 1543 }, { key: "peer_file", value: "peer_score_2025.csv" },
  ],
};
const ship: EconShip = { ...meta, precomputed: [], inputs: { fuel_price_usd_per_t_low: 547.2, fuel_price_usd_per_t_base: 980.95, fuel_price_usd_per_t_high: 1108.2 } };

describe("경제 지표 가격 적용", () => {
  it("시나리오별 연료·배출권 가격과 고정 환율을 입력 가격으로 바꾼다", () => {
    const p = economicsPrices(params, ship, "기준")!;
    expect(p).toMatchObject({ fuel_usd: 980.95, eua_eur: 86, fx_usd: 1356, fx_eur: 1543 });
    expect(p.src?.fuel_usd?.origin).toBe("economics");
    expect(p.src?.fx_usd?.as_of).toBe("2026-10-09");
    expect(economicsPrices(params, ship, "낮음")).toMatchObject({ fuel_usd: 547.2, eua_eur: 65 });
    expect(economicsPrices(params, ship, "높음")).toMatchObject({ fuel_usd: 1108.2, eua_eur: 92 });
  });
  it("값이 하나라도 없으면 적용하지 않는다", () => {
    expect(economicsPrices(params, { ...ship, inputs: {} }, "기준")).toBeUndefined();
    expect(economicsPrices({ ...params, items: params.items.filter((i) => i.key !== "fx_krw_per_eur") }, ship, "기준")).toBeUndefined();
  });
  it("숫자가 아닌 항목은 숫자로 읽지 않는다", () => {
    expect(paramNum(params, "peer_file")).toBeUndefined();
    expect(paramNum(params, "eua_price_eur_per_t_base")).toBe(86);
  });
});
