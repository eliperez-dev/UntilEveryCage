export type Profile='curated'|'community';
export type Publication = Readonly<{origin:'government-sourced'|'community-submitted';review:'project-approved'|'community-unreviewed';profile:Profile;published:boolean}>;
