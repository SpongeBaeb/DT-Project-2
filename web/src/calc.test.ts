import { describe, expect, it } from "vitest";
import golden from "../../contracts/golden/cost_cases.json";
import { annualCost, decomposeCostChange, gapToPeerCost, payback, type Prices, type ShipYearCost } from "./calc";

const REL = 1e-9;
const close = (a: number, b: number) => expect(Math.abs(a - b)).toBeLessThanOrEqual(REL * Math.max(1, Math.abs(b)));

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Case = any;

describe("기준 사례 (contracts/golden/cost_cases.json)", () => {
  for (const c of golden.cases as Case[]) {
    it(c.name, () => {
      if (c.kind === "annualCost") {
        const r = annualCost(c.ship as ShipYearCost, c.prices as Prices);
        for (const k of Object.keys(c.expected)) close(r[k as keyof typeof r], c.expected[k]);
      } else if (c.kind === "gapToPeerCost") {
        const r = gapToPeerCost(c.ship, c.peerMedianKgNm, c.prices);
        for (const k of Object.keys(c.expected)) close(r[k as keyof typeof r], c.expected[k]);
      } else if (c.kind === "payback") {
        const r = payback(c.savings, c.investment);
        close(r.npvKrw, c.expected.npvKrw);
        close(r.upfrontKrw, c.expected.upfrontKrw);
        expect(r.paybackYear).toBe(c.expected.paybackYear);
      } else if (c.kind === "decomposeSum") {
        const d = decomposeCostChange(c.before.ship, c.before.prices, c.after.ship, c.after.prices);
        const sum = Object.values(d.effects).reduce((a, b) => a + b, 0);
        close(d.after - d.before, c.expected.change);
        close(sum, d.after - d.before); // 분해 합 = 변화 (정확히)
      } else {
        throw new Error(`알 수 없는 사례 종류: ${c.kind}`);
      }
    });
  }
});
