---
service: payments
updated_at: 2026-08-18
---
# Payments: CPU saturation

Alert: `PaymentsCPUSaturated` fires when CPU utilisation, `payments_cpu_util_pct`, stays above its threshold for 10 minutes. Payments is a
core-tier service owned by the payments team; it calls
card-auth, ledger, kafka-broker, and
api-gateway, orders call it.

## Symptoms

- CPU throttling counters rise.
- Latency rises with load in a straight line.
- Autoscaler is at its maximum replica count.

## Likely causes

- **Noisy neighbour.** Another workload on the same nodes takes CPU.
- **Hot loop in a release.** A recent change made a common path far more expensive.
- **Traffic spike.** Legitimate load above what the current replica count serves.

The most common cause on payments is noisy neighbour: it explained 24 of the
last 28 pages for this alert.

## Diagnosis

1. Confirm the alert is real: open the `payments-overview` dashboard and compare `payments_cpu_util_pct` with the
   same hour last week.
2. Check recent changes: `deployctl history payments --since 2h`. A deploy in the last hour makes
   "noisy neighbour" less likely than a regression.
3. Search the logs for the error code this failure logs:

   ```bash
   kubectl -n payments logs deploy/payments --since 15m | grep PAY-CPU-274
   ```

4. If `payments_cpu_util_pct` stays above 77 for 5 minutes, treat it as
   CPU saturation and move to mitigation; below that it usually recovers on its own.
5. Check whether request rate rose too; if not, look for an expensive code path.

## Mitigation

1. Raise the autoscaler maximum by 50%.
2. Enable the cached response mode if the service has one.
3. If that doesn't help within 10 minutes, set `autoscale_max_replicas=3` on
   payments (`configctl set payments autoscale_max_replicas 3`) and restart one pod at a
   time.

## Escalation

Page the payments secondary after 45 minutes without improvement, or at once if more than
20% of payments requests are failing. Coordinate in `#payments-oncall`.
