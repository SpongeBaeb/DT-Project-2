import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// /api    → 팀 모델 진단 API (로컬, python -m uvicorn api.main:app --port 8000)
// /shared → 팀 공용 백엔드 (BACKEND_URL, .env.local). 시장 가격·군집 상세·초기 모델 진단
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const shared = env.BACKEND_URL || "https://project2-backend-8zqr.onrender.com";
  const proxy = {
    "/api": { target: env.API_URL || "http://127.0.0.1:8000", changeOrigin: true, rewrite: (p: string) => p.replace(/^\/api/, "") },
    "/shared": { target: shared, changeOrigin: true, rewrite: (p: string) => p.replace(/^\/shared/, "") },
  };
  return { plugins: [react()], server: { port: 5192, open: true, proxy }, preview: { port: 5192, proxy } };
});
