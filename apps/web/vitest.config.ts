import path from "node:path";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      $lib: path.resolve(__dirname, "src/lib"),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["src/**/*.ts"],
      exclude: [
        "src/**/*.test.ts",
        "src/lib/server/db/auth.schema.ts",
        // Database-backed routes are covered by integration tests.
        "src/lib/server/db/index.ts",
        "src/hooks.server.ts",
        "src/lib/server/simulation-repository.ts",
      ],
    },
  },
});
