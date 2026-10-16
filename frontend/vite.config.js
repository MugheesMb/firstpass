import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, /api is proxied to the local FastAPI server.
// In production, Firebase Hosting rewrites /api/** to the Cloud Run service (see firebase.json).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8080" } },
});
