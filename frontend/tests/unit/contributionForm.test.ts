import { describe, expect, it } from 'vitest';
import { buildIntakePayload, createIntakeDrafts, emptyIntakeDraft, readTrackingLink, trackingHref, validateIntakeDraft } from '../../src/app/contributions/contributionForm';
const id = '18c6ef3a-28cd-4c8e-a9bb-3951f45f210d', second = '27d7ef4b-39de-4d9f-bacc-4062f560321e';
describe('contribution intake model', () => {
  it('keeps task drafts independent and emits a minimal facility without invented location', () => {
    const drafts = createIntakeDrafts();
    drafts.facility.label = 'Synthetic name'; drafts.facility.consent = true;
    drafts.evidence.description = 'Synthetic evidence';
    expect(drafts.correction.description).toBe('');
    expect(buildIntakePayload('facility', drafts.facility)).toEqual({ kind: 'facility', consent: true, label: 'Synthetic name', claimed_precision: 'unknown' });
    expect(() => buildIntakePayload('facility', emptyIntakeDraft())).toThrow();
  });
  it('preserves structured facility fields and assigns country and locality separately', () => {
    const draft = { ...emptyIntakeDraft(), label: ' Synthetic place ', consent: true, countryCode: 'dk', locality: 'Synthetic locality', claimedActivity: 'slaughter', locationText: 'Synthetic broad area', latitude: 55, longitude: 12, precision: 'coarse' as const, locationInputMethod: 'manual_pin' as const, sourceUrl: 'https://example.test/source', observedOn: '2026-10-01', description: 'Synthetic note', contactEmail: 'synthetic@example.test' };
    expect(buildIntakePayload('facility', draft)).toMatchObject({ label: 'Synthetic place', country_code: 'DK', locality: 'Synthetic locality', claimed_activity: 'slaughter', location_text: 'Synthetic broad area', claimed_latitude: 55, claimed_longitude: 12, claimed_precision: 'coarse', location_input_method: 'manual_pin', source_url: draft.sourceUrl, observed_on: draft.observedOn, description: draft.description, contact_email: draft.contactEmail });
    expect(buildIntakePayload('facility', { ...draft, precision: 'unmapped' })).not.toHaveProperty('claimed_latitude');
  });
  it.each(['evidence', 'correction', 'duplicate', 'privacy_removal'] as const)('accepts a pasted target for %s without requiring public lookup', kind => {
    const draft = { ...emptyIntakeDraft(), consent: true, targetReference: `https://example.test/#/records/${id}`, duplicateReference: `#/locations/${second}`, description: 'Synthetic explanation' };
    expect(validateIntakeDraft(kind, draft)).toEqual({});
    expect(buildIntakePayload(kind, draft)).toMatchObject({ kind, target_record_id: id, description: draft.description });
    if (kind === 'duplicate') expect(buildIntakePayload(kind, draft).duplicate_record_id).toBe(second);
  });
  it('retains typed bug fields without admitting unrelated structured facility fields', () => {
    const draft = { ...emptyIntakeDraft(), label: 'Ignored facility field', countryCode: 'DK', description: 'Synthetic bug', reproductionSteps: 'Synthetic steps', expectedBehavior: 'Synthetic expected', pageUrl: 'https://example.test/page' };
    expect(buildIntakePayload('bug', draft)).toEqual({ kind: 'bug', consent: true, description: draft.description, reproduction_steps: draft.reproductionSteps, expected_behavior: draft.expectedBehavior, page_url: draft.pageUrl });
  });
  it('identifies actionable errors without echoing raw values', () => {
    expect(validateIntakeDraft('evidence', emptyIntakeDraft())).toMatchObject({ targetReference: expect.any(String), description: expect.any(String), consent: expect.any(String) });
    const draft = { ...emptyIntakeDraft(), consent: true, label: 'Synthetic', sourceUrl: 'https://name:private@example.test', latitude: 91, longitude: 12 };
    expect(validateIntakeDraft('facility', draft)).toMatchObject({ sourceUrl: expect.any(String), latitude: expect.any(String) });
    expect(JSON.stringify(validateIntakeDraft('facility', draft))).not.toContain('private');
    expect(validateIntakeDraft('duplicate', { ...draft, targetReference: id, duplicateReference: id })).toHaveProperty('duplicateReference');
  });
  it('keeps capability credentials inside the router fragment and preserves map context', () => {
    const receipt = { submission_id: id, receipt_secret: 'synthetic-secret', status: 'received' as const };
    const map = '#/map?lat=44.5&lon=8.1&z=5';
    const href = trackingHref(receipt, map);
    const url = new URL(href, 'https://example.test/');
    expect(url.search).toBe('');
    expect(readTrackingLink(url.href)).toEqual({ submissionId: id, secret: receipt.receipt_secret });
    expect(new URLSearchParams(url.hash.split('?')[1]).get('map')).toBe(map);
    expect(readTrackingLink(`https://example.test/?submission_id=${id}&receipt_secret=synthetic-secret`)).toBeNull();
    expect(readTrackingLink(`#/other?submission_id=${id}&receipt_secret=synthetic-secret`)).toBeNull();
    expect(readTrackingLink(`#/contribution-status?submission_id=${id}`)).toBeNull();
  });
});
