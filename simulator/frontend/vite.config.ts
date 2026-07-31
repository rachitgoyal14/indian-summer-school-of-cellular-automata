import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend WebSocket server runs on :8000; the dev server proxies /ws to it
// so the frontend can use a same-origin ws:// URL in development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
    },
  },
});
