export type V2Profile = 'official' | 'secondary' | 'community';
export type V2SourceType = 'official' | 'secondary' | 'user_submitted';
export type V2DisplayPrecision = 'exact' | 'city' | 'unmapped';
export type V2LifecycleStatus = 'active_observed' | 'explicitly_closed' | 'not_seen_recently' | 'status_unknown';
export declare const V2_LOCATION_FIELDS: readonly string[];

export interface V2Location {
    facility_id: string;
    canonical_name: string | null;
    country_code: string;
    city: string | null;
    category: string;
    publication_profile: V2Profile;
    factual_review_status: string;
    privacy_screening_status: string;
    project_approval: string;
    reviewer_role: string | null;
    publication_warning: string | null;
    display_precision: V2DisplayPrecision;
    latitude: number | null;
    longitude: number | null;
    first_observed_at: string | null;
    last_observed_at: string | null;
    observation_count: number | null;
    lifecycle_status: V2LifecycleStatus;
    source_type: V2SourceType;
    source_rights_status: string;
    provenance_source: string | null;
    release_id: string;
    release_ruleset_version: string;
    provenance_source_id: string;
    provenance_source_name: string;
    provenance_source_url: string;
    provenance_retrieved_at: string;
}

export interface V2QueryMeta {
    q?: string | null;
    filters?: Record<string, string | null>;
}

export interface V2ListMeta {
    profile: V2Profile;
    release_id: string | null;
    ruleset_version?: string;
    data_product_version?: string;
    schema_version?: string;
    release_created_at?: string;
    next_cursor?: string | null;
    coverage_note: string;
    coverage_scope?: string;
    count_semantics?: string;
    query?: V2QueryMeta;
}

export interface V2DetailMeta {
    profile: V2Profile;
    release_id: string;
    ruleset_version: string;
    data_product_version?: string;
    schema_version?: string;
    release_created_at: string;
    coverage_scope?: string;
    count_semantics?: string;
}

export interface V2Error {
    api_version: 'v2';
    error: { code: string; message: string };
}

export interface V2Envelope<T, M extends V2ListMeta | V2DetailMeta = V2ListMeta> {
    data: T;
    api_version: 'v2';
    meta: M;
}
