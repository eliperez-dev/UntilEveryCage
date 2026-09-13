/**
 * Data Manager Module
 * 
 * Handles fetching, processing, and storing application data.
 */

import { API_ENDPOINTS, useV2Api } from './constants.js';
import { v2Client } from './v2Client.js';
import { getStateFromCityStateZip } from './geoUtils.js';

class DataManager {
    constructor() {
        this.allLocations = [];
        this.allLabLocations = [];
        this.allInspectionReports = [];
        this.isInitialDataLoading = true;
        this.apiVersion = 'v1';
        this.v2Meta = null;
        this.v2Profile = 'official';
        this.v2Filters = {};
        this.v2Status = 'idle';
        this.v2Error = null;
        this.v2HasMore = false;
    }

    /**
     * Fetch all required data from APIs
     * @param {Function} progressCallback - Callback to update loading progress (percentage, message)
     * @returns {Promise<void>}
     */
    async fetchData(progressCallback) {
        const updateProgress = (pct, msg) => {
            if (progressCallback) progressCallback(pct, msg);
        };

        try {
            updateProgress(0, "Fetching facility data...");
            
            // Determine which environment we are in
            const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
            
            const urls = isLocal ? [
                API_ENDPOINTS.local.locations,
                API_ENDPOINTS.local.aphisReports,
                API_ENDPOINTS.local.inspectionReports
            ] : [
                API_ENDPOINTS.production.locations,
                API_ENDPOINTS.production.aphisReports,
                API_ENDPOINTS.production.inspectionReports
            ];
            
            let usdaResponse, aphisResponse, inspectionsResponse;

            if (useV2Api()) {
                updateProgress(30, "Loading the promoted V2 release...");
                await this.fetchV2Page();
                updateProgress(100, "Done!");
                this.isInitialDataLoading = false;
                return;
            }
            
            // Create AbortController for timeout handling
            const abortController = new AbortController();
            const timeoutId = setTimeout(() => abortController.abort(), 30000); // 30 second timeout
            
            [usdaResponse, aphisResponse, inspectionsResponse] = await Promise.all([
                fetch(urls[0], { 
                    signal: abortController.signal,
                    headers: { 'Accept': 'application/json' }
                }),
                fetch(urls[1], { 
                    signal: abortController.signal,
                    headers: { 'Accept': 'application/json' }
                }),
                fetch(urls[2], { 
                    signal: abortController.signal,
                    headers: { 'Accept': 'application/json' }
                })
            ]);
            
            clearTimeout(timeoutId);

            updateProgress(50, "Processing responses...");

            if (!usdaResponse.ok) throw new Error(`Data request failed`);
            if (!aphisResponse.ok) throw new Error(`APHIS data request failed`);
            if (!inspectionsResponse.ok) throw new Error(`Inspections data request failed`);

            updateProgress(30, "Loading facility locations...");
            this.allLocations = await usdaResponse.json();
            
            updateProgress(70, "Loading APHIS reports...");
            this.allLabLocations = await aphisResponse.json();
            
            updateProgress(80, "Loading inspection reports...");
            this.allInspectionReports = await inspectionsResponse.json();
            
            this.processLocations();
            
            updateProgress(100, "Done!");
            this.isInitialDataLoading = false;

        } catch (error) {
            console.error('Failed to fetch initial data:', error);
            this.isInitialDataLoading = false;
            throw error;
        }
    }

    /**
     * Process locations to add country codes and extract state information
     */
    processLocations() {
        this.allLocations = this.allLocations.map(location => {
            // Create a copy to avoid mutating the original
            let processedLocation = { ...location };
            
            // Set country field based on various detection methods
            if (!processedLocation.country) {
                // Check for Denmark first (simplest detection)
                if (location.county === 'Denmark' || 
                    (location.latitude > 54.5 && location.latitude < 58 && 
                     location.longitude > 8 && location.longitude < 16)) {
                    processedLocation.country = 'dk';
                    // Danish locations don't use state/province system, keep state empty
                    return processedLocation;
                }
                
                // Check for Germany
                if (location.latitude > 47 && location.latitude < 55.2 && 
                    location.longitude > 5 && location.longitude < 16) {
                    processedLocation.country = 'de';
                }
            }
            
            // Process German locations - extract specific German states from establishment IDs
            if (processedLocation.country === 'de' && (!location.state || location.state.trim() === '')) {
                // First try to extract German state from establishment ID (most reliable)
                if (location.establishment_id && typeof location.establishment_id === 'string') {
                    const germanStateMatch = location.establishment_id.match(/^(BW|BY|BE|BB|HB|HH|HE|MV|NI|NW|RP|SL|SN|ST|SH|TH)\s/);
                    if (germanStateMatch) {
                        const germanStateCode = germanStateMatch[1];
                        processedLocation.state = germanStateCode;
                        return processedLocation;
                    }
                }
                
                // If we can't determine the specific German state, use a generic German identifier
                processedLocation.state = 'DE_UNKNOWN';
            }
            
            return processedLocation;
        });
    }

    getAllLocations() {
        return this.allLocations;
    }

    async fetchV2Page(filters = {}, signal) {
        const { profile: ignoredProfile, ...safeFilters } = filters;
        const isContinuation = Boolean(safeFilters.cursor) && safeFilters.cursor === this.v2Meta?.next_cursor;
        const comparableFilters = { ...safeFilters, cursor: undefined };
        const previousFilters = { ...this.v2Filters, cursor: undefined };
        const restart = !isContinuation && JSON.stringify(comparableFilters) !== JSON.stringify(previousFilters);
        this.v2Status = 'loading';
        this.v2Error = null;
        let result;
        try {
            result = await v2Client.list({ profile: 'official', ...safeFilters }, signal);
        } catch (error) {
            this.v2Status = 'error';
            this.v2Error = error;
            throw error;
        }
        this.allLocations = restart ? result.records : [...this.allLocations, ...result.records];
        this.v2Meta = result.meta;
        this.apiVersion = 'v2';
        this.v2Filters = { ...safeFilters, profile: 'official' };
        this.v2HasMore = Boolean(result.meta.next_cursor);
        this.v2Status = result.meta.release_id === null ? 'no_release' : 'ready';
        this.processLocations();
        return result;
    }

    async fetchNextV2Page(signal) {
        if (!this.v2Meta?.next_cursor) {
            this.v2HasMore = false;
            return { records: [], meta: this.v2Meta || {} };
        }
        return this.fetchV2Page({ ...this.v2Filters, cursor: this.v2Meta.next_cursor }, signal);
    }

    setV2Profile(profile) {
        if (profile !== 'official') {
            throw new Error(`V2 profile is not available in the public UI: ${profile}`);
        }
        this.v2Profile = profile;
        this.v2Filters = {};
        this.v2Meta = null;
        this.allLocations = [];
        this.v2Status = 'idle';
        this.v2Error = null;
        this.v2HasMore = false;
    }

    getAllLabLocations() {
        return this.allLabLocations;
    }

    getAllInspectionReports() {
        return this.allInspectionReports;
    }

    getAllStateValues() {
        const values = [...new Set([
            ...this.allLocations.map(loc => loc.state),
            ...this.allLabLocations.map(lab => getStateFromCityStateZip(lab['City-State-Zip'])),
            ...this.allInspectionReports.map(report => report['State'])
        ].filter(Boolean))];
        values.sort();
        return values;
    }
}

export const dataManager = new DataManager();
