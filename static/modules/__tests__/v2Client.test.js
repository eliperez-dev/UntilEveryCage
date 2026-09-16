import { jest } from '@jest/globals';
import { V2ApiError, V2Client } from '../v2Client.js';
import { escapeHtml, normalizeV2Location } from '../v2Adapter.js';
import { validateV2Envelope, validateV2Location } from '../v2Contract.js';
import { exportManager } from '../ExportManager.js';
import { buildLocationPopup } from '../popupBuilder.js';
import { exactOfficialLocation, noPromotedRelease, restrictedLocation } from '../__fixtures__/v2-contract-fixtures.js';

const listPayload = (data = [], meta = {}) => ({ api_version: 'v2', data, meta });
const record = (overrides = {}) => ({
    facility_id: '00000000-0000-0000-0000-000000000001',
    canonical_name: 'Example facility',
    country_code: 'DK',
    city: 'Copenhagen',
    category: 'slaughter',
    display_precision: 'city',
    latitude: 55.67,
    longitude: 12.56,
    publication_profile: 'official',
    factual_review_status: 'reviewed',
    privacy_screening_status: 'passed',
    project_approval: 'approved',
    reviewer_role: 'maintainer',
    publication_warning: null,
    source_type: 'official',
    source_rights_status: 'attribution_required',
    provenance_source: 'Test source',
    release_id: 'fixture-release',
    release_ruleset_version: 'fixture-v1',
    provenance_source_id: 'fixture.source',
    provenance_source_name: 'Test source',
    provenance_source_url: 'https://example.test/source',
    provenance_retrieved_at: '2026-09-13T00:00:00Z',
    lifecycle_status: 'active_observed',
    first_observed_at: '2026-09-13T00:00:00Z',
    last_observed_at: '2026-09-13T00:00:00Z',
    observation_count: 1,
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

test('contract accepts a complete eligible synthetic location', () => {
    expect(validateV2Location(exactOfficialLocation)).toBe(exactOfficialLocation);
    expect(validateV2Envelope({ data: [exactOfficialLocation], api_version: 'v2', meta: { profile: 'official' } })).toBeTruthy();
});

test('contract preserves explicit no-release state without inventing records', () => {
    expect(validateV2Envelope(noPromotedRelease).data).toEqual([]);
});

test('contract rejects privacy-ineligible records before rendering', () => {
    expect(() => validateV2Location(restrictedLocation)).toThrow('not privacy eligible');
});

test('rejects a row whose publication profile differs from the response profile', async () => {
    const body = listPayload([record({ publication_profile: 'secondary' })], { profile: 'official' });
    expect(() => validateV2Envelope(body)).toThrow('publication_profile');
    fetch.mockResolvedValue({ ok: true, json: async () => body });
    await expect(new V2Client('/api/v2/locations').list({ profile: 'official' })).rejects.toThrow('publication_profile');
});

test('rejects a response for a different profile than the one requested', async () => {
    const community = record({ publication_profile: 'community', project_approval: 'not_approved', source_type: 'user_submitted' });
    fetch.mockResolvedValue({ ok: true, json: async () => listPayload([community], { profile: 'community' }) });
    await expect(new V2Client('/api/v2/locations').list({ profile: 'official' })).rejects.toThrow('profile');
});

test('V2 CSV rows retain per-record publication and source context', () => {
    const loc = normalizeV2Location(record({ publication_warning: 'Synthetic limitation', reviewer_role: 'community reviewer' }), { profile: 'official', coverage_note: 'Synthetic coverage' });
    const row = exportManager.normalizeUsdaRow(loc, true);
    const csv = exportManager.toCsv([row]);
    for (const value of ['publication_profile', 'factual_review_status', 'reviewer_role', 'project_approval',
        'source_type', 'provenance_source_id', 'provenance_source_url', 'provenance_retrieved_at',
        'release_id', 'release_ruleset_version', 'publication_warning']) {
        expect(csv).toContain(value);
    }
    expect(csv).toContain('Synthetic limitation');
    expect(csv).toContain('fixture.source');
    expect(row.publication_profile).toBe('official');
    expect(row.factual_review_status).toBe('reviewed');
    expect(row.project_approval).toBe('approved');
    expect(row.selected_profile).toBe('official');
});

test('V1 CSV row retains its legacy columns only', () => {
    const row = exportManager.normalizeUsdaRow({ establishment_name: 'Synthetic legacy facility', latitude: 1, longitude: 2 }, true);
    expect(row.Name).toBe('Synthetic legacy facility');
    expect(row).not.toHaveProperty('publication_profile');
    expect(row).not.toHaveProperty('export_scope');
});

test('paginated V2 export never claims the visible first page is complete', () => {
    const download = jest.spyOn(exportManager, 'downloadText').mockImplementation(() => {});
    const loc = normalizeV2Location(record(), { profile: 'official' });
    exportManager.exportData({ slaughterhouses: [loc] }, {
        includeSlaughter: true, isComplete: true, apiVersion: 'v2',
        v2Meta: { profile: 'official', next_cursor: 'cursor-2', coverage_note: 'Synthetic limited coverage' }
    });
    expect(download).toHaveBeenCalledTimes(1);
    expect(download.mock.calls[0][0]).not.toContain('complete');
    expect(download.mock.calls[0][1]).toContain('Synthetic limited coverage');
    expect(download.mock.calls[0][1]).toContain('partial_page');
    expect(download.mock.calls[0][1]).toContain('Additional pages may be available');
    expect(download.mock.calls[0][1]).toContain('selected_profile');
    download.mockRestore();
});

test('city-precision V2 popup has no directions link while exact V2 and V1 keep it', () => {
    const city = normalizeV2Location(record({ display_precision: 'city' }), { profile: 'official' });
    const exact = normalizeV2Location(record({ display_precision: 'exact' }), { profile: 'official' });
    const legacy = { establishment_name: 'Synthetic legacy facility', latitude: 55, longitude: 12, city: 'Testby' };
    expect(buildLocationPopup(city, 'Facility')).not.toContain('maps/dir/');
    expect(buildLocationPopup(exact, 'Facility')).toContain('maps/dir/');
    expect(buildLocationPopup(legacy, 'Facility')).toContain('maps/dir/');
    expect(buildLocationPopup(normalizeV2Location(record({ display_precision: 'exact', latitude: null, longitude: null })), 'Facility')).not.toContain('maps/dir/');
});
