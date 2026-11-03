import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  // eslint-config-next's default ignores, plus the generated clients (make codegen).
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "src/gql/**", "src/api/schema.d.ts"]),
]);
