import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// The API is same-origin through this proxy in dev, and through a Vercel rewrite in
// production. That is what keeps the session cookie first-party, so never call the
// backend origin directly from the browser.
const apiTarget = process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    // Bind every interface, not just the IPv6 loopback. On Windows `localhost`
    // resolves to ::1 first, so a default bind leaves http://127.0.0.1:5173
    // refusing connections, which also breaks the /api proxy target.
    host: true,
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: false },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});