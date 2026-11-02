import type { CodegenConfig } from "@graphql-codegen/cli";

// Typed GraphQL documents from the contract (contracts/schema.graphql, itself generated from the API). Run
// `pnpm codegen` (or `make codegen` at the repo root) after changing a query or the schema; src/gql is generated.
// The REST/SSE types come from contracts/openapi.yaml via openapi-typescript (src/api/schema.d.ts, also generated).
const config: CodegenConfig = {
  schema: "../../contracts/schema.graphql",
  documents: ["src/**/*.{ts,tsx}", "!src/gql/**/*"],
  ignoreNoDocuments: false,
  generates: {
    "./src/gql/": {
      preset: "client",
      presetConfig: { fragmentMasking: false },
      config: { useTypeImports: true, scalars: { UUID: "string", DateTime: "string", JSON: "any" } },
    },
  },
};

export default config;
