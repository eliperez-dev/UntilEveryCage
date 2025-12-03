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
 * Extract state code from City-State-Zip string
 * @param {string} cityStateZip - The City-State-Zip string (e.g. "City, ST 12345")
 * @returns {string|null} - The 2-letter state code or null
 */
export function getStateFromCityStateZip(cityStateZip) {
    if (!cityStateZip || typeof cityStateZip !== 'string') return null;
    const match = cityStateZip.match(/, ([A-Z]{2})/);
    return match ? match[1] : null;
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
// Moved to ExportManager.js

// --- CSV Utility Functions ---
// Moved to ExportManager.js