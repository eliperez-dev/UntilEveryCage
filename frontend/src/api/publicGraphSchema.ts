import { z } from 'zod';

const uuid = z.string().uuid();
const confidenceBand = z.enum(['exact', 'high', 'medium', 'low']);
const profile = z.enum(['official', 'secondary', 'community']);

export const graphEndpointSchema = z.object({
  entity_id: uuid.nullable(),
  entity_type: z.enum(['facility', 'organization']),
  source_id: z.string().min(1),
  identifier_type: z.string().min(1),
  source_identifier: z.string().min(1),
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

export type PublicGraphConnection = z.infer<typeof graphConnectionSchema>;
export type PublicGraphEntity = z.infer<typeof graphEntitySchema>;
export type PublicGraphProfile = z.infer<typeof profile>;
export type PublicGraphConnectionsEnvelope = z.infer<typeof graphConnectionsEnvelopeSchema>;
export type PublicGraphEntitiesEnvelope = z.infer<typeof graphEntitiesEnvelopeSchema>;
