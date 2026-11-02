---
service: inventory
updated_at: 2026-03-09
incident_date: 2026-03-01
---
# Postmortem: inventory memory pressure and OOM kills (2026-03-01)

## Summary

On 2026-03-01, inventory kept restarting for 37 minutes. The cause was in inventory.
The incident was sev1 and was opened by `InventoryMemoryPressure`.

## Impact

- 43% of inventory requests failed or timed out at the peak.
- Callers affected: orders, search.
- 898 customers saw errors; 87 support tickets were opened.

## Timeline

All times UTC.

- **19:33** inventory 3.33.16 deployed by Lauren Bryant.
- **20:07** `InventoryMemoryPressure` fired; on-call acknowledged.
- **20:11** Checked the inventory runbook for memory pressure and OOM kills.
- **20:17** Found the cause in inventory.
- **20:38** Mitigation applied; error rate falling.
- **20:44** Recovered; incident resolved.

## Root cause

A cache added in 3.33.16 of inventory had no eviction, growing to 885 MB per pod.

Category: memory pressure and OOM kills. Component: inventory.

## Contributing factors

- The memory pressure and OOM kills alert for inventory had no runbook link.
- A recent reorg left the alert routed to the wrong team.

## Action items

- INVE-4903 (discovery): Add an alert on rss_pct_of_limit for inventory.
- INVE-5512 (discovery): Add a regression test for: a cache added in 3.33.16 of inventory had no eviction, growing to 885 mb per pod.
- INVE-1538 (discovery): Link the runbook from the alert.
