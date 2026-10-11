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
const nullableText = z.string().nullable().optional();
const geometryProvenanceSchema = z.object({
  origin: z.enum(['source_coordinates', 'provider_derived', 'verified_coarse_reference', 'provider_geocode', 'city_reference', 'unmapped']),
  method: z.string().max(120).optional(),
  source_precision: z.string().max(120).optional(),
  provider: z.string().max(160).optional(),
  provider_status: z.string().max(80).optional(),
  provider_queried_at: z.string().datetime({ offset: true }).optional(),
  confidence: z.string().max(40).optional(),
  confidence_band: z.string().max(40).optional(),
  coordinate_review_status: z.string().max(80).optional(),
  reference_source_id: z.string().max(160).optional(),
  reference_source: z.string().max(200).optional(),
  evidence_kind: z.string().max(80).optional(),
  evidence_id: z.string().max(160).optional(),
}).strict();
const taxonomyAssignmentSchema = z.object({
  primary_key: z.string().min(1),
  leaf_key: nullableText,
  leaf_label: nullableText,
  source_code_reference: nullableText,
  source_label_reference: nullableText,
  source_code: nullableText,
  source_label: nullableText,
  method: z.enum(['direct', 'derived', 'candidate']),
  status: z.enum(['mapped', 'partial', 'unmapped', 'unclassified', 'conflicting', 'ambiguous']),
  taxonomy_version: z.string().min(1),
  crosswalk_version: nullableText,
  ruleset_version: nullableText,
  observation_id: nullableText,
  source_record_id: nullableText,
  artifact_id: nullableText,
}).strict();
const sourceFlagValue = z.union([z.string().min(1).max(200), z.boolean()]);
const sourceFlags = z.record(z.string().min(1).max(120), sourceFlagValue)
  .refine(value => Object.keys(value).length > 0 && Object.keys(value).length <= 64);
const sourceVolumeProvenance = z.union([
  z.string().min(1).max(160),
  z.object({ source_field: z.string().min(1).max(120).optional(), method: z.string().min(1).max(80).optional() }).strict(),
]);
const sourceVolumeCategory = z.object({
  code: z.string().min(1).max(120),
  provenance: sourceVolumeProvenance.optional(),
}).strict();
const derivedSourceVolumeRange = z.object({
  ordinal_code: z.string().min(1).max(120),
  lower: z.number().int().nonnegative().nullable(),
  upper: z.number().int().positive().nullable(),
  bounds: z.enum(['exclusive_upper', 'inclusive_lower_unbounded', 'inclusive_lower_exclusive_upper']),
  unit: z.enum(['head', 'pounds']),
  period: z.enum(['trailing_360_days', 'month']),
  method_version: z.literal('fsis-mpi-volume-codebook-2026-03-24-v1'),
  source_codebook_url: sourceUrl,
  verification_state: z.literal('source_codebook_verified'),
}).strict().superRefine((range, ctx) => {
  const valid = range.bounds === 'exclusive_upper'
    ? range.lower === null && range.upper !== null
    : range.bounds === 'inclusive_lower_unbounded'
      ? range.lower !== null && range.upper === null
      : range.lower !== null && range.upper !== null && range.lower < range.upper;
  if (!valid) ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'volume range bounds must match its declared shape' });
});
const aphisAnnualReport = z.object({
  fiscal_year: z.string().regex(/^\d{4}$/),
  species_counts: z.array(z.object({ species: z.string().min(1).max(120), count: z.number().int().nonnegative() }).strict()).min(1).max(32),
  source_url: sourceUrl,
  safe_provenance: z.object({
    source_id: z.literal('us.aphis.annual-reports'),
    evidence_type: z.literal('annual_reports'),
    match_method: z.literal('exact_source_identifier'),
    matched_identifier_types: z.array(z.enum(['certificate_number', 'customer_number'])).min(1).max(2),
  }).strict(),
}).strict();
const detailFactsShape = {
  alternate_names: z.array(z.string().min(1).max(200)).min(1).max(32).optional(),
  species_slaughtered: sourceFlags.optional(),
  processing_activities: sourceFlags.optional(),
  source_volume_categories: z.array(sourceVolumeCategory).min(1).max(32).optional(),
  derived_source_volume_ranges: z.array(derivedSourceVolumeRange).min(1).max(32).optional(),
  aphis_annual_reports: z.array(aphisAnnualReport).min(1).max(16).optional(),
  establishment_id: z.string().min(1).max(160).optional(),
  establishment_number: z.string().min(1).max(160).optional(),
  grant_date: z.string().min(1).max(80).optional(),
  native_activity_code: z.string().min(1).max(160).optional(),
  native_activity_label: z.string().min(1).max(500).optional(),
};

// This is the Rust-shaped public projection. Keep this list closed: fields
// that are not present in the current API belong in the convergence gap ledger
// and must not be invented in a frontend DTO.
const locationShape = {
  facility_id: z.string().uuid(),
  canonical_name: z.string().nullable(),
  country_code: z.string().regex(/^[A-Z]{2}$/),
  city: textOrNull,
  category: z.string(),
  // Additive taxonomy contract. Older v2 responses remain valid and are
  // represented by the client as unclassified until an explicit key exists.
  taxonomy_display_category: z.string().min(1).optional(),
  taxonomy_primary_categories: z.array(z.string().min(1)).optional(),
  taxonomy_leaf_activities: z.array(z.object({ key: z.string().min(1), label: z.string().min(1) }).strict()).optional(),
  taxonomy_assignments: z.array(taxonomyAssignmentSchema).optional(),
  publication_profile: z.enum(['official', 'secondary', 'community']),
  factual_review_status: z.string(),
  privacy_screening_status: z.literal('passed'),
  project_approval: z.string(),
  reviewer_role: textOrNull,
  publication_warning: textOrNull,
  display_precision: z.enum(['exact', 'city', 'source_reported', 'approximate', 'unmapped']),
  geometry_provenance: geometryProvenanceSchema.optional(),
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
// Detail accepts only this bounded, source-native allowlist in addition to the
// list projection. Keep listSchema closed so a detail field cannot leak into
// map or list payloads unnoticed.
export const detailLocationSchema = z.object({ ...locationShape, ...detailFactsShape }).strict().superRefine(coordinateRules);
const testReleaseLocationShape = {
  ...locationShape,
  // The disposable test-release fixture predates the optional normalized
  // provenance label; keep that private-only compatibility surface readable.
  provenance_source: textOrNull.optional().default(null),
  publication_profile: z.enum(['official', 'secondary', 'community']).nullable(),
  privacy_screening_status: z.enum(['pending', 'passed', 'failed']),
  project_approval: z.union([z.enum(['pending', 'approved']), z.literal(false), z.literal('not-approved')]),
  source_rights_status: z.string().default('unknown'),
  release_ruleset_version: z.string().nullable(),
  // Filterable candidate projection fields are additive and remain distinct
  // from detail-only native facts.
  category_keys: z.array(z.string().min(1).max(120)).max(16).optional(),
  activity_keys: z.array(z.string().min(1).max(240)).max(64).optional(),
};
export const testReleaseLocationSchema = z.object(testReleaseLocationShape).strict().superRefine(coordinateRules);
// The configured candidate detail retains its private test-release core and
// may add only the same bounded source-native facts as public detail. Keep it
// distinct from public detail: candidate responses do not promise the public
// lifecycle, reviewer, taxonomy, or rights fields beyond their core shape.
const testReleaseDetailLocationShape = {
  facility_id: z.string().uuid(),
  canonical_name: z.string().nullable(),
  country_code: z.string().regex(/^[A-Z]{2}$/),
  city: textOrNull,
  category: z.string(),
  publication_profile: z.enum(['official', 'secondary', 'community']).nullable(),
  factual_review_status: z.string(),
  privacy_screening_status: z.enum(['pending', 'passed', 'failed']),
  project_approval: z.union([z.enum(['pending', 'approved']), z.literal(false), z.literal('not-approved')]),
  publication_warning: textOrNull,
  // Candidate geometry preserves the source's native precision label. The
  // renderer maps this additive source-provided value to its existing
  // source-reported presentation while retaining the provenance precision.
  display_precision: z.enum(['exact', 'city', 'source_reported', 'source-provided', 'approximate', 'unmapped']),
  // Candidate detail geometry is deliberately smaller than the public
  // provenance projection. Keep it closed to the API's safe detail contract.
  coordinate_method: z.enum(['source_coordinate', 'city_reference']).nullable().optional(),
  geometry_provenance: z.object({
    kind: z.string().min(1).max(80),
    method: z.string().min(1).max(120).optional(),
    precision: z.string().min(1).max(120).optional(),
  }).strict().optional(),
  latitude: z.number().finite().nullable(),
  longitude: z.number().finite().nullable(),
  provenance_source_id: z.string(),
  provenance_source_name: z.string(),
  provenance_source_url: sourceUrl,
  provenance_retrieved_at: z.string().datetime({ offset: true }),
  release_id: z.string(),
  release_ruleset_version: z.string().nullable(),
  category_keys: z.array(z.string().min(1).max(120)).max(16).optional(),
  activity_keys: z.array(z.string().min(1).max(240)).max(64).optional(),
};
export const testReleaseDetailLocationSchema = z.object({
  ...testReleaseDetailLocationShape,
  ...detailFactsShape,
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
  total_count: z.number().int().nonnegative().optional(),
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
export type WireDetailLocation = z.infer<typeof detailLocationSchema>;
export type WireTestReleaseLocation = z.infer<typeof testReleaseLocationSchema>;
export type WireTestReleaseDetailLocation = z.infer<typeof testReleaseDetailLocationSchema>;

export const detailEnvelopeSchema = z.object({
  data: detailLocationSchema,
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
