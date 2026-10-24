import { z } from 'zod';

const uuid = z.string().uuid();
const confidenceBand = z.enum(['exact', 'high', 'medium', 'low']);
const profile = z.enum(['official', 'secondary', 'community']);
const aphisDocumentUrl = z.string().url().refine(value => {
  try {
    const url = new URL(value);
    const queryEntries = [...url.searchParams.entries()];
    const queryKeys = queryEntries.map(([key]) => key).sort().join(',');
    const salesforceDocument = url.hostname === 'aphis.file.force.com'
      && ['/sfc/dist/version/download', '/sfc/dist/version/download/'].includes(url.pathname)
      && queryEntries.length === 4 && queryKeys === 'asPdf,d,ids,oid'
      && /^([A-Za-z0-9]{15}|[A-Za-z0-9]{18})$/.test(url.searchParams.get('oid') ?? '')
      && /^([A-Za-z0-9]{15}|[A-Za-z0-9]{18})$/.test(url.searchParams.get('ids') ?? '')
      && ['true', 'false'].includes(url.searchParams.get('asPdf') ?? '')
      && /^[A-Za-z0-9._~/-]{1,512}$/.test(url.searchParams.get('d') ?? '')
      && !url.hash;
    return url.protocol === 'https:'
      && (['aphis.my.site.com', 'direct.aphis.usda.gov', 'www.aphis.usda.gov', 'efile.aphis.usda.gov'].includes(url.hostname)
        && ['/PublicSearchTool/', '/awa/', '/sites/', '/efile/'].some(prefix => url.pathname.startsWith(prefix))
        || salesforceDocument)
      && !url.username && !url.password && !url.port;
  } catch { return false; }
}).nullable();

export const graphEndpointSchema = z.object({
  entity_id: uuid.nullable(),
  entity_type: z.enum(['facility', 'organization']),
  source_id: z.string().min(1),
  identifier_type: z.string().min(1),
  source_identifier: z.string().min(1),
  display_name: z.string().nullable().optional(),
}).strict();

export const graphConnectionSchema = z.object({
  connection_edge_id: uuid,
  from: graphEndpointSchema,
  to: graphEndpointSchema,
  relationship_type: z.string().min(1),
  connection_type: z.enum(['exact', 'inferred']),
  confidence: z.number().finite().min(0).max(1),
  confidence_band: confidenceBand,
  match_method: z.string().min(1),
  signals: z.record(z.string(), z.unknown()),
  contradictions: z.array(z.unknown()),
  provenance: z.object({
    source_ids: z.array(z.string().min(1)).min(1),
    observed_at: z.string().datetime({ offset: true }),
    release_id: z.string().min(1),
  }).strict(),
  source_references: z.array(z.object({ source_id: z.string().min(1) }).strict()).min(1),
  observed_at: z.string().datetime({ offset: true }),
  computed_at: z.string().datetime({ offset: true }),
  ruleset: z.string().min(1),
  conflicting: z.boolean(),
  publication_warning: z.string().min(1),
  disclaimer: z.string().min(1),
}).strict();

export const graphEntitySchema = z.object({
  entity_id: uuid,
  entity_type: z.enum(['facility', 'organization']),
  display_name: z.string().nullable(),
  country_code: z.string().regex(/^[A-Z]{2}$/).nullable(),
}).strict();

const graphEvidenceReferenceBaseSchema = z.object({
  reference_id: uuid,
  source_id: z.enum(['us.aphis.annual-reports', 'us.inspections']),
  evidence_type: z.enum(['annual_reports', 'inspections']),
  event_date: z.string().date().nullable(),
  event_period: z.string().regex(/^\d{4}$/).nullable(),
  observed_at: z.string().datetime({ offset: true }),
  source_url: z.enum([
    'https://direct.aphis.usda.gov/awa/research-facility-report/annual-summary',
    'https://direct.aphis.usda.gov/awa/search/inspection-reports',
  ]),
  match_method: z.literal('exact_source_identifier'),
}).strict();

function validateEvidenceReference(reference: z.infer<typeof graphEvidenceReferenceBaseSchema>, ctx: z.RefinementCtx) {
  const annual = reference.evidence_type === 'annual_reports'
    && reference.source_id === 'us.aphis.annual-reports'
    && reference.event_date === null && reference.event_period !== null
    && reference.source_url.endsWith('/annual-summary');
  const inspection = reference.evidence_type === 'inspections'
    && reference.source_id === 'us.inspections'
    && reference.event_date !== null && reference.event_period === null
    && reference.source_url.endsWith('/inspection-reports');
  if (!annual && !inspection) ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'APHIS reference fields must describe one supported event type.' });
}

export const graphEvidenceReferenceSchema = graphEvidenceReferenceBaseSchema.superRefine(validateEvidenceReference);

const pageMeta = z.object({
  profile,
  release_id: z.string().min(1),
  ruleset_version: z.string().min(1),
  limit: z.number().int().min(1).max(100),
  page_max: z.literal(100),
  next_cursor: uuid.nullable().optional(),
  public_projection: z.literal(true),
}).passthrough();

export const graphConnectionsEnvelopeSchema = z.object({
  api_version: z.literal('v2-graph-v1'),
  data: z.array(graphConnectionSchema),
  meta: pageMeta,
}).strict();

export const graphEntitiesEnvelopeSchema = z.object({
  api_version: z.literal('v2-graph-v1'),
  data: z.array(graphEntitySchema),
  meta: pageMeta,
}).strict();

export const graphEvidenceReferencesEnvelopeSchema = z.object({
  api_version: z.literal('v2-graph-v1'),
  data: z.array(graphEvidenceReferenceSchema),
  meta: pageMeta,
}).strict();

export const aphisReportLinksEnvelopeSchema = z.object({
  api_version: z.literal('v2'),
  data: z.array(graphEvidenceReferenceBaseSchema.extend({
    report_url: aphisDocumentUrl,
    column_e_url: aphisDocumentUrl,
  }).strict().superRefine((reference, ctx) => validateEvidenceReference(reference, ctx))),
  meta: z.object({
    profile,
    release_id: z.string().min(1),
    ruleset_version: z.string().min(1),
    kind: z.enum(['annual_reports', 'inspections']),
    limit: z.number().int().min(1).max(100),
    next_cursor: uuid.nullable(),
    public_projection: z.literal(true),
  }).strict(),
}).strict().superRefine((response, ctx) => {
  response.data.forEach((reference, index) => {
    if (reference.evidence_type !== response.meta.kind) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['data', index, 'evidence_type'], message: 'APHIS report page contains another report kind.' });
    }
  });
});

export type PublicGraphConnection = z.infer<typeof graphConnectionSchema>;
export type PublicGraphEntity = z.infer<typeof graphEntitySchema>;
export type PublicGraphEvidenceReference = z.infer<typeof graphEvidenceReferenceSchema>;
export type PublicAphisReportLink = z.infer<typeof aphisReportLinksEnvelopeSchema>['data'][number];
export type PublicGraphProfile = z.infer<typeof profile>;
export type PublicGraphConnectionsEnvelope = z.infer<typeof graphConnectionsEnvelopeSchema>;
export type PublicGraphEntitiesEnvelope = z.infer<typeof graphEntitiesEnvelopeSchema>;
export type PublicGraphEvidenceReferencesEnvelope = z.infer<typeof graphEvidenceReferencesEnvelopeSchema>;
