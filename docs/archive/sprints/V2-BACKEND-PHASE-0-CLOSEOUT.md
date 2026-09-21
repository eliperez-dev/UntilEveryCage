# V2 Backend Phase 0 Closeout Evidence

Date: 2026-09-13

This document records the current evidence for the V2 backend foundation. It is a handoff and audit record, not authorization to publish V2 or a claim that outstanding policy/deployment controls are complete.

## Verified foundation

- Rust backend tests: 65 passed.
- Python pipeline unit tests: 57 passed, 3 expected skips in the canonical clean runner.
- Public API E2E: 5 passed in an isolated disposable PostGIS environment.
- Community API E2E: 5 passed in an isolated disposable PostGIS environment.
- Seeded API E2E: 12 passed in an isolated disposable PostGIS environment.
- Database migrations 001–020: applied successfully to clean PostGIS.
- Migration rerun: idempotent; the checksum ledger contained 20 migration rows after the second run.
- Backup/restore: passed; the promoted synthetic release survived and the suppressed source record remained absent from public projections.
- Formatting and `git diff --check`: passed.

## Backend capabilities now evidenced

- Promoted-release and profile-aware V2 list/detail API.
- Read-only `REPEATABLE READ` API transactions.
- Stable facility identifiers, deterministic cursor traversal, bounded pagination, and explicit filters.
- Separate source origin, factual review, privacy screening, project approval, publication profile, lifecycle, precision, and provenance fields.
- Append-only evidence and review history.
- Current suppression-aware V2 display history through migration 020.
- Candidate validation separated from explicit promotion.
- Failed candidate releases do not replace the promoted release.
- Disposable backup/restore verification.
- Checksum-tracked migration application.
- Production-mode PostgreSQL connections use Rustls with Mozilla root certificates; development mode remains explicitly local `NoTls`.

## Remaining release blockers

These do not invalidate the verified local/CI backend foundation, but they prevent claiming full public-production readiness:

1. Production PostgreSQL transport is now Rustls-backed, but deployment-level certificate/hostname verification and provider configuration still require a production environment check.
2. Exceptional removal, retention, and propagation workflows remain incomplete across every controlled surface, reimport, cache, historical release, and restore path.
3. The API contract for screened-but-unreviewed community claims is implemented and tested; frontend context, exports, separate aggregate views, and production exposure controls remain incomplete.
4. Authorized maintainer/reviewer availability, least-privilege release controls, publication-pause behavior, and legal-demand handling require operational ownership and evidence.
5. Visitor privacy, hosting/CDN/tile/geocoder/error-provider behavior, logging, and retention remain deployment-audit items.
6. Current source acquisition is complete only for the Denmark partial vertical slice; other source blockers remain recorded in the source registry.
7. The full multi-module E2E discovery command remains intentionally split into sequential modules because each module owns a disposable PostGIS environment; isolated sequential module runs are the authoritative passing evidence.
8. Jest runs in the canonical frontend compatibility gate; broader browser, accessibility, and mobile coverage remains part of frontend platform work.

## Handoff decision

The backend foundation is complete and certified for frontend contract work and integration. It is not yet authorized as the public production replacement for V1. The release blockers above remain linked to the [canonical product readiness roadmap](../../PRODUCT-READINESS.md) and the governing [ETHICS.md](../../ETHICS.md).
