import type { ClaimedPrecision, ContributionDraft, Receipt, SubmissionKind } from '../../api/CommunityRepository';
import { CommunityError, validateContributionDraft } from '../../api/CommunityRepository';
import { parseRecordReference } from '../recordReference';

/** Page-memory drafts only. Do not serialize these to storage, history or diagnostics. */
export type IntakeDraft = {
  targetReference: string; duplicateReference: string; label: string; countryCode: string; locality: string;
  claimedActivity: string; locationText: string; latitude: number | undefined; longitude: number | undefined;
  precision: ClaimedPrecision; locationInputMethod: 'manual_pin' | 'text' | undefined;
  sourceUrl: string; observedOn: string; description: string; expectedBehavior: string;
  reproductionSteps: string; pageUrl: string; contactEmail: string; consent: boolean;
  detailsOpen: boolean; locationOpen: boolean; contactOpen: boolean;
};
export type IntakeErrors = Partial<Record<keyof IntakeDraft | 'form', string>>;
export const intakeKinds: readonly SubmissionKind[] = ['facility', 'correction', 'evidence', 'duplicate', 'privacy_removal', 'bug'];
export const intakeTitles: Record<SubmissionKind, string> = {
  facility: 'Add a facility', correction: 'Suggest a correction', evidence: 'Add evidence',
  duplicate: 'Report a duplicate', privacy_removal: 'Privacy or removal', bug: 'Report a bug',
};
export function emptyIntakeDraft(): IntakeDraft {
  return { targetReference: '', duplicateReference: '', label: '', countryCode: '', locality: '', claimedActivity: '',
    locationText: '', latitude: undefined, longitude: undefined, precision: 'unknown', locationInputMethod: undefined,
    sourceUrl: '', observedOn: '', description: '', expectedBehavior: '', reproductionSteps: '', pageUrl: '',
    contactEmail: '', consent: false, detailsOpen: false, locationOpen: false, contactOpen: false };
}
export function createIntakeDrafts(): Record<SubmissionKind, IntakeDraft> {
  return Object.fromEntries(intakeKinds.map(kind => [kind, emptyIntakeDraft()])) as Record<SubmissionKind, IntakeDraft>;
}
const httpUrl = (value: string): boolean => {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password; }
  catch { return false; }
};
export function validateIntakeDraft(kind: SubmissionKind, draft: IntakeDraft): IntakeErrors {
  const errors: IntakeErrors = {};
  const target = parseRecordReference(draft.targetReference);
  const duplicate = parseRecordReference(draft.duplicateReference);
  if (kind !== 'facility' && kind !== 'bug' && !target) errors.targetReference = 'Choose a facility or paste its record link.';
  if (kind === 'facility' && !draft.label.trim()) errors.label = 'Add a facility name or a short description.';
  if (kind === 'duplicate' && (!duplicate || duplicate === target)) errors.duplicateReference = 'Choose a different record for the possible duplicate.';
  if (['correction', 'privacy_removal', 'bug'].includes(kind) && !draft.description.trim()) errors.description = 'Add a short explanation.';
  if (kind === 'evidence' && !draft.sourceUrl.trim() && !draft.description.trim()) errors.description = 'Add a source link or describe what you found.';
  if (kind === 'bug' && !draft.reproductionSteps.trim()) errors.reproductionSteps = 'Describe how to reproduce the issue.';
  if (draft.sourceUrl.trim() && !httpUrl(draft.sourceUrl.trim())) errors.sourceUrl = 'Use a complete web link without embedded sign-in details.';
  if (kind === 'bug' && draft.pageUrl.trim() && !httpUrl(draft.pageUrl.trim())) errors.pageUrl = 'Use a complete web link without embedded sign-in details.';
  if (draft.contactEmail.trim() && !/^[^\s@]+@[^\s@]+$/.test(draft.contactEmail.trim())) errors.contactEmail = 'Enter a valid email address or leave it blank.';
  if (kind !== 'bug' && !draft.consent) errors.consent = 'Confirm you have permission to share this information.';
  if (kind === 'facility' || kind === 'correction') {
    if ((draft.latitude === undefined) !== (draft.longitude === undefined)) errors.latitude = 'Enter both coordinates or clear the selected point.';
    if (draft.latitude !== undefined && (!Number.isFinite(draft.latitude) || Math.abs(draft.latitude) > 90)) errors.latitude = 'Latitude must be between −90 and 90.';
    if (draft.longitude !== undefined && (!Number.isFinite(draft.longitude) || Math.abs(draft.longitude) > 180)) errors.longitude = 'Longitude must be between −180 and 180.';
  }
  return errors;
}
export function buildIntakePayload(kind: SubmissionKind, draft: IntakeDraft): ContributionDraft {
  if (kind !== 'bug' && !draft.consent) throw new CommunityError('invalid', 'Confirm you have permission to share this information.');
  const text = (value: string) => value.trim() || undefined;
  const target = parseRecordReference(draft.targetReference), duplicate = parseRecordReference(draft.duplicateReference);
  const locationKind = kind === 'facility' || kind === 'correction';
  const hasPoint = locationKind && draft.precision !== 'unmapped' && draft.latitude !== undefined && draft.longitude !== undefined;
  const payload: ContributionDraft = {
    kind, consent: true,
    ...(kind !== 'bug' && target ? { target_record_id: target } : {}),
    ...(kind === 'duplicate' && duplicate ? { duplicate_record_id: duplicate } : {}),
    ...(kind === 'facility' && text(draft.label) ? { label: draft.label.trim() } : {}),
    ...(kind === 'facility' && text(draft.countryCode) ? { country_code: draft.countryCode.trim().toUpperCase() } : {}),
    ...(kind === 'facility' && text(draft.locality) ? { locality: draft.locality.trim() } : {}),
    ...(kind === 'facility' && text(draft.claimedActivity) ? { claimed_activity: draft.claimedActivity.trim() } : {}),
    ...(locationKind ? { claimed_precision: draft.precision } : {}),
    ...(locationKind && text(draft.locationText) ? { location_text: draft.locationText.trim() } : {}),
    ...(hasPoint ? { claimed_latitude: draft.latitude!, claimed_longitude: draft.longitude!, location_input_method: draft.locationInputMethod ?? 'text' as const } : {}),
    ...(locationKind && !hasPoint && draft.precision !== 'unmapped' && text(draft.locationText) ? { location_input_method: 'text' as const } : {}),
    ...(text(draft.sourceUrl) && kind !== 'bug' ? { source_url: draft.sourceUrl.trim() } : {}),
    ...(['facility', 'evidence'].includes(kind) && text(draft.observedOn) ? { observed_on: draft.observedOn } : {}),
    ...(text(draft.description) ? { description: draft.description.trim() } : {}),
    ...(text(draft.contactEmail) ? { contact_email: draft.contactEmail.trim() } : {}),
    ...(kind === 'bug' ? { reproduction_steps: draft.reproductionSteps.trim(),
      ...(text(draft.expectedBehavior) ? { expected_behavior: draft.expectedBehavior.trim() } : {}),
      ...(text(draft.pageUrl) ? { page_url: draft.pageUrl.trim() } : {}) } : {}),
  };
  validateContributionDraft(payload);
  return payload;
}
export function trackingHref(receipt: Receipt, returnMapHref = '#/map'): string {
  const params = new URLSearchParams({ submission_id: receipt.submission_id, receipt_secret: receipt.receipt_secret });
  if (returnMapHref !== '#/map') params.set('map', returnMapHref);
  return `#/contribution-status?${params}`;
}
export function readTrackingLink(value: string): { submissionId: string; secret: string } | null {
  try {
    const fragment = value.includes('#') ? value.slice(value.indexOf('#') + 1) : value;
    if (fragment.split('?')[0] !== '/contribution-status') return null;
    const params = new URLSearchParams(fragment.split('?')[1] ?? '');
    const submissionId = params.get('submission_id') ?? '', secret = params.get('receipt_secret') ?? '';
    return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(submissionId) && secret.trim() && secret.length <= 80 ? { submissionId, secret } : null;
  } catch { return null; }
}
