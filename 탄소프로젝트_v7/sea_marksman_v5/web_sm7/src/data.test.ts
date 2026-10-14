// 화면 데이터 점검: 내보낸 JSON이 팀 결과 표의 약속을 지키는지 (반올림 허용 오차 안에서)
//   ① 원인 막대 합 = ln(실제 ÷ 동급 중간)   ② 비용 변화 분해의 몫 합 = 총변화   ③ 리스트 규칙
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { FACTORS, type Meta, type Ship, type ShipCost } from "./data";
import { verdictOf } from "./verdict";

const load = <T,>(f: string): T => JSON.parse(readFileSync(new URL(`../public/data/${f}`, import.meta.url), "utf-8"));
const ships = load<Ship[]>("ships.json");
const meta = load<Meta>("meta.json");
const cost = load<Record<string, ShipCost>>("cost.json");

describe("원인 막대", () => {
  it("모든 선박에서 막대 합 = ln(실제 ÷ 동급 중간)", () => {
    let worst = 0;
    for (const s of ships) {
      const sum = FACTORS.reduce((a, k) => a + s.c[k], 0) / 100;
      // 해상 효율·동급 중간은 0.1, 막대는 0.01%p 단위로 반올림
      worst = Math.max(worst, Math.abs(sum - Math.log(s.sea / s.peer)));
    }
    expect(worst).toBeLessThan(0.002);
  });
});

describe("비용 표", () => {
  it("변화 분해 몫의 합 = 총변화 (백만 원, 반올림 0.1)", () => {
    let worst = 0;
    for (const c of Object.values(cost)) for (const rows of Object.values(c.s ?? {})) for (const r of rows) {
      worst = Math.max(worst, Math.abs(r[7] + r[8] + r[9] + r[10] - r[6]));
    }
    expect(worst).toBeLessThan(0.5);
  });
  it("기준 연도 보고 선박만 비용 표가 있다", () => {
    const by = new Map(ships.map((s) => [String(s.imo), s.ly]));
    expect(Object.keys(cost).every((k) => by.get(k) === meta.base_year)).toBe(true);
  });
});

describe("다음 해 리스트", () => {
  const cur = ships.filter((s) => s.ly === meta.base_year);
  it("영업 타깃 = D·E 확률 ≥ 기준, 관찰 = 현재 A~C", () => {
    for (const s of cur.filter((x) => x.lst === "target")) expect(s.pde![0]).toBeGreaterThanOrEqual(meta.list.de_cut - 1e-3);
    for (const s of cur.filter((x) => x.lst === "watch")) expect(meta.list.watch_ratings).toContain(s.cii);
  });
  it("척수가 요약과 같다", () => {
    expect(cur.filter((s) => s.lst === "target").length).toBe(meta.list.target);
    expect(cur.filter((s) => s.lst === "watch").length).toBe(meta.list.watch);
  });
});

describe("판정", () => {
  it("TIGANI: 정박 요인, NEXUS: 데이터 확인 필요", () => {
    const t = ships.find((s) => s.n === "TIGANI")!, n = ships.find((s) => s.n === "NEXUS" && s.sig?.includes("report"))!;
    expect(verdictOf(t)).toBe("berth");
    expect(verdictOf(n)).toBe("check");
  });
});
