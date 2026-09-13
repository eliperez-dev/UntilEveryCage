import { API_ENDPOINTS } from './constants.js';
import { normalizeV2Location } from './v2Adapter.js';
import { validateV2Envelope } from './v2Contract.js';

function endpoint() {
    const local = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    return local ? API_ENDPOINTS.local.v2Locations : API_ENDPOINTS.production.v2Locations;
}

export class V2ApiError extends Error {
    constructor(message, status = 0) {
        super(message);
        this.name = 'V2ApiError';
        this.status = status;
    }
}

export class V2Client {
    constructor(baseUrl = endpoint()) {
        this.baseUrl = baseUrl;
    }

    async request(path = '', params = {}, signal) {
        const query = new URLSearchParams();
        Object.entries(params).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') query.set(key, value);
        });
        const suffix = query.toString() ? `?${query}` : '';
        const response = await fetch(`${this.baseUrl}${path}${suffix}`, {
            signal,
            headers: { Accept: 'application/json' }
        });
        if (!response.ok) throw new V2ApiError(`V2 request failed: HTTP ${response.status}`, response.status);
        const body = await response.json();
        let isList;
        try {
            validateV2Envelope(body);
            isList = Array.isArray(body.data);
        } catch (error) {
            throw new V2ApiError(`V2 response did not match the public API contract: ${error.message}`);
        }
        const isDetail = !isList;
        return {
            records: isList ? body.data.map(record => normalizeV2Location(record, body.meta || {})) : [normalizeV2Location(body.data, body.meta || {})],
            meta: body.meta || {},
            apiVersion: body.api_version,
            isDetail
        };
    }

    list(params = {}, signal) {
        return this.request('', params, signal);
    }

    detail(facilityId, profile, signal) {
        return this.request(`/${encodeURIComponent(facilityId)}`, { profile }, signal);
    }
}

export const v2Client = new V2Client();
