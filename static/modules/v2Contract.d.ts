export type V2Profile = 'official' | 'secondary' | 'community';
export type V2SourceType = 'official' | 'secondary' | 'user_submitted';
export type V2DisplayPrecision = 'exact' | 'city' | 'unmapped';
export type V2LifecycleStatus = 'active_observed' | 'explicitly_closed' | 'not_seen_recently' | 'status_unknown';

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
    provenance_source: string | null;
    release_id: string;
    release_ruleset_version: string;
    provenance_source_id: string;
    provenance_source_name: string;
    provenance_source_url: string;
    provenance_retrieved_at: string;
}

export interface V2Envelope<T> {
    data: T;
    api_version: 'v2';
    meta: Record<string, unknown>;
}
