import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// eslint-disable-next-line no-restricted-exports
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": "/src",
    },
  },
  server: {
    port: 3200,
    // 로컬 `npm run dev` 실행 시 백엔드로 프록시. Docker 안에서는 nginx.conf가 대신 이 역할을 함.
    proxy: {
      "/api": {
        target: "http://localhost:13000",
        changeOrigin: true,
      },
    },
  },
});
