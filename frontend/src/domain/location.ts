export type LocationId = string;
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
}>;
export type Location = Readonly<{id:LocationId,name:string,region:string,category:string,lat:number|null,lon:number|null,observed:string,source:string,evidence?:LocationEvidence}>;
