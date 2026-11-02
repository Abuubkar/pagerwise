---
service: payments
---
# Payments: card authorization timeouts

Alert: `PaymentsAcquirerTimeouts` fires when more than 2% of card authorizations time out over 10 minutes.

## How authorization works

Payments sends each authorization to the acquirer (our card processor) over HTTPS. The acquirer timeout is 4
seconds. A timed-out authorization is retried once, with the same idempotency key, after 500 ms. The second
attempt is the last; after it the charge fails with `acquirer_timeout` and the customer is asked to try again.

Because the idempotency key is reused, a retry never charges a card twice even if the first attempt actually went
through at the acquirer.

## The circuit breaker

The acquirer client has a circuit breaker. It opens after 50 failed authorizations within 30 seconds and stays open
for 60 seconds. While it is open, payments fails new card charges immediately with `acquirer_unavailable` instead
of waiting 4 seconds each. Wallet payments (Apple Pay, Google Pay) go through a different acquirer connection and
are not affected by this breaker.

Check the breaker state:

```bash
kubectl -n payments exec deploy/payments -- paymentsctl breaker status
# acquirer-cards: OPEN (opened 34s ago, failures=61/30s)
```

## First steps

1. Check the acquirer status page linked from the "Payments / Acquirer" dashboard. Most timeout incidents are on
   the acquirer's side.
2. Confirm the timeouts come from the acquirer and not from us: `payments_acquirer_call_seconds` p99 should be near
   4 s, while `payments_ledger_call_seconds` stays normal.
3. Do not raise the acquirer timeout above 4 seconds. Our client timeout is 5 seconds, so a longer acquirer wait
   turns every slow authorization into a client error with an unknown outcome.
4. If the acquirer has declared an incident, post the status link in #incidents and switch the checkout banner on:

```bash
kubectl -n payments exec deploy/payments -- paymentsctl banner set card-delays
```

## Escalation

The acquirer's support line is in the vendor contacts page. Open a P1 with them when timeouts exceed 10% for more
than 5 minutes.
