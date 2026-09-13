import { jest } from '@jest/globals';
import { V2ApiError, V2Client } from '../v2Client.js';
import { escapeHtml, normalizeV2Location } from '../v2Adapter.js';

const listPayload = (data = [], meta = {}) => ({ api_version: 'v2', data, meta });
const record = (overrides = {}) => ({
    facility_id: '00000000-0000-0000-0000-000000000001',
    canonical_name: 'Example facility',
    country_code: 'DK',
    city: 'Copenhagen',
    display_precision: 'city',
    latitude: 55.67,
    longitude: 12.56,
    source_type: 'official',
    provenance_source_name: 'Test source',
    provenance_source_url: 'https://example.test/source',
    provenance_retrieved_at: '2026-09-13T00:00:00Z',
    lifecycle_status: 'active_observed',
    ...overrides
});

beforeEach(() => { global.fetch = jest.fn(); });

test('parses list envelopes and preserves cursor metadata', async () => {
    fetch.mockResolvedValue({ ok: true, json: async () => listPayload([record()], { next_cursor: 'cursor-2', profile: 'official' }) });
    const result = await new V2Client('/api/v2/locations').list({ profile: 'official', limit: 1 });
    expect(result.records).toHaveLength(1);
    expect(result.meta.next_cursor).toBe('cursor-2');
    expect(fetch.mock.calls[0][0]).toContain('profile=official');
});

test('parses detail envelopes with a single data object', async () => {
    fetch.mockResolvedValue({ ok: true, json: async () => ({ api_version: 'v2', data: record(), meta: { profile: 'official' } }) });
    const result = await new V2Client('/api/v2/locations').detail(record().facility_id, 'official');
    expect(result.isDetail).toBe(true);
    expect(result.records[0].v2.profile).toBe('official');
});

test('rejects malformed payloads and preserves HTTP status', async () => {
    fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ data: [] }) });
    await expect(new V2Client().list()).rejects.toThrow('did not match');
    fetch.mockResolvedValueOnce({ ok: false, status: 404 });
    await expect(new V2Client().detail('missing')).rejects.toMatchObject({ status: 404 });
});

test('represents an empty no-promoted-release response without inventing records', async () => {
    fetch.mockResolvedValue({ ok: true, json: async () => listPayload([], { release_id: null, coverage_note: 'No promoted release is currently available.' }) });
    const result = await new V2Client().list({ profile: 'official' });
    expect(result.records).toEqual([]);
    expect(result.meta.release_id).toBeNull();
});

test('normalizes provenance and escapes untrusted values', () => {
    const normalized = normalizeV2Location(record({ canonical_name: '<img src=x onerror=alert(1)>' }));
    expect(normalized.v2.provenance.source_url).toBe('https://example.test/source');
    expect(escapeHtml(normalized.establishment_name)).toContain('&lt;img');
    expect(escapeHtml('"quoted" & <unsafe>')).toBe('&quot;quoted&quot; &amp; &lt;unsafe&gt;');
});

test('does not permit unsupported profiles through the data manager profile guard', async () => {
    const { dataManager } = await import('../DataManager.js');
    expect(() => dataManager.setV2Profile('community')).toThrow('not available');
    expect(() => dataManager.setV2Profile('unsupported')).toThrow('not available');
});

test('V2 requests cannot override the official profile', async () => {
    const { dataManager } = await import('../DataManager.js');
    dataManager.v2Profile = 'official';
    dataManager.v2Meta = { next_cursor: null };
    fetch.mockResolvedValue({ ok: true, json: async () => listPayload([], { release_id: null }) });
    await dataManager.fetchV2Page({ profile: 'community', category: 'slaughter' });
    expect(fetch.mock.calls.at(-1)[0]).toContain('profile=official');
    expect(fetch.mock.calls.at(-1)[0]).not.toContain('profile=community');
});
