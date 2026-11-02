---
service: card-auth
updated_at: 2025-10-14
---
# Card auth: memory pressure and OOM kills

Alert: `CardAuthMemoryPressure` fires when container memory, `card_auth_rss_pct_of_limit`, stays above its threshold for 10 minutes or a pod is OOM-killed. Card auth is a
core-tier service owned by the payments team; it calls
redis-cache, and
payments call it.

## Symptoms

- Pods restart with reason OOMKilled.
- Memory climbs steadily between restarts: a sawtooth.
- Latency spikes right before each restart.

## Likely causes

- **Large payloads.** A few very large requests allocate far more than usual.
- **Memory leak in a recent release.** A new code path keeps references to finished requests.
- **Unbounded cache.** An in-process cache without a size limit grows with traffic.

The most common cause on card-auth is large payloads: it explained 9 of the
last 15 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `card-auth-overview` dashboard and compare `card_auth_rss_pct_of_limit` with the
   same hour last week.
2. Check recent changes: `deployctl history card-auth --since 2h`. A deploy in the last hour makes
   "large payloads" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/card-auth --since 15m | grep CAR-MEM-246
   ```

4. If `card_auth_rss_pct_of_limit` stays above 84 for 8 minutes, treat it as
   memory pressure and OOM kills and move to mitigation; below that it usually recovers on its own.
5. Compare memory growth rate before and after the last deploy.

## Mitigation

1. Raise the memory limit by 25% as a stopgap: `kubectl -n platform set resources deploy/card-auth`.
2. Restart pods in a rolling fashion to buy time.
3. If that doesn't help within 10 minutes, set `max_request_body_kb=58` on
   card-auth (`configctl set card-auth max_request_body_kb 58`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 45 minutes without improvement, or at once if more than
25% of card-auth requests are failing. Coordinate in `#payments-oncall`.
