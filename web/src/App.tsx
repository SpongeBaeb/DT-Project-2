/**
 * 화면 뼈대 [담당: 장원우]. 주소(#)로 화면을 고른다: #/ 찾기 · #/ship/<imo> 진단 · #/my 내 선박 진단
 * 라우터 라이브러리 없이 시작 — 화면이 늘면 react-router 로 바꿔도 된다.
 */
import { useEffect, useState } from "react";
import { data } from "./api/client";
import type { Meta } from "./api/types";
import MyShip from "./pages/MyShip";
import Search from "./pages/Search";
import ShipPage from "./pages/ShipPage";

function useHash() {
  const [hash, setHash] = useState(window.location.hash || "#/");
  useEffect(() => {
    const on = () => setHash(window.location.hash || "#/");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}

export default function App() {
  const hash = useHash();
  const [meta, setMeta] = useState<Meta | null>(null);
  useEffect(() => {
    data.meta().then(setMeta).catch(() => setMeta(null));
  }, []);

  const ship = hash.match(/^#\/ship\/(\d+)/);
  return (
    <div className="app">
      <header>
        <a href="#/" className="brand">Sea Marksman</a>
        <nav>
          <a href="#/">선박 찾기</a>
          <a href="#/my">내 선박 진단</a>
        </nav>
        <span className="muted small">{meta ? `모델 ${meta.model_version} · 데이터 ${meta.data_hash}` : "데이터 없음: python tasks.py build"}</span>
      </header>
      <main>
        {ship ? <ShipPage imo={Number(ship[1])} /> : hash.startsWith("#/my") ? <MyShip meta={meta} /> : <Search />}
      </main>
    </div>
  );
}
