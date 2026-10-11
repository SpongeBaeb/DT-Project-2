import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// 개발 서버: http://localhost:5173  ·  /api/* 는 진단 API(127.0.0.1:8000)로 넘김
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", rewrite: (p) => p.replace(/^\/api/, "") } },
  },
  test: { environment: "node" },
});
