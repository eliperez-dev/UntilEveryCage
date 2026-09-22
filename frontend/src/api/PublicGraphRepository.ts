import { z } from 'zod';
import type { ApiError } from './errors';
import type { FetchLike, LocalProfile } from './LocalLocationRepository';
import { graphConnectionsEnvelopeSchema, graphEntitiesEnvelopeSchema, type PublicGraphConnection, type PublicGraphEntity } from './publicGraphSchema';

export type GraphFilters = Readonly<{
  connection_type?: 'exact' | 'inferred';
  min_confidence?: number;
  max_confidence?: number;
  confidence_band?: 'exact' | 'high' | 'medium' | 'low';
  include_conflicting?: boolean;
  source_id?: string;
  entity_id?: string;
  cursor?: string;
  limit?: number;
}>;
export type GraphEntityFilters = Readonly<{ q?: string; entity_type?: 'facility' | 'organization'; cursor?: string; limit?: number }>;
export type GraphPage<T> = Readonly<{ data: readonly T[]; releaseId: string; ruleset: string; profile: LocalProfile; nextCursor: string | null }>;

const fail = (kind: ApiError['kind'], message: string, status?: number, code?: string): ApiError => Object.assign(new Error(message), { kind, ...(status === undefined ? {} : { status }), ...(code ? { code } : {}) });
const uuid = z.string().uuid();

export const serializeGraphQuery = (profile: LocalProfile, filters: Record<string, unknown> = {}): string => {
  const params = new URLSearchParams({ profile });
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  return params.toString();
};

export class PublicGraphRepository {
  readonly #base: string | undefined;
  constructor(private readonly fetcher: FetchLike = globalThis.fetch, baseUrl?: string) { this.#base = baseUrl ? new URL(baseUrl).origin : undefined; }

  private async json(path: string, signal?: AbortSignal): Promise<unknown> {
    let response: Response;
    try {
      response = await this.fetcher.call(globalThis, `${this.#base ?? ''}${path}`, { cache: 'no-store', ...(signal ? { signal } : {}) });
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') throw fail('aborted', 'Public graph request was aborted.');
      if (error instanceof TypeError) throw fail('network', 'Public graph request could not connect.');
      throw fail('network', 'Public graph request failed.');
    }
    if (!response.ok) {
      let code: string | undefined; let message = `Public graph request failed with status ${response.status}.`;
      try { const body = await response.json() as { error?: { code?: string; message?: string } }; code = body.error?.code; message = body.error?.message ?? message; } catch { /* keep status-safe text */ }
      throw fail(response.status === 404 ? 'no-release' : response.status === 429 ? 'rate-limited' : response.status >= 500 ? 'unavailable' : 'http', message, response.status, code);
    }
    try { return await response.json(); } catch { throw fail('invalid-contract', 'Public graph response was not valid JSON.'); }
  }

  async connections(profile: LocalProfile = 'official', filters: GraphFilters = {}, signal?: AbortSignal): Promise<GraphPage<PublicGraphConnection>> {
    const parsed = graphConnectionsEnvelopeSchema.safeParse(await this.json(`/api/v2/graph/connections?${serializeGraphQuery(profile, filters)}`, signal));
    if (!parsed.success) throw fail('invalid-contract', 'Public graph connection response was rejected safely.');
    return { data: parsed.data.data, profile, releaseId: parsed.data.meta.release_id, ruleset: parsed.data.meta.ruleset_version, nextCursor: parsed.data.meta.next_cursor ?? null };
  }

  async entities(profile: LocalProfile = 'official', filters: GraphEntityFilters = {}, signal?: AbortSignal): Promise<GraphPage<PublicGraphEntity>> {
    const parsed = graphEntitiesEnvelopeSchema.safeParse(await this.json(`/api/v2/graph/entities?${serializeGraphQuery(profile, filters)}`, signal));
    if (!parsed.success) throw fail('invalid-contract', 'Public graph entity response was rejected safely.');
    return { data: parsed.data.data, profile, releaseId: parsed.data.meta.release_id, ruleset: parsed.data.meta.ruleset_version, nextCursor: parsed.data.meta.next_cursor ?? null };
  }

  async neighborhood(entityId: string, profile: LocalProfile = 'official', filters: Omit<GraphFilters, 'entity_id'> = {}, signal?: AbortSignal): Promise<GraphPage<PublicGraphConnection>> {
    if (!uuid.safeParse(entityId).success) throw fail('invalid-contract', 'Graph entity ID must be a UUID.');
    return this.connections(profile, { ...filters, entity_id: entityId }, signal);
  }
}
