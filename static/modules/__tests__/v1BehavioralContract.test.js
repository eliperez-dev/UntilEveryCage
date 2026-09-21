import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

const root = process.cwd();
const contractPath = resolve(root, 'docs/frontend/v1-behavioral-contract.json');
const prosePath = resolve(root, 'docs/frontend/v1-behavioral-contract.md');

const contract = JSON.parse(readFileSync(contractPath, 'utf8'));
const prose = readFileSync(prosePath, 'utf8');
const source = (files) => files.map((file) => readFileSync(resolve(root, file), 'utf8')).join('\n');

test('V1 behavioral contract has a stable identity and complete requirement inventory', () => {
    expect(contract.contract_id).toBe('uec-v1-behavioral-contract');
    expect(contract.contract_version).toBe('1.0.0');
    expect(contract.status).toBe('baseline-for-v2-reconciliation');
    expect(Array.isArray(contract.requirements)).toBe(true);
    expect(contract.requirements.length).toBeGreaterThanOrEqual(20);

    const ids = contract.requirements.map((requirement) => requirement.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toEqual(expect.arrayContaining([
        'V1-SEARCH-001', 'V1-SEARCH-002', 'V1-GEO-001', 'V1-GEO-002',
        'V1-TYPE-001', 'V1-DISCOVERY-001', 'V1-MAP-001', 'V1-MAP-002',
        'V1-URL-001', 'V1-URL-002', 'V1-RESET-001', 'V1-EXPORT-001',
        'V1-COVERAGE-001', 'V1-ACTION-001', 'V1-I18N-001',
        'V1-APHIS-001', 'V1-APHIS-002', 'V2-PRIVACY-001', 'V2-PRIVACY-002',
        'V2-DEFER-001', 'V2-DEFER-002', 'V2-DEFER-003'
    ]));
});

test('prose and JSON remain aligned on every requirement and disposition', () => {
    const dispositions = new Set([
        'preserve_user_critical',
        'v2_privacy_review_replacement',
        'deferred_to_eli_v2_frontend_overhaul'
    ]);

    for (const requirement of contract.requirements) {
        expect(prose).toContain('`' + requirement.id + '`');
        expect(dispositions.has(requirement.disposition)).toBe(true);
        expect(requirement.title).toBeTruthy();
        expect(requirement.observed_behavior).toBeTruthy();
        expect(requirement.acceptance).toBeTruthy();
        expect(requirement.evidence.length).toBeGreaterThan(0);
        for (const file of requirement.evidence) {
            expect(existsSync(resolve(root, file))).toBe(true);
        }
    }

    expect(prose).toContain('preserve_user_critical');
    expect(prose).toContain('v2_privacy_review_replacement');
    expect(prose).toContain('deferred_to_eli_v2_frontend_overhaul');
});

test('the contract covers each required behavior family', () => {
    const areas = new Set(contract.requirements.map((requirement) => requirement.area));
    for (const area of [
        'search', 'geography', 'facility-types', 'discovery', 'map',
        'share-state', 'reset', 'export', 'coverage', 'detail-actions',
        'language', 'aphis', 'v2-replacement', 'v2-overhaul'
    ]) {
        expect(areas.has(area)).toBe(true);
    }
});

test('the search contract is grounded in the actual V1 fields and controls', () => {
    const implementation = source([
        'static/modules/FilterManager.js',
        'static/modules/SearchManager.js',
        'static/index.html'
    ]);

    for (const field of [
        'establishment_name', 'dbas', 'animals_slaughtered', 'animals_processed',
        'Animals Tested On', 'Account Name', 'License Type', 'slaughterhousesCheckbox',
        'meatProcessingPlantsCheckbox', 'testingLabsCheckbox', 'breedersCheckbox',
        'dealersCheckbox', 'exhibitorsCheckbox'
    ]) {
        expect(implementation).toContain(field);
    }
    expect(implementation).toContain("'cow': 'cattle'");
    expect(implementation).toContain("'cows': 'cattle'");
});

test('map, URL, reset, and visible-export claims are grounded in V1 code', () => {
    const app = readFileSync(resolve(root, 'static/app.js'), 'utf8');
    const map = readFileSync(resolve(root, 'static/modules/MapManager.js'), 'utf8');
    const html = readFileSync(resolve(root, 'static/index.html'), 'utf8');
    const exportCode = readFileSync(resolve(root, 'static/modules/ExportManager.js'), 'utf8');

    for (const param of ['lat', 'lng', 'zoom', 'country', 'state', 'search', 'layers']) {
        expect(app).toContain(param);
    }
    for (const behavior of ['Link Copied!', 'isComplete', 'lastFilteredData']) {
        expect(app).toContain(behavior);
    }
    expect(html).toContain('id="reset-filters-btn"');
    expect(map).toContain('unifiedClusterLayer');
    expect(map).toContain('markerClusterGroup');
    expect(html).toContain('id="cluster-threshold-slider"');
    expect(exportCode).toContain('visible_results');
    expect(exportCode).toContain('partial_page');
    expect(prose).toContain('visible-results versus complete-coverage');
});

test('popup, language, and lazy APHIS claims are grounded in V1 code', () => {
    const popup = readFileSync(resolve(root, 'static/modules/popupBuilder.js'), 'utf8');
    const app = readFileSync(resolve(root, 'static/app.js'), 'utf8');
    const translation = readFileSync(resolve(root, 'static/modules/translationManager.js'), 'utf8');

    for (const behavior of [
        'copyable-text', 'getDirections', 'viewSource', 'loadAphisReports',
        'filterAnnualReports', 'aphisQuery', 'aphisLoading', 'aphisNoResults',
        'aphisError', 'Link Copied!'
    ]) {
        expect(popup + app).toContain(behavior);
    }
    expect(translation).toContain('setLanguage');
    for (const locale of ['de', 'en', 'es', 'fr']) {
        expect(existsSync(resolve(root, `static/locales/${locale}.json`))).toBe(true);
    }
});

test('privacy/review replacement and V2 deferral are explicit', () => {
    const privacy = contract.requirements.filter((requirement) => requirement.disposition === 'v2_privacy_review_replacement');
    const deferred = contract.requirements.filter((requirement) => requirement.disposition === 'deferred_to_eli_v2_frontend_overhaul');
    expect(privacy.map((requirement) => requirement.id)).toEqual(expect.arrayContaining(['V1-COVERAGE-001', 'V1-ACTION-001', 'V2-PRIVACY-001', 'V2-PRIVACY-002']));
    expect(deferred.map((requirement) => requirement.id)).toEqual(expect.arrayContaining(['V2-DEFER-001', 'V2-DEFER-002', 'V2-DEFER-003']));
    expect(prose).toContain('Government-sourced does not mean project-approved');
    expect(prose).toContain('No CSS or visual redesign is part of this lane');
    expect(prose).toContain('It intentionally does not redesign');
});
