import { describe, expect, it } from "vitest";
import { annualCost, applyAssumption, decompose, npvOf, speedFactor, type Operation, type Prices } from "./calc";

const P: Prices = { fuel_usd: 600, eua_eur: 70, fx_usd: 1400, fx_eur: 1500 };
const o: Operation = { sea: 400, dist: 50000, berth: 2000, cpf: 3.11, ets: 0.6, phase: 0.7 };

describe("연간 비용", () => {
  it("CO₂ = 해상 효율 × 거리 + 정박, 연료 = CO₂ ÷ 연료 1톤당 CO₂", () => {
    const c = annualCost(o, P);
    expect(c.co2).toBeCloseTo(22000, 6);
    expect(c.fuel).toBeCloseTo(22000 / 3.11, 6);
    expect(c.etsKrw).toBeCloseTo(22000 * 0.6 * 0.7 * 70 * 1500, 3);
  });
  it("가격이 없으면 금액은 비운다", () => {
    expect(annualCost(o, {}).total).toBeUndefined();
  });
});

describe("속력 가정 (물리 규칙)", () => {
  it("변화 없으면 1, 주기관만이면 속력²", () => {
    expect(speedFactor(0, 0.8)).toBeCloseTo(1, 12);
    expect(speedFactor(-0.1, 1)).toBeCloseTo(0.81, 12);
  });
  it("보조기관 비중이 있으면 감속 효과가 줄어든다", () => {
    expect(speedFactor(-0.1, 0.7)).toBeGreaterThan(0.81);
    expect(applyAssumption(o, { eff_pct: 5, berth_pct: 50, speed_pct: 0, main_share: 0.8 }).berth).toBe(1000);
  });
});

describe("변화 분해 (LMDI)", () => {
  it("나눈 값의 합 = 변화 (정확히)", () => {
    const o0: Operation = { sea: 380, dist: 48000, berth: 1500, cpf: 3.12, ets: 0.55, phase: 0.4 };
    const p0: Prices = { fuel_usd: 650, eua_eur: 80, fx_usd: 1350, fx_eur: 1450 };
    const d = decompose(o0, o, p0, P)!;
    const sum = Object.values(d.parts).reduce((a, b) => a + b, 0);
    expect(Math.abs(sum - d.total) / Math.abs(d.total)).toBeLessThan(1e-9);
    expect(d.parts.phase).toBeGreaterThan(0); // 부과 비율 40% → 70%
  });
  it("가격이 한 해만 있으면 가격 효과는 0", () => {
    const d = decompose({ ...o, sea: 380 }, o, {}, P)!;
    expect(d.parts.fuelprice).toBeCloseTo(0, 9);
    expect(d.parts.euaprice).toBeCloseTo(0, 9);
  });
});

describe("순현재가치·회수", () => {
  it("공사비 100, 매년 30 절감이면 3.33년에 회수", () => {
    const r = npvOf([30], { capex_krw: 100, days: 0, years: 10, discount_pct: 0 });
    expect(r.payback_years).toBeCloseTo(100 / 30, 9);
    expect(r.npv).toBeCloseTo(200, 9);
  });
});
