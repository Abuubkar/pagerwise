import createClient from "openapi-fetch";
import type { components, paths } from "@/api/schema";

// The REST client, typed from contracts/openapi.yaml (src/api/schema.d.ts is generated: `pnpm codegen`).
export const makeApi = (baseUrl = "") => createClient<paths>({ baseUrl });

type Schemas = components["schemas"];
export type Citation = Schemas["CitationEvent"];
export type DegradedSource = Schemas["DegradedSourceEvent"];
export type TriageBrief = Schemas["TriageBrief"];
export type ErrorEvent = Schemas["ErrorEvent"];
