export type LocationId = string;
export type GeometryProvenance = Readonly<{
  origin: 'source_coordinates' | 'provider_derived' | 'verified_coarse_reference' | 'provider_geocode' | 'city_reference' | 'unmapped';
  method?: string; source_precision?: string; provider?: string; provider_status?: string; provider_queried_at?: string;
  confidence?: string; confidence_band?: string; coordinate_review_status?: string; reference_source_id?: string;
  reference_source?: string; evidence_kind?: string; evidence_id?: string;
}>;
// Evidence stays separate from the display name: origin, review, privacy,
// approval, precision, and lifecycle are independent signals.
export type LocationEvidence = Readonly<{
  sourceType: 'official' | 'secondary' | 'user_submitted';
  factualReviewStatus: string;
  reviewerRole: string | null;
  privacyScreeningStatus: 'pending' | 'passed' | 'failed';
  projectApproval: string | false;
  publicationProfile: 'official' | 'secondary' | 'community' | null;
  publicationWarning: string | null;
  sourceId: string;
  sourceUrl: string;
  provenanceSource: string | null;
  sourceRightsStatus: string;
  retrievedAt: string;
  displayPrecision: 'exact' | 'city' | 'source_reported' | 'approximate' | 'unmapped';
  geometryProvenance?: GeometryProvenance;
  lifecycleStatus: 'active_observed' | 'explicitly_closed' | 'not_seen_recently' | 'status_unknown';
  observationCount: number | null;
}>;
import type { TaxonomyClassification } from './taxonomy';
export type Location = Readonly<{id:LocationId,name:string,region:string,category:string,lat:number|null,lon:number|null,observed:string,source:string,sourceId?:string,taxonomy?:TaxonomyClassification,evidence?:LocationEvidence}>;
