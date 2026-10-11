import { useEffect, useMemo, useState } from "react";
import { data } from "../api/client";
import type { IndexEntry } from "../api/types";

const CLASS_LABEL: Record<string, string> = {
  consistently_high: "동급보다 꾸준히 높음",
  typical: "보통",
  consistently_low: "동급보다 꾸준히 낮음",
};

export default function Search() {
  const [rows, setRows] = useState<IndexEntry[]>([]);
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [onlyClean, setOnlyClean] = useState(false);
  const [onlyHigh, setOnlyHigh] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    data.index().then(setRows).catch((e) => setErr(String(e)));
  }, []);

  const types = useMemo(() => [...new Set(rows.map((r) => r.ship_type))].sort(), [rows]);
  const query = q.trim().toLowerCase();
  const byText = rows.filter(
    (r) =>
      (!type || r.ship_type === type) &&
      (!query || String(r.imo).includes(query) || (r.name ?? "").toLowerCase().includes(query) ||
        r.former_names.some((n) => n.toLowerCase().includes(query))),
  );
  const clean = byText.filter((r) => !r.sig_any);
  const high = clean.filter((r) => r.position_class === "consistently_high");
  const shown = onlyHigh ? high : onlyClean ? clean : byText;

  if (err) return <p className="error">{err}</p>;
  return (
    <section>
      <h1>선박 찾기</h1>
      <div className="filters">
        <input placeholder="이름·옛 이름·IMO" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">모든 선종</option>
          {types.map((t) => <option key={t}>{t}</option>)}
        </select>
        <label><input type="checkbox" checked={onlyClean} onChange={(e) => setOnlyClean(e.target.checked)} /> 착시 신호 없음</label>
        <label><input type="checkbox" checked={onlyHigh} onChange={(e) => setOnlyHigh(e.target.checked)} /> 꾸준히 높음만</label>
      </div>
      <p className="funnel">
        전체 <b>{byText.length}</b> → 착시 신호 없음 <b>{clean.length}</b> → 동급보다 꾸준히 높음 <b>{high.length}</b>
      </p>
      <table>
        <thead>
          <tr><th>IMO</th><th>이름</th><th>선종</th><th>재화중량</th><th>최근 연도</th><th>동급 대비</th><th>위치</th><th>신호</th></tr>
        </thead>
        <tbody>
          {shown.slice(0, 200).map((r) => (
            <tr key={r.imo} onClick={() => (window.location.hash = `#/ship/${r.imo}`)} className="clickable">
              <td>{r.imo}</td>
              <td>{r.name}{r.former_names.length > 0 && <span className="muted small"> (옛 {r.former_names.join(", ")})</span>}</td>
              <td>{r.ship_type}</td>
              <td className="num">{r.dwt.toLocaleString()}</td>
              <td className="num">{r.last_year}</td>
              <td className={`num ${r.vs_peer_pct > 0 ? "worse" : "better"}`}>{r.vs_peer_pct > 0 ? "+" : ""}{r.vs_peer_pct.toFixed(1)}%</td>
              <td>{CLASS_LABEL[r.position_class] ?? r.position_class}</td>
              <td>{r.sig_any ? "⚠" : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {shown.length > 200 && <p className="muted small">앞 200척만 표시</p>}
    </section>
  );
}
