# Problem codes

Every error response is an RFC 9457 problem (`application/problem+json`) with a stable `code`. The triage
stream's `error` event uses the same codes.

| code | status | meaning |
|---|---|---|
| <a id="invalid_request"></a>`invalid_request` | 400 | The body or a parameter failed validation; `detail` says which. |
| <a id="invalid_cursor"></a>`invalid_cursor` | 400 | The `after` cursor was edited, signed with another secret, or issued for different filters. Start from the first page. |
| <a id="not_found"></a>`not_found` | 404 | No such incident, or the incident has no triage to stream yet. |
| <a id="triage_in_progress"></a>`triage_in_progress` | 409 | A triage of this incident version is already queued or running; `triage_id` is that run. Open its stream instead. |
| <a id="model_unavailable"></a>`model_unavailable` | 503 / stream | Ollama isn't reachable. |
| <a id="prompt_too_long"></a>`prompt_too_long` | 422 / stream | The prompt wouldn't fit `num_ctx`; it was not sent, because Ollama would truncate it silently. |
| <a id="format_invalid"></a>`format_invalid` | stream | The brief broke the section or citation contract; `problems` lists how. |
| <a id="triage_abandoned"></a>`triage_abandoned` | stream | The triage stopped renewing its heartbeat (its process died or its client left) and was given up. |
