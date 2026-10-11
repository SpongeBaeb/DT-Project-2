import { useEffect, useState } from "react";
import { data } from "../api/client";
import type { ShipFile } from "../api/types";
import DiagnosisView from "../components/DiagnosisView";

export default function ShipPage({ imo }: { imo: number }) {
  const [ship, setShip] = useState<ShipFile | null>(null);
  const [year, setYear] = useState<number | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    setShip(null);
    data.ship(imo).then((s) => { setShip(s); setYear(s.results.at(-1)!.year); }).catch((e) => setErr(String(e)));
  }, [imo]);

  if (err) return <p className="error">{err}</p>;
  if (!ship || year == null) return <p>불러오는 중…</p>;
  const idx = ship.results.findIndex((r) => r.year === year);
  const result = ship.results[idx];
  const input = ship.inputs.years.find((y) => y.year === year);
  const last = ship.inputs.ship;

  return (
    <section>
      <h1>{ship.name} <span className="muted small">IMO {ship.imo}</span></h1>
      <p className="muted">
        {ship.ship_type} · {last.dwt.toLocaleString()} DWT · {last.build_year}년 건조{ship.company ? ` · ${ship.company}` : ""}
        {ship.former_names.length > 0 && ` · 옛 이름 ${ship.former_names.join(", ")}`}
      </p>
      <div className="years">
        {ship.results.map((r) => (
          <button key={r.year} className={r.year === year ? "active" : ""} onClick={() => setYear(r.year)}>{r.year}</button>
        ))}
        <a className="button" href={`#/my?imo=${ship.imo}`}>이 배로 가정 바꿔 보기</a>
      </div>
      <DiagnosisView result={result} history={ship.results.slice(0, idx + 1)} input={input} />
    </section>
  );
}
