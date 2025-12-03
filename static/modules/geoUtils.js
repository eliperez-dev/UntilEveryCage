/**
 * Geographic and Location Utilities Module
 * 
 * This module contains functions for handling geographic data, country/state validation,
 * location categorization, and data normalization for CSV export.
 */

import { 
    US_STATE_NAMES, 
    GERMAN_STATE_NAMES, 
    SPANISH_STATE_NAMES, 
    FRENCH_STATE_NAMES,
    CANADIAN_PROVINCE_NAMES,
    MEXICAN_STATE_NAMES
} from './constants.js';

// --- State/Country Detection Functions ---

/**
 * Get display name for a state code, supporting multiple countries
 * @param {string} stateCode - The state/province code
 * @returns {string} - Display name or original code if not found
 */
export function getStateDisplayName(stateCode) {
    // Return empty string for undefined, null, or empty state codes (like Danish locations)
    if (!stateCode || stateCode.trim() === '') {
        return '';
    }
    
    const normalized = stateCode.toUpperCase();
    
    return US_STATE_NAMES[stateCode] || 
           GERMAN_STATE_NAMES[stateCode] || 
           SPANISH_STATE_NAMES[stateCode] || 
           FRENCH_STATE_NAMES[stateCode] ||
           CANADIAN_PROVINCE_NAMES[stateCode] ||
           MEXICAN_STATE_NAMES[normalized] ||
           stateCode;
}

/**
 * Check if a state code belongs to the United States
 * @param {string} stateCode - The state code to check
 * @returns {boolean} - True if US state
 */
export function isUSState(stateCode) {
    return US_STATE_NAMES.hasOwnProperty(stateCode);
}

/**
 * Check if a state code belongs to Germany
 * @param {string} stateCode - The state code to check
 * @returns {boolean} - True if German state
 */
export function isGermanState(stateCode) {
    return GERMAN_STATE_NAMES.hasOwnProperty(stateCode) || stateCode === 'DE_UNKNOWN';
}

/**
 * Check if a state code belongs to Spain
 * @param {string} stateCode - The state code to check
 * @returns {boolean} - True if Spanish state
 */
export function isSpanishState(stateCode) {
    return SPANISH_STATE_NAMES.hasOwnProperty(stateCode) || stateCode === 'ES_UNKNOWN';
}

/**
 * Check if a state code belongs to France
 * @param {string} stateCode - The state code to check
 * @returns {boolean} - True if French state
 */
export function isFrenchState(stateCode) {
    return FRENCH_STATE_NAMES.hasOwnProperty(stateCode) || stateCode === 'FR_UNKNOWN';
}

/**
 * Check if a state code belongs to Canada
 * @param {string} stateCode - The province code to check
 * @returns {boolean} - True if Canadian province
 */
export function isCanadianProvince(stateCode) {
    return CANADIAN_PROVINCE_NAMES.hasOwnProperty(stateCode);
}

/**
 * Check if a state code belongs to Mexico
 * @param {string} stateCode - The state code to check
 * @returns {boolean} - True if Mexican state
 */
export function isMexicanState(stateCode) {
    return stateCode ? MEXICAN_STATE_NAMES.hasOwnProperty(stateCode.toUpperCase()) : false;
}

/**
 * Check if a location belongs to France
 * @param {Object} location - The location object with country property
 * @returns {boolean} - True if French location
 */
export function isFrenchLocation(location) {
    return location.country === 'fr';
}

/**
 * Check if a location belongs to Canada
 * @param {Object} location - The location object with country property
 * @returns {boolean} - True if Canadian location
 */
export function isCanadianLocation(location) {
    return location.country === 'ca';
}

/**
 * Check if a location belongs to Denmark
 * @param {Object} location - The location object with country property
 * @returns {boolean} - True if Danish location
 */
export function isDanishLocation(location) {
    return location.country === 'dk';
}

/**
 * Check if a location belongs to Mexico
 * @param {Object} location - The location object with country property
 * @returns {boolean} - True if Mexican location
 */
export function isMexicanLocation(location) {
    return location.country === 'mx';
}

/**
 * Check if a location belongs to New Zealand
 * @param {Object} location - The location object with country property
 * @returns {boolean} - True if NZ location
 */
export function isNZLocation(location) {
    return location.country === 'nz';
}

/**
 * Check if a state code belongs to the UK
 * UK states/counties are any that aren't US, German, Spanish, French, Canadian, or Mexican states
 * @param {string} stateCode - The state code to check
 * @returns {boolean} - True if UK state
 */
export function isUKState(stateCode) {
    return !isUSState(stateCode) && 
           !isGermanState(stateCode) && 
           !isSpanishState(stateCode) && 
           !isFrenchState(stateCode) && 
           !isCanadianProvince(stateCode) && 
           !isMexicanState(stateCode) && 
           !isNZState(stateCode) &&
           stateCode && 
           stateCode.trim() !== '';
}

// --- Country Mapping Functions ---

/**
 * Get the selected country code for a given state code
 * @param {string} stateCode - The state code
 * @returns {string} - Country code (US, DE, ES, FR, CA, MX, UK) or 'all'
 */
export function getSelectedCountryForState(stateCode) {
    if (isUSState(stateCode)) return 'US';
    if (isGermanState(stateCode)) return 'DE';
    if (isSpanishState(stateCode)) return 'ES';
    if (isFrenchState(stateCode)) return 'FR';
    if (isCanadianProvince(stateCode)) return 'CA';
    if (isMexicanState(stateCode)) return 'MX';
    if (isUKState(stateCode)) return 'UK';
    if (isNZState(stateCode)) return 'NZ';
    return 'all';
}

/**
 * Check if a state code belongs to New Zealand
 * @param {string} stateCode - The state code to check
 * @returns {boolean} - True if NZ state
 */
export function isNZState(stateCode) {
    // NZ regions are typically full names, so we check if it's not another country's state
    // and if the location country is 'nz' (handled in getSelectedCountryForLocation)
    // But for state selector filtering, we might need a list or just rely on the country check
    return false; // Placeholder, logic handled via location country check mostly
}

/**
 * Get the selected country code for a given location object
 * @param {Object} location - The location object with country property
 * @returns {string} - Country code (US, DE, ES, FR, CA, MX, UK, NZ) or 'all'
 */
export function getSelectedCountryForLocation(location) {
    if (location.country === 'us') return 'US';
    if (location.country === 'de') return 'DE';
    if (location.country === 'es') return 'ES';
    if (location.country === 'fr') return 'FR';
    if (location.country === 'ca') return 'CA';
    if (location.country === 'mx') return 'MX';
    if (location.country === 'dk') return 'DK';
    if (location.country === 'uk') return 'UK';
    if (location.country === 'nz') return 'NZ';
    return 'all';
}

// --- Data Normalization Functions ---

/**
 * Normalize USDA location data for CSV export
 * @param {Object} loc - The location object
 * @param {string|boolean} facilityTypeParam - The facility type parameter
 * @param {Function} mapFacilityType - Optional function to map facility types
 * @returns {Object} - Normalized row object for CSV export
 */
export function normalizeUsdaRow(loc, facilityTypeParam, mapFacilityType = null) {
    const stateDisplayName = getStateDisplayName(loc.state?.trim() || '');
    const statePart = stateDisplayName ? `, ${stateDisplayName}` : '';
    const address = (loc.street && loc.street.trim()) ? 
        `${loc.street.trim()}, ${loc.city?.trim() || ''}${statePart} ${loc.zip || ''}`.replace(/ ,/g, ',') : 
        '';
    
    // Determine the type label based on the parameter and the location data
    let typeLabel;
    if (typeof facilityTypeParam === 'string') {
        switch (facilityTypeParam) {
            case 'breeding': typeLabel = 'Production Facility'; break;
            case 'exhibition': typeLabel = 'Exhibition Facility'; break;
            default: typeLabel = 'Facility';
        }
    } else {
        // Legacy boolean support
        typeLabel = facilityTypeParam ? 'Slaughterhouse' : 'Processing';
    }
    
    // If we have the type field and mapFacilityType function, use the mapped display label
    if (loc.type && typeof mapFacilityType === 'function') {
        const facilityMapping = mapFacilityType(loc.type, loc.establishment_name);
        typeLabel = facilityMapping.displayLabel;
    }
    
    return {
        Type: typeLabel,
        Name: loc.establishment_name || '',
        State: getStateDisplayName(loc.state || ''),
        City: loc.city || '',
        ZIP: loc.zip || '',
        Address: address,
        Latitude: loc.latitude || '',
        Longitude: loc.longitude || '',
        EstablishmentID: loc.establishment_id || '',
        Phone: loc.phone || '',
        AnimalsProcessed: loc.animals_processed || '',
        AnimalsSlaughtered: loc.animals_slaughtered || ''
    };
}

/**
 * Normalize lab data for CSV export
 * @param {Object} lab - The lab object
 * @returns {Object} - Normalized row object for CSV export
 */
export function normalizeLabRow(lab) {
    const fullAddress = `${lab['Address Line 1'] || ''} ${lab['Address Line 2'] || ''} ${lab['City-State-Zip'] || ''}`
        .trim()
        .replace(/ ,/g, ',');
        
    return {
        Type: 'Lab',
        Name: lab['Account Name'] || '',
        State: (lab['City-State-Zip'] || '').split(',')[1]?.trim().split(' ')[0] || '',
        City: (lab['City-State-Zip'] || '').split(',')[0]?.trim() || '',
        ZIP: (lab['City-State-Zip'] || '').split(/\s+/).pop() || '',
        Address: fullAddress,
        Latitude: lab.latitude || '',
        Longitude: lab.longitude || '',
        CertificateNumber: lab['Certificate Number'] || '',
        AnimalsTestedOn: lab['Animals Tested On'] || ''
    };
}

/**
 * Normalize inspection report data for CSV export
 * @param {Object} report - The inspection report object
 * @returns {Object} - Normalized row object for CSV export
 */
export function normalizeInspectionRow(report) {
    let type = 'Other';
    if (report['License Type'] === 'Class A - Breeder') type = 'Breeder';
    else if (report['License Type'] === 'Class B - Dealer') type = 'Dealer';
    else if (report['License Type'] === 'Class C - Exhibitor') type = 'Exhibitor';
    
    const address = `${report['Address Line 1'] || ''}, ${report['City-State-Zip'] || ''}`
        .replace(/^,|,$/g, '')
        .trim();
        
    return {
        Type: type,
        Name: report['Account Name'] || '',
        State: report['State'] || '',
        City: (report['City-State-Zip'] || '').split(',')[0]?.trim() || '',
        ZIP: (report['City-State-Zip'] || '').split(/\s+/).pop() || '',
        Address: address,
        Latitude: report['Geocodio Latitude'] || '',
        Longitude: report['Geocodio Longitude'] || '',
        CertificateNumber: report['Certificate Number'] || ''
    };
}

// --- CSV Utility Functions ---

/**
 * Convert an array of objects to CSV format
 * @param {Array} rows - Array of row objects
 * @returns {string} - CSV formatted string
 */
export function toCsv(rows) {
    if (!rows || rows.length === 0) return '';
    
    // @ts-ignore
    const headers = Array.from(new Set(rows.flatMap(r => Object.keys(r))));
    
    const esc = (v) => {
        if (v === null || v === undefined) return '';
        const s = String(v);
        if (/[",\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
        return s;
    };
    
    const lines = [headers.join(',')].concat(
        rows.map(r => headers.map(h => esc(r[h])).join(','))
    );
    
    return lines.join('\n');
}

/**
 * Download text content as a file
 * @param {string} filename - The filename to download
 * @param {string} text - The text content to download
 */
export function downloadText(filename, text) {
    const blob = new Blob([text], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}