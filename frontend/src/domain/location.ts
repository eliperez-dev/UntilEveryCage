export type LocationId = string;
// Evidence stays separate from the display name: origin, review, privacy,
// approval, precision, and lifecycle are independent signals.
export type LocationEvidence = Readonly<{
  sourceType: 'official' | 'secondary' | 'user_submitted';
  factualReviewStatus: 'unreviewed' | 'reviewed' | 'rejected';
  reviewerRole: string | null;
  privacyScreeningStatus: 'passed';
  projectApproval: 'pending' | 'approved';
  publicationProfile: 'official' | 'secondary' | 'community';
  publicationWarning: string | null;
  sourceId: string;
  sourceUrl: string;
  retrievedAt: string;
  displayPrecision: 'exact' | 'city' | 'unmapped';
  lifecycleStatus: 'active_observed' | 'explicitly_closed' | 'not_seen_recently' | 'status_unknown';
  observationCount: number | null;
}>;
export type Location = Readonly<{id:LocationId,name:string,region:string,category:string,lat:number|null,lon:number|null,observed:string,source:string,evidence?:LocationEvidence}>;
