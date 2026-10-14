// 선박 현재 위치 지도 (AIS 수신값, aisstream.io). 서버가 모아 둔 값을 /api/ais/{imo} 로 받는다.
import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { aisOf, type AisPosition } from "../api";

const POLL_MS = { wait: 12_000, ok: 60_000 };

export function ago(sec: number): string {
  if (sec < 90) return "방금 전";
  if (sec < 3600) return `${Math.round(sec / 60)}분 전`;
  if (sec < 86400) return `${Math.round(sec / 3600)}시간 전`;
  return `${Math.round(sec / 86400)}일 전`;
}

const EMPTY: Record<string, string> = {
  waiting: "AIS 신호를 기다리는 중입니다. 선박은 약 6분마다 정보를 보내므로 몇 분 걸릴 수 있습니다.",
  no_position: "선박은 확인됐지만 위치 신호가 아직 들어오지 않았습니다.",
  no_key: "AIS 키가 설정되지 않아 위치를 표시할 수 없습니다.",
  error: "위치 서버에 연결할 수 없습니다. 모델 서버(8000)가 켜져 있는지 확인하세요.",
};

function icon(p: AisPosition) {
  const moving = (p.sog ?? 0) >= 0.5;
  const rot = p.heading ?? p.cog ?? 0;
  const cls = p.status === "stale" ? "smap-m stale" : "smap-m";
  const html = moving
    ? `<svg viewBox="0 0 24 24" style="transform:rotate(${rot}deg)"><path d="M12 2 19 21l-7-4-7 4z" /></svg>`
    : `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="6" /></svg>`;
  return L.divIcon({ className: cls, html, iconSize: [30, 30], iconAnchor: [15, 15] });
}

export default function ShipMap({ imo, name }: { imo: number; name: string }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const marker = useRef<L.Marker | null>(null);
  const fitted = useRef(false);
  const [pos, setPos] = useState<AisPosition | null>(null);
  const [err, setErr] = useState(false);
  const [, tick] = useState(0);

  useEffect(() => {
    if (!el.current) return;
    const m = L.map(el.current, { zoomControl: true, attributionControl: true, worldCopyJump: true, minZoom: 1 }).setView([20, 20], 1);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 12, attribution: "© OpenStreetMap" }).addTo(m);
    map.current = m;
    const ro = new ResizeObserver(() => m.invalidateSize());
    ro.observe(el.current);
    return () => { ro.disconnect(); m.remove(); map.current = null; marker.current = null; fitted.current = false; };
  }, []);

  useEffect(() => {
    let alive = true, t: number;
    setPos(null); setErr(false); fitted.current = false;
    const load = async () => {
      let next = POLL_MS.wait;
      try {
        const p = await aisOf(imo);
        if (!alive) return;
        setPos(p); setErr(false);
        if (p.status === "ok" || p.status === "stale") next = POLL_MS.ok;
        if (p.status === "no_key") return;
      } catch {
        if (!alive) return;
        setErr(true);
      }
      t = window.setTimeout(load, next);
    };
    load();
    const clock = window.setInterval(() => tick((x) => x + 1), 30_000);
    return () => { alive = false; window.clearTimeout(t); window.clearInterval(clock); };
  }, [imo]);

  useEffect(() => {
    const m = map.current;
    if (!m || !pos || pos.lat === undefined || pos.lon === undefined) return;
    const ll: L.LatLngExpression = [pos.lat, pos.lon];
    if (marker.current) marker.current.setLatLng(ll).setIcon(icon(pos));
    else marker.current = L.marker(ll, { icon: icon(pos), keyboard: false, title: name }).addTo(m);
    if (!fitted.current) { m.setView(ll, 6, { animate: false }); fitted.current = true; }
  }, [pos, name]);

  const has = pos && (pos.status === "ok" || pos.status === "stale");
  const emptyKey = err ? "error" : pos && !has ? pos.status : "waiting";
  const age = pos?.received_at ? Math.max(0, Date.now() / 1000 - pos.received_at) : pos?.age_s;
  const eta = pos?.eta ? `${pos.eta.Month}월 ${pos.eta.Day}일 ${String(pos.eta.Hour ?? 0).padStart(2, "0")}:${String(pos.eta.Minute ?? 0).padStart(2, "0")} (UTC)` : null;
  return (
    <figure className="smap" aria-label={`${name} 현재 위치`}>
      <div className="smap-map" ref={el} />
      {!has && <div className="smap-empty" role="status"><span className={emptyKey === "waiting" || emptyKey === "no_position" ? "dot" : ""} />{EMPTY[emptyKey] ?? EMPTY.waiting}</div>}
      <figcaption>
        {has && pos ? (
          <>
            <b>{pos.status === "stale" ? "마지막 수신 위치" : "현재 위치"}</b>
            <span>{age !== undefined ? ago(age) : ""} 수신{pos.status === "stale" ? " · 오래된 값" : ""}</span>
            <dl>
              <div><dt>속력</dt><dd>{pos.sog !== null && pos.sog !== undefined ? `${pos.sog.toFixed(1)} 노트` : "–"}</dd></div>
              <div><dt>상태</dt><dd>{pos.nav_status ?? "–"}</dd></div>
              <div><dt>목적지</dt><dd>{pos.destination ?? "–"}</dd></div>
              {eta && <div><dt>도착 예정</dt><dd>{eta}</dd></div>}
            </dl>
          </>
        ) : (
          <span>선박자동식별장치(AIS) 실시간 수신</span>
        )}
        <small>AIS: aisstream.io · 지도: OpenStreetMap</small>
      </figcaption>
    </figure>
  );
}
