import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // The hook owns a WebSocket and React state, so it needs a DOM to live in.
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
