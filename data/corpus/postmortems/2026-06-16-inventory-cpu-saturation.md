---
service: inventory
updated_at: 2026-06-20
incident_date: 2026-06-16
---
# Postmortem: inventory CPU saturation (2026-06-16)

## Summary

On 2026-06-16, inventory was saturated for 175 minutes. The cause was in postgres-primary.
The incident was sev2 and was opened by `InventoryCPUSaturated`.

## Impact

- 17% of inventory requests failed or timed out at the peak.
- Callers affected: orders, search.
- 12,273 customers saw errors; 72 support tickets were opened.

## Timeline

All times UTC.

- **00:29** postgres-primary 1.33.11 deployed by Melissa Sanchez.
- **01:04** `InventoryCPUSaturated` fired; on-call acknowledged.
- **01:07** Checked the inventory runbook for CPU saturation.
- **01:27** Found the cause in postgres-primary.
- **02:48** Mitigation applied; error rate falling.
- **03:59** Recovered; incident resolved.

## Root cause

postgres-primary recomputed a full price table per request after a cache key change in 1.33.11.

Category: CPU saturation. Component: postgres-primary.

## Contributing factors

- The CPU saturation alert for postgres-primary had no runbook link.
- A recent reorg left the alert routed to the wrong team.

## Action items

- INVE-3678 (platform): Add an alert on cpu_util_pct for postgres-primary.
- INVE-1076 (platform): Add a regression test for: postgres-primary recomputed a full price table per request after a cache key change in 1.33.11.
- INVE-9516 (platform): Link the runbook from the alert.
