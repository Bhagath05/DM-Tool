import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

/**
 * Vitest config — mirrors Next.js's tsconfig path alias so `@/` imports
 * resolve in tests the same way they do in `next build`.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
    css: false,
    include: ["src/**/*.test.{ts,tsx}"],

    /**
     * Bump test timeout from the 5s default. A handful of component
     * tests render React-Testing-Library trees that take 5-6s under
     * load — failing them on a busy machine isn't a real signal.
     * (Vitest 4 reworked poolOptions placement; the bumped timeout
     * alone is enough to absorb the flakes we hit in Phase 10.4.)
     */
    testTimeout: 15_000,
  },
});
