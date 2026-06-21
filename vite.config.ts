import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Frontend dev server proxies API calls to the FastAPI backend
// (uvicorn app.main:app --reload, default :8000) so the SPA can call /health,
// /api/* without CORS during development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/health": "http://127.0.0.1:8000",
      "/api": "http://127.0.0.1:8000",
    },
  },
});
