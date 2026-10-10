export type LocationId = string;
export type GeometryProvenance = Readonly<{
  origin: 'source_coordinates' | 'provider_derived' | 'verified_coarse_reference' | 'provider_geocode' | 'city_reference' | 'unmapped';
  method?: string | undefined; source_precision?: string | undefined; provider?: string | undefined; provider_status?: string | undefined; provider_queried_at?: string | undefined;
  confidence?: string | undefined; confidence_band?: string | undefined; coordinate_review_status?: string | undefined; reference_source_id?: string | undefined;
  reference_source?: string | undefined; evidence_kind?: string | undefined; evidence_id?: string | undefined;
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
export type SourceFlagValue = string | boolean;
export type SourceVolumeCategory = Readonly<{
  code: string;
  provenance?: string | Readonly<{ sourceField?: string; method?: string }>;
}>;
export type DerivedSourceVolumeRange = Readonly<{
  ordinalCode: string;
  lower: number | null;
  upper: number | null;
  bounds: 'exclusive_upper' | 'inclusive_lower_unbounded' | 'inclusive_lower_exclusive_upper';
  unit: 'head' | 'pounds';
  period: 'trailing_360_days' | 'month';
  methodVersion: 'fsis-mpi-volume-codebook-2026-03-24-v1';
  sourceCodebookUrl: string;
  verificationState: 'source_codebook_verified';
}>;
export type AphisAnnualReport = Readonly<{
  fiscalYear: string;
  speciesCounts: readonly Readonly<{ species: string; count: number }>[];
  sourceUrl: string;
  safeProvenance: Readonly<{
    sourceId: 'us.aphis.annual-reports';
    evidenceType: 'annual_reports';
    matchMethod: 'exact_source_identifier';
    matchedIdentifierTypes: readonly ('certificate_number' | 'customer_number')[];
  }>;
}>;
// These are source-native, release-built detail facts. They are intentionally
// absent from list and map projections.
export type LocationSourceFacts = Readonly<{
  alternateNames?: readonly string[];
  speciesSlaughtered?: Readonly<Record<string, SourceFlagValue>>;
  processingActivities?: Readonly<Record<string, SourceFlagValue>>;
  sourceVolumeCategories?: readonly SourceVolumeCategory[];
  derivedSourceVolumeRanges?: readonly DerivedSourceVolumeRange[];
  aphisAnnualReports?: readonly AphisAnnualReport[];
  establishmentId?: string;
  establishmentNumber?: string;
  grantDate?: string;
  nativeActivityCode?: string;
  nativeActivityLabel?: string;
}>;
import type { TaxonomyClassification } from './taxonomy';
export type Location = Readonly<{id:LocationId,name:string,region:string,category:string,lat:number|null,lon:number|null,observed:string,source:string,sourceId?:string,taxonomy?:TaxonomyClassification,evidence?:LocationEvidence,sourceFacts?:LocationSourceFacts}>;
