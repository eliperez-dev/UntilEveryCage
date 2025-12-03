// @ts-nocheck
/**
 * =============================================================================
 * POPUP BUILDER MODULE
 * =============================================================================
 * This module contains functions for building HTML popup content for different
 * types of map markers in the Until Every Cage is Empty application.
 * 
 * Functions:
 * - buildLocationPopup: Creates popups for USDA facilities (slaughterhouses, processing plants, etc.)
 * - buildLabPopup: Creates popups for animal testing laboratories
 * - buildInspectionReportPopup: Creates popups for USDA inspection facilities
 * 
 * Dependencies:
 * - geoUtils: For state display name conversion
 * - constants: For external URLs and configuration
 */

// Import required modules
import { getStateDisplayName } from './geoUtils.js';
import { EXTERNAL_URLS } from './constants.js';
import { i18n } from './translationManager.js';

// Helper to split string by comma respecting parentheses
const splitWithParentheses = (str) => {
    const result = [];
    let current = '';
    let depth = 0;
    
    for (let i = 0; i < str.length; i++) {
        const char = str[i];
        if (char === '(') depth++;
        else if (char === ')') depth--;
        
        if (char === ',' && depth === 0) {
            result.push(current.trim());
            current = '';
        } else {
            current += char;
        }
    }
    if (current) result.push(current.trim());
    return result;
};

// Helper to translate a single item
const translateItem = (text) => {
    const key = text.toLowerCase();
    if (i18n.exists(`animals.${key}`)) {
        return i18n.t(`animals.${key}`);
    }
    // Try singular if plural (simple check)
    if (key.endsWith('s') && i18n.exists(`animals.${key.slice(0, -1)}`)) {
        return i18n.t(`animals.${key.slice(0, -1)}`);
    }
    return text;
};

// Helper to translate comma-separated lists (recursive)
const translateList = (listStr) => {
    if (!listStr) return listStr;
    
    const items = splitWithParentheses(listStr);
    
    return items.map(item => {
        const trimmed = item.trim();
        
        // Handle parentheses: "Cattle (Cows, Bulls)"
        const parenMatch = trimmed.match(/^([^(]+)\s*\((.*)\)$/);
        if (parenMatch) {
            const mainPart = parenMatch[1].trim();
            const insideParens = parenMatch[2];
            
            const translatedMain = translateItem(mainPart);
            const translatedInside = translateList(insideParens); // Recursion
            
            return `${translatedMain} (${translatedInside})`;
        }
        
        // Handle counts: "311 Hamsters"
        const countMatch = trimmed.match(/^(\d+)\s+(.+)$/);
        if (countMatch) {
            const count = countMatch[1];
            const animal = countMatch[2];
            const translatedAnimal = translateItem(animal);
            return `${count} ${translatedAnimal}`;
        }
        
        return translateItem(trimmed);
    }).join(', ');
};

/**
 * Builds HTML popup content for USDA facility locations
 * @param {Object} location - The facility location data
 * @param {string|boolean} facilityTypeLabel - Type label or boolean for slaughterhouse
 * @returns {string} HTML string for the popup content
 */
export function buildLocationPopup(location, facilityTypeLabel) {
    const establishmentName = location.establishment_name || i18n.t('popups.unknownName');
    
    let locationTypeText;
    if (typeof facilityTypeLabel === 'string') {
        locationTypeText = i18n.exists(facilityTypeLabel) ? i18n.t(facilityTypeLabel) : facilityTypeLabel;
    } else if (typeof facilityTypeLabel === 'object' && facilityTypeLabel.key) {
        locationTypeText = i18n.t(facilityTypeLabel.key) + (facilityTypeLabel.suffix || '');
    } else {
        locationTypeText = facilityTypeLabel ? i18n.t('popups.slaughterhouse') : i18n.t('popups.processing');
    }

    const stateDisplayName = location.state ? getStateDisplayName(location.state.trim()) : '';
    const statePart = stateDisplayName ? ` ${stateDisplayName}` : '';
    const fullAddress = location.street && location.street.trim() ? `${location.street.trim()}, ${location.city.trim()}${statePart} ${location.zip}` : i18n.t('popups.addressNA');
    const establishmentId = location.establishment_id;
    const grantDate = location.grant_date;
    const phone = location.phone;
    const dbas = location.dbas;
    const directionsUrl = `https://www.google.com/maps/dir/?api=1&destination=${location.latitude},${location.longitude}`;

    let animals_processed_monthly_text = "N/A";
    if (location.processing_volume_category) {
        switch (location.processing_volume_category) {
            case "1.0": animals_processed_monthly_text = "Less than 10,000 pounds/month."; break;
            case "2.0": animals_processed_monthly_text = "10k - 100k pounds/month."; break;
            case "3.0": animals_processed_monthly_text = "100k - 1M pounds/month."; break;
            case "4.0": animals_processed_monthly_text = "1M - 10M pounds/month."; break;
            case "5.0": animals_processed_monthly_text = "Over 10M pounds/month."; break;
        }
    }

    const animalsProcessed = translateList(location.animals_processed);
    const animalsSlaughtered = translateList(location.animals_slaughtered);

    // Check if animals_processed has meaningful data
    const hasAnimalsProcessed = location.animals_processed && 
                               location.animals_processed.toLowerCase() !== 'n/a' && 
                               location.animals_processed.toLowerCase() !== 'unknown' &&
                               location.animals_processed.trim() !== '';
    
    // Check if processing volume has meaningful data
    const hasProcessingVolume = location.processing_volume_category && 
                               location.processing_volume_category !== "0.0" &&
                               animals_processed_monthly_text !== "N/A";

    let slaughterText = "";
    
    let isSlaughterFacility = false;
    if (typeof facilityTypeLabel === 'string') {
        isSlaughterFacility = facilityTypeLabel.toLowerCase().includes('slaughter') || facilityTypeLabel.toLowerCase().includes('aquatic processing');
    } else if (typeof facilityTypeLabel === 'object' && facilityTypeLabel.key) {
        isSlaughterFacility = facilityTypeLabel.key.toLowerCase().includes('slaughter');
    } else {
        isSlaughterFacility = facilityTypeLabel === true;
    }
    
    if (isSlaughterFacility) {
        let animals_slaughtered_yearly_text = "N/A";
        if (location.slaughter_volume_category) {
            switch (location.slaughter_volume_category) {
                case "1.0": animals_slaughtered_yearly_text = "Less than 1,000 animals/year."; break;
                case "2.0": animals_slaughtered_yearly_text = "1k - 10k animals/year."; break;
                case "3.0": animals_slaughtered_yearly_text = "10k - 100k animals/year."; break;
                case "4.0": animals_slaughtered_yearly_text = "100k - 10M animals/year."; break;
                case "5.0": animals_slaughtered_yearly_text = "Over 10M animals/year."; break;
            }
        }
        
        // Check if animals_slaughtered has meaningful data
        const hasAnimalsSlaughtered = location.animals_slaughtered && 
                                     location.animals_slaughtered.toLowerCase() !== 'n/a' && 
                                     location.animals_slaughtered.toLowerCase() !== 'unknown' &&
                                     location.animals_slaughtered.trim() !== '';
        
        // Check if slaughter volume has meaningful data
        const hasSlaughterVolume = location.slaughter_volume_category && 
                                  location.slaughter_volume_category !== "0.0" &&
                                  animals_slaughtered_yearly_text !== "N/A";
        
        // Only include slaughter data if at least one field has meaningful data
        // Skip animals_slaughtered for Mexican facilities
        const isMexican = location.country === 'mx';
        if (hasAnimalsSlaughtered || hasSlaughterVolume) {
            slaughterText = `<hr>`;
            if (hasAnimalsSlaughtered && !isMexican) {
                slaughterText += `<p><strong>${i18n.t('popups.animalsKilled')}:</strong> ${animalsSlaughtered}</p>`;
            }
            if (hasSlaughterVolume) {
                slaughterText += `<p><strong>${i18n.t('popups.slaughterVolume')}:</strong> ${animals_slaughtered_yearly_text}</p>`;
            }
        }
    }

    // Create disclaimer text if needed
    let disclaimerText = '';
    if (location.country && location.country !== 'us') {
        disclaimerText = ` ${i18n.t('popups.approx')}`;
    }

    const isMexican = location.country === 'mx';

    return `
        <div class="info-popup">
            <h3>${establishmentName}</h3>
            <p1><strong>${locationTypeText}</strong></p1><br>
            <p1>(${location.latitude}, ${location.longitude}) ${disclaimerText}</p1>
            <hr>
            <p><strong>${i18n.t('popups.address')}:</strong> <span class="copyable-text" data-copy="${fullAddress}">${fullAddress}</span></p>
            <p><strong>${i18n.t('popups.id')}:</strong> <span class="copyable-text" data-copy="${establishmentId}">${establishmentId}</span></p>
            ${phone && phone.trim() !== '' && phone !== 'N/A' ? `<p><strong>${i18n.t('popups.phone')}:</strong> <span class="copyable-text" data-copy="${phone}">${phone}</span></p>` : ''}
            ${dbas ? `<p><strong>${i18n.t('popups.dba')}:</strong> <span class="copyable-text" data-copy="${dbas}">${dbas}</span></p>` : ""}
            ${(hasAnimalsProcessed || hasProcessingVolume) && !isMexican ? '<hr>' : ''}
            ${hasAnimalsProcessed && !isMexican ? `<p><strong>${i18n.t('popups.productsProcessed')}:</strong> ${animalsProcessed}</p>` : ''}
            ${hasProcessingVolume && !isMexican ? `<p><strong>${i18n.t('popups.productVolume')}:</strong> ${animals_processed_monthly_text}</p>` : ''}
            ${slaughterText}
            <a href="${directionsUrl}" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>${i18n.t('popups.getDirections')}</strong></a>${location.country === 'us' || !location.country ? ` | <a href="https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>${i18n.t('popups.viewSource')}</strong></a>` : location.country === 'uk' ? ` | <a href="https://transparentfarms.org.uk/" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>${i18n.t('popups.viewSource')}</strong></a>` : location.country === 'ca' ? ` | <a href="https://open.canada.ca/data/en/dataset/a763088c-018d-48b7-bf47-3027a8c725b8" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>${i18n.t('popups.viewSource')}</strong></a>` : location.country === 'es' ? ` | <a href="https://granjastransparentes.es/" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>${i18n.t('popups.viewSource')}</strong></a>` : location.country === 'mx' ? ` | <a href="https://www.inegi.org.mx/app/mapa/denue/" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>${i18n.t('popups.viewSource')}</strong></a>` : location.country === 'fr' ? ` | <a href="https://www.google.com/maps/d/u/0/viewer?mid=1TGGpOJz40AHgTrbfYMO6sg3XrTFoG31n&ll=48.794860747569736%2C2.0410253416334534&z=8" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>${i18n.t('popups.viewSource')}</strong></a>` : location.country === 'de' ? ` | <a href="https://www.google.com/maps/d/u/0/viewer?mid=1TGGpOJz40AHgTrbfYMO6sg3XrTFoG31n&ll=48.794860747569736%2C2.0410253416334534&z=8" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>${i18n.t('popups.viewSource')}</strong></a>` : ''}
        </div>`;
}

/**
 * Builds HTML popup content for animal testing laboratory locations
 * @param {Object} lab - The laboratory data
 * @returns {string} HTML string for the popup content
 */
export function buildLabPopup(lab) {
    const name = lab['Account Name'] || i18n.t('popups.unknownName');
    const certNum = lab['Certificate Number'];
    const fullAddress = `${lab['Address Line 1'] || ''} ${lab['Address Line 2'] || ''} ${lab['City-State-Zip'] || ''}`.trim().replace(/ ,/g, ',');
    const arloUrl = certNum ? `https://arlo.riseforanimals.org/browse?query=${encodeURIComponent(certNum)}&order=relevance` : null;
    const directionsUrl = `https://www.google.com/maps/dir/?api=1&destination=${lab.latitude},${lab.longitude}`;

    const investigationText = i18n.t('popups.investigationText').replace(/{certNum}/g, certNum || 'N/A');

    const regType = lab['Registration Type'];
    let regTypeText = regType || 'N/A';
    if (regType) {
        if (regType.includes('Class A')) regTypeText = i18n.t('facilityTypes.classABreeder');
        else if (regType.includes('Class B')) regTypeText = i18n.t('facilityTypes.classBDealer');
        else if (regType.includes('Class C')) regTypeText = i18n.t('facilityTypes.classCExhibitor');
        else if (regType.includes('Class R')) regTypeText = i18n.t('facilityTypes.classRResearchFacility');
        else if (regType.includes('Class T')) regTypeText = i18n.t('facilityTypes.classTCarrier');
        else if (regType.includes('Class H')) regTypeText = i18n.t('facilityTypes.classHIntermediateHandler');
    }

    const animalsTested = translateList(lab['Animals Tested On']);

    return `
        <div class="info-popup">
            <h3>${name}</h3>
            <p1><strong>${regTypeText}</strong></p1><br>
            <p1>(${lab.latitude},${lab.longitude}) ${i18n.t('popups.approx')}</p1>
            <hr>
            <p><strong>${i18n.t('popups.address')}:</strong> <span class="copyable-text" data-copy="${fullAddress}">${fullAddress || 'N/A'}</span></p>
            <p><strong>${i18n.t('popups.certNum')}:</strong> <span class="copyable-text" data-copy="${certNum}">${certNum || 'N/A'}</span></p>
            <p><strong>${i18n.t('popups.animalsTested')}:</strong> ${animalsTested || 'N/A'}</p>
            <hr>
            
            <p><strong>${i18n.t('popups.investigation')}: </strong>${investigationText}</p>

            <a href="${EXTERNAL_URLS.aphis.annualReports}" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>${i18n.t('popups.openAphis')}</strong></a>
            <p></p>
            <a href="${directionsUrl}" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>${i18n.t('popups.getDirections')}</strong></a> | <a href="${EXTERNAL_URLS.eFileAphis.annualReports}" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>${i18n.t('popups.viewSource')}</strong></a>
        </div>`;
}

/**
 * Builds HTML popup content for USDA inspection report locations
 * @param {Object} report - The inspection report data
 * @returns {string} HTML string for the popup content
 */
export function buildInspectionReportPopup(report) {
    let classText = "N/A";
    const licenseType = report['License Type'];
    if (licenseType === "Class A - Breeder") classText = i18n.t('facilityTypes.classABreeder');
    else if (licenseType === "Class B - Dealer") classText = i18n.t('facilityTypes.classBDealer');
    else if (licenseType === "Class C - Exhibitor") classText = i18n.t('facilityTypes.classCExhibitor');
    
    const name = report['Account Name'] || i18n.t('popups.unknownName');
    const certNum = report['Certificate Number'];
    const fullAddress = `${report['Address Line 1'] || ''}, ${report['City-State-Zip'] || ''}`.trim().replace(/^,|,$/g, '').trim();
    const directionsUrl = `https://www.google.com/maps/dir/?api=1&destination=${report['Geocodio Latitude']},${report['Geocodio Longitude']}`;

    const investigationText = i18n.t('popups.investigationTextInspection').replace(/{certNum}/g, certNum || 'N/A');

    return `
        <div class="info-popup inspection-popup">
            <h3>${name}</h3>
            <p1><strong>${classText}</strong></p1><br>
            <p1>(${report['Geocodio Latitude']}, ${report['Geocodio Longitude']}) ${i18n.t('popups.approx')}</p1>
            <hr>
            <p><strong>${i18n.t('popups.address')}:</strong> <span class="copyable-text" data-copy="${fullAddress}">${fullAddress || 'N/A'}</span></p>
            <p><strong>${i18n.t('popups.certNum')}:</strong> <span class="copyable-text" data-copy="${certNum}">${certNum || 'N/A'}</span></p>
            <p><strong>${i18n.t('popups.investigation')}: </strong>${investigationText}</p>
            <a href="${EXTERNAL_URLS.aphis.inspectionReports}" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>${i18n.t('popups.openAphis')}</strong></a>
            <p></p>
            <a href="${directionsUrl}" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>${i18n.t('popups.getDirections')}</strong></a> | <a href="${EXTERNAL_URLS.eFileAphis.inspectionReports}" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>${i18n.t('popups.viewSource')}</strong></a>
        </div>`;
}