# Private candidate preview

The candidate preview is a development-only operator surface at
`GET /api/dev/preview/candidates`. It is not a V2 profile and never reads the
public promoted-release routes.

The server starts the preview only when all of these are true:

- `UEC_RUNTIME_MODE=development`;
- `UEC_DEV_PREVIEW=true`;
- `UEC_BIND_HOST` is exactly `127.0.0.1` or `::1`;
- `UEC_DEV_PREVIEW_TOKEN` is supplied as a non-empty process secret; and
- configured CORS origins are loopback-only.

Every request must send the token in the `X-UEC-Dev-Preview-Token` header.
Never place it in a URL, source file, browser bundle, or log. Production mode,
non-loopback binding, missing authentication, remote CORS, and ambiguous
configuration fail closed. A local dev proxy may hold the token server-side;
browser clients may hold it only in memory for the current session.

Preview responses contain only privacy-screened, non-withheld candidate fields
and source/retrieval metadata. Exact coordinates require a separate explicit
`coordinate_review_status=approved` decision; an accepted geocoder result alone
is not permission to expose a point. They omit raw payloads, addresses, and geocoder
queries. Every row is labeled `Private development candidate — not
project-approved or published`; `project_approval` remains `false` and the
release remains `candidate`. Candidate seed/reset/rebuild belongs to a
disposable E2E database only. This path is not production deployment or
publication authorization.
