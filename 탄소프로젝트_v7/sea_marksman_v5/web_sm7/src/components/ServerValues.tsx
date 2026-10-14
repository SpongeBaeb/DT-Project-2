// 공용 서버 값: 서버가 MRV 원자료로 계산한 CII, 규제 평가 상태, 군집 소속 확률. 우리(팀 모델) 값과 나란히 보여 준다.
import { useEffect, useState, type ReactNode } from "react";
import type { Grade, Ship } from "../data";
import { clusterTypes, shipDetail, type ClusterDetail, type ClusterType, type ShipDetail } from "../shared";
import { num, pct } from "../format";
import { Card, Grade_, prob } from "./ui";

const f = (v: unknown) => { const x = Number(v); return Number.isFinite(x) ? x : undefined; };
const has = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export default function ServerValues({ s, cl }: { s: Ship; cl: ClusterDetail | null | undefined }) {
  const [d, setD] = useState<ShipDetail | null | undefined>(undefined);
  const [types, setTypes] = useState<ClusterType[]>([]);
  useEffect(() => {
    let alive = true;
    setD(undefined);
    shipDetail(s.imo).then((x) => alive && setD(x)).catch(() => alive && setD(null));
    clusterTypes().then((t) => alive && setTypes(t)).catch(() => undefined);
    return () => { alive = false; };
  }, [s.imo]);

  if (d === undefined) return <p className="muted">공용 서버에서 불러오는 중입니다. 서버가 유휴 상태면 30초 이상 걸릴 수 있습니다.</p>;
  if (d === null) return <p className="notice">공용 서버에 이 선박의 상세가 없거나 연결되지 않았습니다.</p>;

  const r = d.source_record;
  const a = d.analysis;
  const att = f(r.cii_attained), req = f(r.cii_required);
  const sRatio = f(r.cii_ratio_2026basis);
  const rows: { k: string; ours: ReactNode; srv: ReactNode; ok?: boolean }[] = [
    { k: `${a.data_year}년 CII 등급`, ours: <Grade_ g={s.cii} sm />, srv: <Grade_ g={r.cii_rating as Grade} sm />, ok: s.cii === r.cii_rating },
    { k: "2026 기준선 등급", ours: <Grade_ g={s.cii26} sm />, srv: <Grade_ g={r.cii_rating_2026basis as Grade} sm />, ok: s.cii26 === r.cii_rating_2026basis },
    { k: "2026 기준선 대비 비율", ours: s.ciir?.toFixed(3) ?? "–", srv: sRatio?.toFixed(3) ?? "–", ok: s.ciir !== undefined && sRatio !== undefined && Math.abs(s.ciir - sRatio) < 0.02 },
    { k: "달성 · 요구 CII (gCO₂/t·해리)", ours: "–", srv: att !== undefined && req !== undefined ? `${att.toFixed(2)} · ${req.toFixed(2)}` : "–" },
  ];
  const allOk = rows.filter((x) => x.ok !== undefined).every((x) => x.ok);
  const ra = a.regulatory_assessment, ma = a.miss_probability_assessment;
  const unevaluated = ra.status === "not_evaluated" || ma.status === "not_evaluated";
  const sh = cl?.ship;
  const name = (axis: "exposure" | "profile", id: number) => types.find((t) => t.axis === axis && t.type_id === id)?.type_name ?? `유형 ${id}`;
  const axes: { title: string; axis: "exposure" | "profile"; p: (number | null | undefined)[]; outlier: boolean }[] = sh ? [
    { title: "EU 규제 노출도", axis: "exposure", p: [sh.exposure_prob_1, sh.exposure_prob_2, sh.exposure_prob_3], outlier: !!sh.exposure_outlier },
    { title: "선령·설계 프로파일", axis: "profile", p: [sh.profile_prob_1, sh.profile_prob_2, sh.profile_prob_3], outlier: !!sh.profile_outlier },
  ] : [];

  return (
    <div className="srv">
      <Card title="CII 계산 대조" sub="팀 모델 값과 공용 서버 값">
        <div className="tbl">
          <table className="t srv-t">
            <thead><tr><th>항목</th><th>팀 모델</th><th>공용 서버</th><th /></tr></thead>
            <tbody>{rows.map((x) => <tr key={x.k}><td>{x.k}</td><td>{x.ours}</td><td>{x.srv}</td><td className={x.ok === undefined ? "" : x.ok ? "down" : "up"}>{x.ok === undefined ? "" : x.ok ? "일치" : "다름"}</td></tr>)}</tbody>
          </table>
        </div>
        <p className="card-foot">{allOk ? "두 계산 결과가 같습니다. " : "두 값이 다릅니다. 기준선 연도나 선종 분류 차이일 수 있습니다. "}서버는 MRV 원자료로, 팀 모델은 팀 파이프라인(연도별 선종 기준선)으로 계산합니다. 공식 등급이 아닌 근사값입니다.</p>
      </Card>

      <Card title="규제 평가 상태" sub={`공용 서버 · ${ma.target_year}년 기준`}>
        <dl className="srv-dl">
          <div><dt>필요 개선율</dt><dd>{has(ma.required_improvement) ? `${(ma.required_improvement * 100).toFixed(1)}%` : "–"}</dd></div>
          <div><dt>기준 확률 p*</dt><dd>{has(ma.p_star) ? prob(ma.p_star) : "–"}</dd></div>
          <div><dt>미달 확률</dt><dd>{has(ma.p_miss) ? prob(ma.p_miss) : "미산출"}</dd></div>
          <div><dt>평가 상태</dt><dd>{unevaluated ? "미평가" : "평가됨"}</dd></div>
        </dl>
        {unevaluated && <p className="notice" style={{ marginTop: 12 }}>공용 서버는 아직 내년 미달 확률을 계산하지 않습니다(예측 모델 미탑재). 이 화면의 D·E 확률과 기준 미달 확률은 팀 모델 값입니다.</p>}
        <p className="card-foot">서버의 미달 확률은 팀의 추세 기반 값이며 공식 CII 등급이 아닙니다.</p>
      </Card>

      <Card title="군집 소속 확률" sub={cl?.ship.cluster_run ?? "공용 서버 군집"}>
        {!sh ? <p className="muted small">군집 결과가 없습니다.</p> : (
          <>
            {axes.map((ax) => (
              <div key={ax.axis} className="srv-ax">
                <b>{ax.title}{ax.outlier ? <em className="srv-flag">이상치</em> : null}</b>
                {ax.p.map((p, i) => {
                  const mx = Math.max(...ax.p.map((x) => x ?? 0));
                  return <div key={i} className={`srv-bar ${(p ?? 0) === mx && mx > 0 ? "max" : ""}`}><span>{name(ax.axis, i + 1)}</span><i><em style={{ width: `${(p ?? 0) * 100}%` }} /></i><b>{has(p) ? prob(p) : "–"}</b></div>;
                })}
              </div>
            ))}
            <dl className="srv-dl">
              <div><dt>설계 효율</dt><dd>{sh.design_level ?? "–"}{has(sh.design_rank_pct) ? ` · 상위 ${num(100 - sh.design_rank_pct, 0)}%` : ""}</dd></div>
              <div><dt>거리당 CO₂ (동급 대비)</dt><dd>{has(sh.co2nm_vs_peers_pct) ? pct(sh.co2nm_vs_peers_pct) : "–"}</dd></div>
              <div><dt>거리당 CO₂ (같은 속력 대비)</dt><dd>{has(sh.co2nm_vs_same_speed_pct) ? pct(sh.co2nm_vs_same_speed_pct) : "–"}</dd></div>
              <div><dt>저속 운항</dt><dd>{sh.slow_steaming ? "해당" : "해당 없음"}</dd></div>
            </dl>
          </>
        )}
      </Card>
    </div>
  );
}
