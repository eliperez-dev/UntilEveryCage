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

## Local real-preview protocol

For local map testing of a prepared real candidate release, the more specific
`/api/dev/preview/test-release/*` routes may be enabled only on the developer
machine. They require all candidate-preview conditions above plus a non-empty
`UEC_TEST_RELEASE_ID` and `UEC_TEST_RELEASE_TOKEN`. The selected release must
already be a disposable candidate with existing privacy, restriction, and
coordinate-review decisions; enabling the route does not import, promote, or
approve a release.

The approved local rehearsal corpus is the bounded 50,750-row legacy V1
snapshot (48,703 mapped; 2,047 unmapped). It is labeled
legacy/development-only/not-V2-reviewed, is never promoted, and is read with
viewport-bounded queries; it must not be copied into a browser bundle or
rendered as one DOM marker per row.

With the one-command launchpad, set `UEC_LOCAL_REAL_PREVIEW=true` and all four
of `UEC_DEV_PREVIEW=true`, `UEC_DEV_PREVIEW_TOKEN`, `UEC_TEST_RELEASE_ID`, and
`UEC_TEST_RELEASE_TOKEN` in the current process environment. The launchpad
passes only that allowlist to the loopback API and deliberately removes it from
the Vite process. It prints neither token values nor rows. An incomplete,
ambiguous, or disabled configuration fails closed.

Keep tokens in memory and send them only in the
`X-UEC-Dev-Preview-Token` request header. Never put them in URLs, source,
`.env` files, browser storage, exports, screenshots, or logs. The route has no
remote/tunnel mode and must not drive analytics, downloads, or public
`/api/v2/*` content. The standard frontend dataset remains synthetic and all
row-free artifact rules remain in effect. On completion, stop the local stack
and clear the environment values; candidate/release deletion is not a remedy
for any copied data, cache, or log.
