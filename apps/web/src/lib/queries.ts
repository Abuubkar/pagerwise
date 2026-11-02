import { graphql } from "@/gql";

// Every GraphQL document the UI sends. Types come from contracts/schema.graphql via `pnpm codegen` (src/gql).
export const IncidentsQuery = graphql(`
  query Incidents($first: Int!, $after: String) {
    incidents(first: $first, after: $after) {
      edges { cursor node { id title service severity status openedAt lastAlertAt alertCount version } }
      pageInfo { hasNextPage endCursor }
    }
  }
`);

export const IncidentUpdatedSubscription = graphql(`
  subscription IncidentUpdated {
    incidentUpdated { id title service severity status openedAt lastAlertAt alertCount version }
  }
`);

export const IncidentQuery = graphql(`
  query Incident($id: UUID!) {
    incident(id: $id) {
      id title service severity status summary openedAt lastAlertAt alertCount version
      alerts(first: 20) { service alertname instance fingerprint count firstAt lastAt }
      triage { id status verdict incidentVersion degradedSources createdAt finishedAt }
    }
  }
`);

export const AcknowledgeMutation = graphql(`
  mutation Acknowledge($id: UUID!, $expectedVersion: Int!) {
    acknowledgeIncident(id: $id, expectedVersion: $expectedVersion) {
      __typename
      ... on Incident { id status version }
      ... on VersionConflict { expectedVersion currentVersion }
    }
  }
`);
