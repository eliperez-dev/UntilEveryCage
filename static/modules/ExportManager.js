/**
 * Export Manager Module
 * 
 * Handles data export functionality, including CSV generation and download.
 */

import { getStateDisplayName } from './geoUtils.js';

class ExportManager {
    /**
     * Normalize USDA location data for CSV export
     * @param {Object} loc - The location object
     * @param {string|boolean} facilityTypeParam - The facility type parameter
     * @param {Function} mapFacilityType - Optional function to map facility types
     * @returns {Object} - Normalized row object for CSV export
     */
    normalizeUsdaRow(loc, facilityTypeParam, mapFacilityType = null) {
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
    normalizeLabRow(lab) {
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
    normalizeInspectionRow(report) {
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

    /**
     * Convert an array of objects to CSV format
     * @param {Array} rows - Array of row objects
     * @returns {string} - CSV formatted string
     */
    toCsv(rows) {
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
    downloadText(filename, text) {
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

    /**
     * Export data to CSV based on current filters
     * @param {Object} filteredData - The currently filtered data
     * @param {Object} options - Export options (checkbox states, etc.)
     * @param {Function} mapFacilityType - Function to map facility types
     */
    exportData(filteredData, options, mapFacilityType) {
        const {
            includeSlaughter,
            includeProcessing,
            includeLabs,
            includeBreeders,
            includeDealers,
            includeExhibitors,
            isComplete
        } = options;

        const rows = [];
        if (includeSlaughter && Array.isArray(filteredData.slaughterhouses)) {
            rows.push(...filteredData.slaughterhouses.map(loc => this.normalizeUsdaRow(loc, true, mapFacilityType)));
        }
        if (includeProcessing && Array.isArray(filteredData.processingPlants)) {
            rows.push(...filteredData.processingPlants.map(loc => this.normalizeUsdaRow(loc, false, mapFacilityType)));
        }
        if (includeBreeders && Array.isArray(filteredData.breedingFacilities)) {
            rows.push(...filteredData.breedingFacilities.map(loc => this.normalizeUsdaRow(loc, 'breeding', mapFacilityType)));
        }
        if (includeExhibitors && Array.isArray(filteredData.exhibitionFacilities)) {
            rows.push(...filteredData.exhibitionFacilities.map(loc => this.normalizeUsdaRow(loc, 'exhibition', mapFacilityType)));
        }
        if (includeLabs && Array.isArray(filteredData.filteredLabs)) {
            rows.push(...filteredData.filteredLabs.map(lab => this.normalizeLabRow(lab)));
        }
        
        if (Array.isArray(filteredData.filteredInspections)) {
            filteredData.filteredInspections.forEach(r => {
                if ((includeBreeders && r['License Type'] === 'Class A - Breeder') ||
                    (includeDealers && r['License Type'] === 'Class B - Dealer') ||
                    (includeExhibitors && r['License Type'] === 'Class C - Exhibitor')) {
                    rows.push(this.normalizeInspectionRow(r));
                }
            });
        }
        
        if (rows.length === 0) {
            alert('No data to export for current filters.');
            return;
        }
        
        const csv = this.toCsv(rows);
            
        const now = new Date();
        const yyyy = now.getFullYear();
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const dd = String(now.getDate()).padStart(2, '0');
        const dateStr = `${yyyy}-${mm}-${dd}`;
        const suffix = isComplete ? 'complete' : 'filtered';
        const filename = `untileverycage-visible-${dateStr}-${suffix}.csv`;
        this.downloadText(filename, csv);
    }
}

export const exportManager = new ExportManager();
