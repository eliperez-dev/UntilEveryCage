import { z } from 'zod';

const textOrNull = z.string().nullable();
const dateTimeOrNull = z.string().datetime({ offset: true }).nullable();
const sourceUrl = z.string().url().refine(value => {
  try {
    return ['http:', 'https:'].includes(new URL(value).protocol);
  } catch {
    return false;
  }
}, 'source URL must use HTTP or HTTPS');

// This is the Rust-shaped public projection. Keep this list closed: fields
// that are not present in the current API belong in the convergence gap ledger
// and must not be invented in a frontend DTO.
const locationShape = {
  facility_id: z.string().uuid(),
  canonical_name: z.string().nullable(),
  country_code: z.string().regex(/^[A-Z]{2}$/),
  city: textOrNull,
  category: z.string(),
  publication_profile: z.enum(['official', 'secondary', 'community']),
  factual_review_status: z.string(),
  privacy_screening_status: z.literal('passed'),
  project_approval: z.string(),
  reviewer_role: textOrNull,
  publication_warning: textOrNull,
  display_precision: z.enum(['exact', 'city', 'unmapped']),
  latitude: z.number().finite().nullable(),
  longitude: z.number().finite().nullable(),
  first_observed_at: dateTimeOrNull,
  last_observed_at: dateTimeOrNull,
  observation_count: z.number().int().nonnegative().nullable(),
  lifecycle_status: z.enum(['active_observed', 'explicitly_closed', 'not_seen_recently', 'status_unknown']),
  source_type: z.enum(['official', 'secondary', 'user_submitted']),
  source_rights_status: z.string(),
  provenance_source: textOrNull,
  release_id: z.string(),
  release_ruleset_version: z.string(),
  provenance_source_id: z.string(),
  provenance_source_name: z.string(),
  provenance_source_url: sourceUrl,
  provenance_retrieved_at: z.string().datetime({ offset: true }),
};

const coordinateRules = (row: { latitude: number | null; longitude: number | null; display_precision: string }, ctx: z.RefinementCtx) => {
  if ((row.latitude === null) !== (row.longitude === null)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'coordinate pair must be complete' });
  }
  if (row.display_precision === 'unmapped' && (row.latitude !== null || row.longitude !== null)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'unmapped record cannot have coordinates' });
  }
  if (row.display_precision !== 'unmapped' && (row.latitude === null || row.longitude === null)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'mapped record requires coordinates' });
  }
};

export const locationSchema = z.object(locationShape).strict().superRefine(coordinateRules);
export const testReleaseLocationSchema = z.object({
  ...locationShape,
  // The disposable test-release fixture predates the optional normalized
  // provenance label; keep that private-only compatibility surface readable.
  provenance_source: textOrNull.optional().default(null),
  publication_profile: z.enum(['official', 'secondary', 'community']).nullable(),
  privacy_screening_status: z.enum(['pending', 'passed', 'failed']),
  project_approval: z.union([z.enum(['pending', 'approved']), z.literal(false), z.literal('not-approved')]),
  source_rights_status: z.string().default('unknown'),
  release_ruleset_version: z.string().nullable(),
}).strict().superRefine(coordinateRules);

const profile = z.enum(['official', 'secondary', 'community']);
const listMeta = z.object({
  release_id: z.string().nullable(),
  ruleset_version: z.string().optional(),
  data_product_version: z.string().optional(),
  schema_version: z.string().optional(),
  release_created_at: z.string().datetime({ offset: true }).optional(),
  profile,
  next_cursor: z.string().nullable().optional(),
  coverage_note: z.string().min(1),
  coverage_scope: z.string().optional(),
  count_semantics: z.string().optional(),
  query: z.object({
    q: z.string().nullable().optional(),
    filters: z.record(z.string(), z.string().nullable()),
  }).optional(),
});

export const envelopeSchema = z.object({ data: z.array(locationSchema), api_version: z.literal('v2'), meta: listMeta }).strict();
export type WireEnvelope = z.infer<typeof envelopeSchema>;
export type WireLocation = z.infer<typeof locationSchema>;
export type WireTestReleaseLocation = z.infer<typeof testReleaseLocationSchema>;

export const detailEnvelopeSchema = z.object({
  data: locationSchema,
  api_version: z.literal('v2'),
  meta: z.object({
    release_id: z.string(),
    ruleset_version: z.string(),
    data_product_version: z.string().optional(),
    schema_version: z.string().optional(),
    release_created_at: z.string().datetime({ offset: true }),
    profile,
    coverage_scope: z.string().optional(),
    count_semantics: z.string().optional(),
  }).strict(),
}).strict();
export type DetailEnvelope = z.infer<typeof detailEnvelopeSchema>;
