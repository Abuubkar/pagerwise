---
service: card-auth
updated_at: 2026-03-30
---
# Card auth: CPU saturation

Alert: `CardAuthCPUSaturated` fires when CPU utilisation, `card_auth_cpu_util_pct`, stays above its threshold for 10 minutes. Card auth is a
core-tier service owned by the payments team; it calls
redis-cache, and
payments call it.

## Symptoms

- CPU throttling counters rise.
- Latency rises with load in a straight line.
- Autoscaler is at its maximum replica count.

## Likely causes

- **Traffic spike.** Legitimate load above what the current replica count serves.
- **Hot loop in a release.** A recent change made a common path far more expensive.
- **Noisy neighbour.** Another workload on the same nodes takes CPU.

The most common cause on card-auth is traffic spike: it explained 13 of the
last 18 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `card-auth-overview` dashboard and compare `card_auth_cpu_util_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history card-auth --since 2h`. A deploy in the last hour makes
   "traffic spike" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/card-auth --since 15m | grep CAR-CPU-265
   ```

4. If `card_auth_cpu_util_pct` stays above 80 for 6 minutes, treat it as
   CPU saturation and move to mitigation; below that it usually recovers on its own.
5. Check whether request rate rose too; if not, look for an expensive code path.

## Mitigation

1. Raise the autoscaler maximum by 50%.
2. Enable the cached response mode if the service has one.
3. If that doesn't help within 10 minutes, set `cache_ttl_s=29` on
   card-auth (`configctl set card-auth cache_ttl_s 29`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 30 minutes without improvement, or at once if more than
20% of card-auth requests are failing. Coordinate in `#payments-oncall`.
