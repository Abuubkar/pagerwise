---
service: payments
---
# Payments: high p99 latency

Alert: `PaymentsP99LatencyHigh` fires when the p99 of `POST /v1/charges` stays above 800 ms for 5 minutes.
The normal p99 is 180–250 ms. Customers notice at about 1.5 s, when the mobile checkout starts showing a spinner
and retry button.

## Symptoms

- p99 rises first; p50 usually stays under 120 ms until the problem gets worse.
- `payments_ledger_call_seconds` (the time payments waits on the ledger service) accounts for most of the increase.
- Error rate is normally flat at first. Errors only start once requests hit the 5 s client timeout.

## Likely causes

### Ledger connection pool running low

Payments p99 rises when the ledger connection pool drops below 20 idle connections. Every charge writes a ledger
entry synchronously, so when ledger pods are waiting for database connections, payments waits with them. This is
the cause in roughly 70% of past pages for this alert.

Check the ledger pool from any ledger pod:

```bash
kubectl -n ledger exec deploy/ledger -- ledgerctl pool stats
# idle=14 in_use=26 waiting=9 max=40
```

If `idle` is under 20 and `waiting` is above 0, follow the ledger runbook "Ledger: connection pool exhaustion".

### Card network slowness

If `payments_ledger_call_seconds` is normal but `payments_acquirer_call_seconds` is high, the card network is slow.
See "Payments: card authorization timeouts".

### A recent payments deploy

Payments deploys roll out 25% of pods at a time. A bad build shows up as latency on only part of the pods; compare
p99 per pod in the "Payments / Overview" dashboard.

## First steps

1. Open the "Payments / Overview" dashboard and check which downstream call grew: ledger or acquirer.
2. If it is the ledger, run `ledgerctl pool stats` as above.
3. If only some pods are slow and a deploy went out in the last hour, roll back:

```bash
kubectl -n payments rollout undo deploy/payments
```

4. Do not scale payments up to fix ledger slowness. More payments pods open more ledger requests and make the pool
   shortage worse.

## Escalation

Page the ledger on-call if the ledger pool is the cause and has not recovered within 15 minutes.
