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

/**
 * Builds HTML popup content for USDA facility locations
 * @param {Object} location - The facility location data
 * @param {string|boolean} facilityTypeLabel - Type label or boolean for slaughterhouse
 * @returns {string} HTML string for the popup content
 */
export function buildLocationPopup(location, facilityTypeLabel) {
    const establishmentName = location.establishment_name || 'Unknown Name';
    const locationTypeText = typeof facilityTypeLabel === 'string' ? facilityTypeLabel : 
                            (facilityTypeLabel ? "Slaughterhouse" : "Processing-Only Facility");
    const stateDisplayName = location.state ? getStateDisplayName(location.state.trim()) : '';
    const statePart = stateDisplayName ? ` ${stateDisplayName}` : '';
    const fullAddress = location.street && location.street.trim() ? `${location.street.trim()}, ${location.city.trim()}${statePart} ${location.zip}` : 'Address not available';
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
    const isSlaughterFacility = typeof facilityTypeLabel === 'string' ? 
        (facilityTypeLabel.toLowerCase().includes('slaughter') || facilityTypeLabel.toLowerCase().includes('aquatic processing')) :
        facilityTypeLabel === true;
    
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
        if (hasAnimalsSlaughtered || hasSlaughterVolume) {
            slaughterText = `<hr>`;
            if (hasAnimalsSlaughtered) {
                slaughterText += `<p><strong>Types of Animals Killed:</strong> ${location.animals_slaughtered}</p>`;
            }
            if (hasSlaughterVolume) {
                slaughterText += `<p><strong>Slaughter Volume:</strong> ${animals_slaughtered_yearly_text}</p>`;
            }
        }
    }

    // Create disclaimer text if needed
    let disclaimerText = '';
    if (location.country && location.country !== 'us') {
        disclaimerText = ' (Approximately)';
    }

    return `
        <div class="info-popup">
            <h3>${establishmentName}</h3>
            <p1><strong>${locationTypeText}</strong></p1><br>
            <p1>(${location.latitude}, ${location.longitude}) ${disclaimerText}</p1>
            <hr>
            <p><strong>Address:</strong> <span class="copyable-text" data-copy="${fullAddress}">${fullAddress}</span></p>
            <p><strong>ID:</strong> <span class="copyable-text" data-copy="${establishmentId}">${establishmentId}</span></p>
            ${phone && phone.trim() !== '' && phone !== 'N/A' ? `<p><strong>Phone:</strong> <span class="copyable-text" data-copy="${phone}">${phone}</span></p>` : ''}
            ${dbas ? `<p><strong>Doing Business As:</strong> <span class="copyable-text" data-copy="${dbas}">${dbas}</span></p>` : ""}
            ${(hasAnimalsProcessed || hasProcessingVolume) ? '<hr>' : ''}
            ${hasAnimalsProcessed ? `<p><strong>Products Processed:</strong> ${location.animals_processed}</p>` : ''}
            ${hasProcessingVolume ? `<p><strong>Product Volume:</strong> ${animals_processed_monthly_text}</p>` : ''}
            ${slaughterText}
            <a href="${directionsUrl}" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>Get Directions</strong></a>${location.country === 'us' || !location.country ? ' | <a href="https://www.fsis.usda.gov/inspection/establishments/meat-poultry-and-egg-product-inspection-directory" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>View Source</strong></a>' : location.country === 'uk' ? ' | <a href="https://transparentfarms.org.uk/" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>View Source</strong></a>' : location.country === 'ca' ? ' | <a href="https://open.canada.ca/data/en/dataset/a763088c-018d-48b7-bf47-3027a8c725b8" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>View Source</strong></a>' : location.country === 'es' ? ' | <a href="https://granjastransparentes.es/" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>View Source</strong></a>' : location.country === 'fr' ? ' | <a href="https://www.google.com/maps/d/u/0/viewer?mid=1TGGpOJz40AHgTrbfYMO6sg3XrTFoG31n&ll=48.794860747569736%2C2.0410253416334534&z=8" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>View Source</strong></a>' : location.country === 'de' ? ' | <a href="https://www.google.com/maps/d/u/0/viewer?mid=1TGGpOJz40AHgTrbfYMO6sg3XrTFoG31n&ll=48.794860747569736%2C2.0410253416334534&z=8" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>View Source</strong></a>' : ''}
        </div>`;
}

/**
 * Builds HTML popup content for animal testing laboratory locations
 * @param {Object} lab - The laboratory data
 * @returns {string} HTML string for the popup content
 */
export function buildLabPopup(lab) {
    const name = lab['Account Name'] || 'Unknown Name';
    const certNum = lab['Certificate Number'];
    const fullAddress = `${lab['Address Line 1'] || ''} ${lab['Address Line 2'] || ''} ${lab['City-State-Zip'] || ''}`.trim().replace(/ ,/g, ',');
    const arloUrl = certNum ? `https://arlo.riseforanimals.org/browse?query=${encodeURIComponent(certNum)}&order=relevance` : null;
    const directionsUrl = `https://www.google.com/maps/dir/?api=1&destination=${lab.latitude},${lab.longitude}`;

    return `
        <div class="info-popup">
            <h3>${name}</h3>
            <p1><strong>${lab['Registration Type'] || 'N/A'}</strong></p1><br>
            <p1>(${lab.latitude},${lab.longitude}) (Approximately)</p1>
            <hr>
            <p><strong>Address:</strong> <span class="copyable-text" data-copy="${fullAddress}">${fullAddress || 'N/A'}</span></p>
            <p><strong>Certificate Number:</strong> <span class="copyable-text" data-copy="${certNum}">${certNum || 'N/A'}</span></p>
            <p><strong>Animals Being Tested On:</strong> ${lab['Animals Tested On'] || 'N/A'}</p>
            <hr>
            
            <p><strong>Investigation Instructions: </strong>Copy the <span class="copyable-text" data-copy="${certNum}">${"certificate number" || 'N/A'}</span>, paste it into the APHIS search tool below, then click <strong>query annual reports</strong> on the facility. Keep an eye out for <strong> exception reports</strong>; those are especially cruel.</p>

            <a href="${EXTERNAL_URLS.aphis.annualReports}" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>Open APHIS Search Tool</strong></a>
            <p></p>
            <a href="${directionsUrl}" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>Get Directions</strong></a> | <a href="${EXTERNAL_URLS.eFileAphis.annualReports}" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>View Source</strong></a>
        </div>`;
}

/**
 * Builds HTML popup content for USDA inspection report locations
 * @param {Object} report - The inspection report data
 * @returns {string} HTML string for the popup content
 */
export function buildInspectionReportPopup(report) {
    let classText = "N/A";
    if (report['License Type'] === "Class A - Breeder") classText = "Animal Breeder";
    else if (report['License Type'] === "Class B - Dealer") classText = "Animal Dealer";
    else if (report['License Type'] === "Class C - Exhibitor") classText = "Exhibitor / Zoo";
    
    const name = report['Account Name'] || 'Unknown Name';
    const certNum = report['Certificate Number'];
    const fullAddress = `${report['Address Line 1'] || ''}, ${report['City-State-Zip'] || ''}`.trim().replace(/^,|,$/g, '').trim();
    const directionsUrl = `https://www.google.com/maps/dir/?api=1&destination=${report['Geocodio Latitude']},${report['Geocodio Longitude']}`;

    return `
        <div class="info-popup inspection-popup">
            <h3>${name}</h3>
            <p1><strong>${classText}</strong></p1><br>
            <p1>(${report['Geocodio Latitude']}, ${report['Geocodio Longitude']}) (Approximately)</p1>
            <hr>
            <p><strong>Address:</strong> <span class="copyable-text" data-copy="${fullAddress}">${fullAddress || 'N/A'}</span></p>
            <p><strong>Certificate Number:</strong> <span class="copyable-text" data-copy="${certNum}">${certNum || 'N/A'}</span></p>
            <p><strong>Investigation Instructions: </strong>Copy the <span class="copyable-text" data-copy="${certNum}">${"certificate number" || 'N/A'}</span>, paste it into the APHIS search tool below, then click <strong>query inspection reports</strong> on the facility.</p>
            <a href="${EXTERNAL_URLS.aphis.inspectionReports}" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>Open APHIS Search Tool</strong></a>
            <p></p>
            <a href="${directionsUrl}" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>Get Directions</strong></a> | <a href="${EXTERNAL_URLS.eFileAphis.inspectionReports}" target="_blank" rel="noopener noreferrer" class="directions-btn"><strong>View Source</strong></a>
        </div>`;
}