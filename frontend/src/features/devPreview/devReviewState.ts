export type LocalReviewState = 'unreviewed' | 'inspected' | 'follow_up';

/** These actions are operator notes for this browser session, never approval or suppression writes. */
export const nextLocalReviewState = (state: LocalReviewState, action: 'inspect' | 'follow_up'): LocalReviewState =>
  action === 'follow_up' ? 'follow_up' : state === 'follow_up' ? state : 'inspected';
