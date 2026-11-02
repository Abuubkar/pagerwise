---
service: redis-cache
updated_at: 2026-03-09
incident_date: 2026-03-06
---
# Postmortem: redis-cache regression after a deploy (2026-03-06)

## Summary

On 2026-03-06, redis-cache broke after a deploy for 93 minutes. The cause was in redis-cache.
The incident was sev2 and was opened by `RedisCachePostDeployErrors`.

## Impact

- 46% of redis-cache requests failed or timed out at the peak.
- Callers affected: auth, card-auth, search.
- 22,582 customers saw errors; 105 support tickets were opened.

## Timeline

All times UTC.

- **15:33** redis-cache 6.33.2 deployed by Emily Dominguez.
- **15:49** `RedisCachePostDeployErrors` fired; on-call acknowledged.
- **15:58** Checked the redis-cache runbook for regression after a deploy.
- **16:28** Found the cause in redis-cache.
- **16:35** Mitigation applied; error rate falling.
- **17:22** Recovered; incident resolved.

## Root cause

6.33.2 of redis-cache renamed a config key, so production fell back to a default of 1410.

Category: regression after a deploy. Component: redis-cache.

## Contributing factors

- The regression after a deploy alert for redis-cache had no runbook link.
- Logs were sampled at 1%, so the first errors weren't visible.

## Action items

- REDI-9586 (platform): Add an alert on post_deploy_error_pct for redis-cache.
- REDI-9382 (platform): Add a regression test for: 6.33.2 of redis-cache renamed a config key, so production fell back to a default of 1410.
- REDI-9272 (platform): Link the runbook from the alert.
