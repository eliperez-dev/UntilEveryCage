import { describe, expect, it, vi } from 'vitest';
import { CommunityError, createCommunityRepository, validateContributionDraft, type ContributionDraft } from '../../src/api/CommunityRepository';
import { normalizeClaimedPoint } from '../../src/map/claimedPoint';

const id = '18c6ef3a-28cd-4c8e-a9bb-3951f45f210d';
const accepted: ContributionDraft = { kind: 'facility', label: 'Synthetic demonstration facility', country_code: 'DK', source_url: 'https://example.test/source', consent: true };

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
}

describe('community contribution repository', () => {
  it('validates required structured claims and accepts an optional paired pin', () => {
    expect(() => validateContributionDraft(accepted)).not.toThrow();
    expect(() => validateContributionDraft({ ...accepted, claimed_latitude: 55.7, claimed_longitude: 12.5, claimed_precision: 'coarse' })).not.toThrow();
    expect(() => validateContributionDraft({ ...accepted, claimed_latitude: 55.7 })).toThrow(CommunityError);
    expect(() => validateContributionDraft({ ...accepted, source_url: 'https://user:pass@example.test/source' })).toThrow(CommunityError);
    expect(() => validateContributionDraft({ ...accepted, kind: 'duplicate', target_record_id: id, duplicate_record_id: id })).toThrow(CommunityError);
    expect(() => validateContributionDraft({ ...accepted, claimed_latitude: 55.7, location_input_method: 'manual_pin' })).toThrow(CommunityError);
    expect(() => validateContributionDraft({ ...accepted, claimed_latitude: 55.7, claimed_longitude: 12.5, location_input_method: 'manual_pin' })).not.toThrow();
  });

  it('accepts minimal facility claims and evidence with either a source or a description', () => {
    expect(() => validateContributionDraft({ kind: 'facility', label: 'Synthetic name only', consent: true })).not.toThrow();
    expect(() => validateContributionDraft({ kind: 'evidence', target_record_id: id, description: 'Synthetic observation', consent: true })).not.toThrow();
    expect(() => validateContributionDraft({ kind: 'evidence', target_record_id: id, source_url: 'https://example.test/evidence', consent: true })).not.toThrow();
    expect(() => validateContributionDraft({ kind: 'evidence', target_record_id: id, consent: true })).toThrow(CommunityError);
  });

  it('normalizes map-picked longitudes and rejects non-finite or out-of-range latitude', () => {
    expect(normalizeClaimedPoint(55.6761119, 190.1234567)).toEqual({ latitude: 55.676112, longitude: -169.876543 });
    expect(normalizeClaimedPoint(91, 12)).toBeNull();
    expect(normalizeClaimedPoint(Number.NaN, 12)).toBeNull();
  });

  it('posts a structured claim without logging it and displays only a validated one-time receipt', async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({ submission_id: id, receipt_secret: 'synthetic-once-only', status: 'received' }));
    const receipt = await createCommunityRepository(fetcher).submit(accepted);
    expect(receipt).toEqual({ submission_id: id, receipt_secret: 'synthetic-once-only', status: 'received' });
    expect(fetcher).toHaveBeenCalledOnce();
    const [, init] = fetcher.mock.calls[0]!;
    expect(init?.cache).toBe('no-store');
    expect(JSON.parse(String(init?.body))).toEqual(accepted);
    expect(JSON.stringify(init)).not.toContain('synthetic-once-only');
  });

  it('keeps receipt status in a POST body and never places it in a URL', async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL) => response({ submission_id: id, status: 'held', public_record_url: `/api/v2/locations/${id}?profile=community&release_id=pilot-synthetic` }));
    const result = await createCommunityRepository(fetcher).status(id, 'synthetic-secret');
    expect(result).toEqual({ submission_id: id, status: 'held', public_record_url: `/api/v2/locations/${id}?profile=community&release_id=pilot-synthetic` });
    const [input, init] = fetcher.mock.calls[0]!;
    expect(String(input)).toBe('/api/community/status');
    expect(init?.method).toBe('POST');
    expect(init?.cache).toBe('no-store');
    expect(JSON.parse(String(init?.body))).toEqual({ submission_id: id, receipt_secret: 'synthetic-secret' });
  });

  it('requests an operator-only queue with a bounded limit and excludes private contact and receipt fields', async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL) => response({
      pending_count: 1,
      submissions: [{ submission_id: id, kind: 'correction', status: 'received', created_at: '2026-10-01T12:00:00Z', target_record_id: id, description: 'Synthetic correction', location_text: null, claimed_latitude: null, claimed_longitude: null, claimed_precision: 'unknown', location_input_method: null, contact_email: 'private@example.test', receipt_secret_hash: 'never-return-this' }],
    }));
    const result = await createCommunityRepository(fetcher).queue('synthetic-operator-token', 200);
    expect(String(fetcher.mock.calls[0]?.[0])).toBe('/api/private/community/submissions?limit=50');
    expect(result.submissions[0]).toMatchObject({ submission_id: id, description: 'Synthetic correction' });
    expect(result.submissions[0]).not.toHaveProperty('contact_email');
    expect(result.submissions[0]).not.toHaveProperty('receipt_secret_hash');
    expect(JSON.stringify(result)).not.toContain('private@example.test');
  });

  it('defaults the operator queue to pending and passes an explicit status filter', async () => {
    const fetcher = vi.fn(async (_input: RequestInfo | URL) => response({ pending_count: 1, submissions: [] }));
    const repository = createCommunityRepository(fetcher);
    await repository.queue('synthetic-operator-token');
    expect(String(fetcher.mock.calls[0]?.[0])).toBe('/api/private/community/submissions?limit=50');
    await repository.queue('synthetic-operator-token', 20, 'screened');
    expect(String(fetcher.mock.calls[1]?.[0])).toBe('/api/private/community/submissions?limit=20&status=screened');
  });

  it('accepts only same-origin, community-profile links with the requested release scope', async () => {
    const claim = { submission_id: id, kind: 'facility', record_id: id, release_id: 'pilot-synthetic', public_record_url: `/api/v2/locations/${id}?profile=community&release_id=pilot-synthetic`, origin: 'community-submitted', factual_review_status: 'unreviewed', project_approval: 'not-approved', warning: 'Unreviewed community claim — not verified by Until Every Cage.' };
    const fetcher = vi.fn(async (_input: RequestInfo | URL) => response({ claims: [claim], claim_count: 1, warning: claim.warning }));
    const result = await createCommunityRepository(fetcher).claims('pilot-synthetic');
    expect(result.claims[0]?.public_record_url).toBe(claim.public_record_url);
    const badFetcher = vi.fn(async (_input: RequestInfo | URL) => response({ claims: [{ ...claim, public_record_url: `https://attacker.example/${id}?profile=community&release_id=pilot-synthetic` }], claim_count: 1, warning: claim.warning }));
    await expect(createCommunityRepository(badFetcher).claims('pilot-synthetic')).rejects.toMatchObject({ category: 'invalid' });
  });

  it('marks service requests no-store and turns error bodies into generic safe messages', async () => {
    const fetcher = vi.fn(async () => response({ error: 'Synthetic private server detail', address: 'Synthetic private value' }, 500));
    await expect(createCommunityRepository(fetcher).submit(accepted)).rejects.toMatchObject({ category: 'unavailable' });
    expect(fetcher.mock.calls[0]?.[1]?.cache).toBe('no-store');
  });

  it('maps allowlisted validation messages to useful guidance without echoing server text', async () => {
    const badRequest = vi.fn(async () => response({ error: { code: 'invalid_submission', message: 'facility requires a label' } }, 400));
    await expect(createCommunityRepository(badRequest).submit(accepted)).rejects.toMatchObject({ category: 'invalid', message: 'Add a facility name.' });

    for (const message of ['<script>synthetic-secret</script>', '__proto__', 'constructor']) {
      const malicious = vi.fn(async () => response({ error: { message } }, 422));
      const repository = createCommunityRepository(malicious);
      let caught: unknown;
      try { await repository.submit(accepted); } catch (error) { caught = error; }
      expect(caught).toBeInstanceOf(CommunityError);
      expect((caught as Error).message).not.toContain(message);
    }
  });

  it('distinguishes capacity, missing receipts, service failures, and network errors', async () => {
    const atCapacity = createCommunityRepository(vi.fn(async () => response({}, 429)));
    await expect(atCapacity.submit(accepted)).rejects.toMatchObject({ category: 'unavailable', message: 'Submissions are temporarily at capacity. Please try again later.' });

    const missingReceipt = createCommunityRepository(vi.fn(async () => response({}, 404)));
    await expect(missingReceipt.status(id, 'synthetic-receipt')).rejects.toMatchObject({ category: 'invalid', message: 'No active submission matches that receipt. Check the values and try again.' });

    const serviceFailure = createCommunityRepository(vi.fn(async () => response({ error: { message: 'synthetic private detail' } }, 503)));
    await expect(serviceFailure.submit(accepted)).rejects.toMatchObject({ category: 'unavailable' });
    await expect(serviceFailure.submit(accepted)).rejects.not.toThrow('synthetic private detail');

    const networkFailure = createCommunityRepository(vi.fn(async () => { throw new Error('synthetic connection detail'); }));
    await expect(networkFailure.submit(accepted)).rejects.toMatchObject({ category: 'network' });
  });
});
