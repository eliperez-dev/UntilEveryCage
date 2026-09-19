/** `curated` is retained only as the fixture-mode label. It maps to the V2
 * `official` profile before a request is made. */
export type Profile = 'curated' | 'official' | 'secondary' | 'community';
export type ApiProfile = Exclude<Profile, 'curated'>;
export const API_PROFILES: readonly ApiProfile[] = ['official', 'secondary', 'community'];
export const toApiProfile = (profile: Profile): ApiProfile => profile === 'curated' ? 'official' : profile;
export const profileLabel = (profile: Profile): string => ({
  curated: 'Official / curated release',
  official: 'Official profile',
  secondary: 'Secondary sources',
  community: 'Community claims',
}[profile]);
export type Publication = Readonly<{origin:'government-sourced'|'community-submitted';review:'project-approved'|'community-unreviewed';profile:Profile;published:boolean}>;
