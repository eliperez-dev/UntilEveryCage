# V2 API contract

The machine-readable contract is [v2-contract.json](v2-contract.json). Successful list/detail response shapes remain unchanged. Errors use one additive, stable envelope:

```json
{"api_version":"v2","error":{"code":"invalid_profile","message":"profile is unsupported"}}
```

Frontend clients should branch on HTTP status and `error.code`, display `message` only as user-safe text, and treat unknown codes as generic failures. A list request with no promoted eligible release is a successful empty response; an unavailable database is `503`; an absent or suppressed detail is `404`; rate limiting is `429` with `Retry-After`.
