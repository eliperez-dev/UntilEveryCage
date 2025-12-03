/**
 * Filter Manager Module
 * 
 * Handles filtering logic, UI controls for filters, and statistics updates.
 */

import { initializeDOMElements } from './constants.js';
import { mapFacilityType } from './iconUtils.js';
import { 
    isUSState, isGermanState, isSpanishState, isFrenchState, isCanadianProvince, isMexicanState, isUKState,
    isFrenchLocation, isCanadianLocation, isDanishLocation, isMexicanLocation, isNZLocation,
    getStateDisplayName, getStateFromCityStateZip
} from './geoUtils.js';

export class FilterManager {
    constructor() {
        this.elements = initializeDOMElements();
        this.clusterThreshold = 2800;
    }

    getFilterState() {
        return {
            selectedCountry: this.elements.countrySelector.value,
            selectedState: this.elements.stateSelector.value,
            searchTerm: this.elements.nameSearchInput.value.toLowerCase().trim(),
            showSlaughter: this.elements.slaughterhouseCheckbox.checked,
            showProcessing: this.elements.meatProcessingCheckbox.checked,
            showLabs: this.elements.testingLabsCheckbox.checked,
            showBreeders: this.elements.breedersCheckbox.checked,
            showDealers: this.elements.dealersCheckbox.checked,
            showExhibitors: this.elements.exhibitorsCheckbox.checked,
            clusterThreshold: this.clusterThreshold
        };
    }

    populateCountrySelector(allStateValues, allLocations) {
        const { countrySelector } = this.elements;
        
        const hasUSStates = allStateValues.some(state => isUSState(state));
        const hasGermanStates = allStateValues.some(state => isGermanState(state));
        const hasSpanishStates = allStateValues.some(state => isSpanishState(state));
        const hasFrenchStates = allLocations.some(location => isFrenchLocation(location));
        const hasCanadianStates = allLocations.some(location => isCanadianLocation(location));
        const hasMexicanStates = allLocations.some(location => isMexicanLocation(location));
        const hasDanishStates = allLocations.some(location => isDanishLocation(location));
        const hasNZStates = allLocations.some(location => isNZLocation(location));
        const hasUKStates = allStateValues.some(state => isUKState(state));
        
        countrySelector.innerHTML = '<option value="all">All Countries</option>';
        
        if (hasUSStates) this.addOption(countrySelector, 'US', 'United States');
        if (hasGermanStates) this.addOption(countrySelector, 'DE', 'Deutschland');
        if (hasSpanishStates) this.addOption(countrySelector, 'ES', 'España');
        if (hasFrenchStates) this.addOption(countrySelector, 'FR', 'France');
        if (hasCanadianStates) this.addOption(countrySelector, 'CA', 'Canada');
        if (hasMexicanStates) this.addOption(countrySelector, 'MX', 'México');
        if (hasDanishStates) this.addOption(countrySelector, 'DK', 'Danmark');
        if (hasNZStates) this.addOption(countrySelector, 'NZ', 'New Zealand');
        if (hasUKStates) this.addOption(countrySelector, 'UK', 'United Kingdom');
    }

    addOption(select, value, text) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = text;
        select.appendChild(option);
    }

    populateStateSelector(allStateValues, allLocations, selectedCountry = 'all') {
        const { stateSelector } = this.elements;
        let filteredStates = [];
        
        if (selectedCountry === 'all') {
            filteredStates = allStateValues;
        } else if (selectedCountry === 'US') {
            filteredStates = allStateValues.filter(state => isUSState(state));
        } else if (selectedCountry === 'DE') {
            filteredStates = allStateValues.filter(state => isGermanState(state));
        } else if (selectedCountry === 'ES') {
            filteredStates = allStateValues.filter(state => isSpanishState(state));
        } else if (selectedCountry === 'FR') {
            filteredStates = allStateValues.filter(state => isFrenchState(state));
        } else if (selectedCountry === 'CA') {
            filteredStates = allStateValues.filter(state => isCanadianProvince(state));
        } else if (selectedCountry === 'MX') {
            const mexicanStateMap = new Map();
            allStateValues.filter(state => isMexicanState(state)).forEach(state => {
                const normalized = state.toUpperCase();
                if (!mexicanStateMap.has(normalized)) {
                    mexicanStateMap.set(normalized, state);
                }
            });
            filteredStates = Array.from(mexicanStateMap.values());
        } else if (selectedCountry === 'DK') {
            filteredStates = [...new Set(allLocations
                .filter(location => isDanishLocation(location))
                .map(location => location.city)
                .filter(city => city && city.trim() !== '')
            )].sort();
        } else if (selectedCountry === 'NZ') {
            filteredStates = [...new Set(allLocations
                .filter(location => isNZLocation(location))
                .map(location => location.state)
                .filter(state => state && state.trim() !== '')
            )].sort();
        } else if (selectedCountry === 'UK') {
            filteredStates = allStateValues.filter(state => isUKState(state));
        }
        
        stateSelector.innerHTML = '<option value="all">All States/Provinces</option>';
        
        if (filteredStates.length === 0 && selectedCountry === 'FR') {
            const noStatesOption = document.createElement('option');
            noStatesOption.value = 'none';
            noStatesOption.textContent = '(Region data not available)';
            noStatesOption.disabled = true;
            stateSelector.appendChild(noStatesOption);
        } else if (filteredStates.length === 0 && selectedCountry === 'DK') {
            const noStatesOption = document.createElement('option');
            noStatesOption.value = 'none';
            noStatesOption.textContent = '(City data not available)';
            noStatesOption.disabled = true;
            stateSelector.appendChild(noStatesOption);
        } else {
            filteredStates
                .sort((a, b) => getStateDisplayName(a).localeCompare(getStateDisplayName(b)))
                .forEach(state => {
                    const option = document.createElement('option');
                    option.value = state;
                    option.textContent = getStateDisplayName(state);
                    stateSelector.appendChild(option);
                });
        }
    }

    filterData(allLocations, allLabLocations, allInspectionReports) {
        const filterState = this.getFilterState();
        const {
            selectedCountry,
            selectedState,
            searchTerm
        } = filterState;

        const isAllStatesView = selectedState === 'all';
        
        const searchSynonyms = {
            'cow': 'cattle',
            'cows': 'cattle'
        };
        const effectiveSearchTerm = searchSynonyms[searchTerm] || searchTerm;

        const filteredUsdaLocations = this.filterUsdaLocations(allLocations, filterState, isAllStatesView, effectiveSearchTerm);
        const filteredLabs = this.filterLabs(allLabLocations, filterState, isAllStatesView);
        const filteredInspections = this.filterInspections(allInspectionReports, filterState, isAllStatesView);

        const slaughterhouses = filteredUsdaLocations.filter(loc => mapFacilityType(loc.type, loc.establishment_name).category === 'slaughter');
        const processingPlants = filteredUsdaLocations.filter(loc => mapFacilityType(loc.type, loc.establishment_name).category === 'processing');
        const breedingFacilities = filteredUsdaLocations.filter(loc => mapFacilityType(loc.type, loc.establishment_name).category === 'breeder');
        const exhibitionFacilities = filteredUsdaLocations.filter(loc => mapFacilityType(loc.type, loc.establishment_name).category === 'exhibitor');

        return {
            slaughterhouses,
            processingPlants,
            breedingFacilities,
            exhibitionFacilities,
            filteredLabs,
            filteredInspections
        };
    }

    filterUsdaLocations(allLocations, filterState, isAllStatesView, effectiveSearchTerm) {
        const { selectedCountry, selectedState, searchTerm } = filterState;

        return allLocations.filter(loc => {
            // Country filtering
            if (!this.checkCountryMatch(loc, selectedCountry, loc.state)) return false;

            // State filtering
            if (!this.checkStateMatch(loc, selectedCountry, selectedState, isAllStatesView)) return false;

            if (!searchTerm) return true;

            const nameMatch = (loc.establishment_name && loc.establishment_name.toLowerCase().includes(searchTerm)) ||
                              (loc.dbas && loc.dbas.toLowerCase().includes(searchTerm));
            
            const animalMatch = (loc.animals_slaughtered && loc.animals_slaughtered.toLowerCase().includes(effectiveSearchTerm)) ||
                                (loc.animals_processed && loc.animals_processed.toLowerCase().includes(effectiveSearchTerm));

            const facilityType = mapFacilityType(loc.type, loc.establishment_name);
            const facilityTypeMatch = facilityType.displayLabel && facilityType.displayLabel.toLowerCase().includes(searchTerm);

            return nameMatch || animalMatch || facilityTypeMatch;
        });
    }

    filterLabs(allLabLocations, filterState, isAllStatesView) {
        const { selectedCountry, selectedState, searchTerm } = filterState;

        return allLabLocations.filter(lab => {
            const labState = getStateFromCityStateZip(lab['City-State-Zip']);
            
            if (!this.checkCountryMatch(lab, selectedCountry, labState)) return false;

            const stateMatch = isAllStatesView || labState === selectedState;
            if (!stateMatch) return false;

            if (!searchTerm) return true;

            const nameMatch = lab['Account Name'] && lab['Account Name'].toLowerCase().includes(searchTerm);
            const animalMatch = lab['Animals Tested On'] && lab['Animals Tested On'].toLowerCase().includes(searchTerm);
            
            const facilityTypeMatch = 'research laboratory'.includes(searchTerm) || 
                                     'laboratory'.includes(searchTerm) || 
                                     'research facility'.includes(searchTerm) ||
                                     'testing facility'.includes(searchTerm) ||
                                     'lab'.includes(searchTerm);

            return nameMatch || animalMatch || facilityTypeMatch;
        });
    }

    filterInspections(allInspectionReports, filterState, isAllStatesView) {
        const { selectedCountry, selectedState, searchTerm, showBreeders, showDealers, showExhibitors } = filterState;

        return allInspectionReports.filter(report => {
            const reportState = report['State'];
            
            if (!this.checkCountryMatch(report, selectedCountry, reportState)) return false;

            const stateMatch = isAllStatesView || reportState === selectedState;
            const nameMatch = !searchTerm || (report['Account Name'] && report['Account Name'].toLowerCase().includes(searchTerm));
            
            const licenseType = report['License Type'] || '';
            let facilityTypeMatch = false;
            if (searchTerm) {
                facilityTypeMatch = licenseType.toLowerCase().includes(searchTerm) ||
                                   ('breeder'.includes(searchTerm) && licenseType === 'Class A - Breeder') ||
                                   ('dealer'.includes(searchTerm) && licenseType === 'Class B - Dealer') ||
                                   ('exhibitor'.includes(searchTerm) && licenseType === 'Class C - Exhibitor');
            }
            
            const searchMatch = !searchTerm || nameMatch || facilityTypeMatch;
            if (!stateMatch || !searchMatch) return false;

            if (showBreeders && licenseType === 'Class A - Breeder') return true;
            if (showDealers && licenseType === 'Class B - Dealer') return true;
            if (showExhibitors && licenseType === 'Class C - Exhibitor') return true;
            return false;
        });
    }

    checkCountryMatch(item, selectedCountry, stateCode) {
        if (selectedCountry === 'all') return true;
        
        if (selectedCountry === 'US' && isUSState(stateCode)) return true;
        if (selectedCountry === 'DE' && isGermanState(stateCode)) return true;
        if (selectedCountry === 'ES' && isSpanishState(stateCode)) return true;
        if (selectedCountry === 'FR' && isFrenchLocation(item)) return true;
        if (selectedCountry === 'FR' && isFrenchState(stateCode)) return true; // Handle both location object and state code
        if (selectedCountry === 'CA' && isCanadianLocation(item)) return true;
        if (selectedCountry === 'CA' && isCanadianProvince(stateCode)) return true;
        if (selectedCountry === 'MX' && isMexicanLocation(item)) return true;
        if (selectedCountry === 'MX' && isMexicanState(stateCode)) return true;
        if (selectedCountry === 'DK' && isDanishLocation(item)) return true;
        if (selectedCountry === 'UK' && isUKState(stateCode)) return true;
        if (selectedCountry === 'NZ' && isNZLocation(item)) return true;
        
        return false;
    }

    checkStateMatch(item, selectedCountry, selectedState, isAllStatesView) {
        if (isAllStatesView) return true;
        if (selectedCountry === 'FR') return true; // French locations don't filter by state in the same way currently
        if (selectedCountry === 'DK') return item.city === selectedState;
        return item.state === selectedState;
    }

    updateStats(data) {
        const {
            slaughterhouses,
            processingPlants,
            breedingFacilities,
            exhibitionFacilities,
            filteredLabs,
            filteredInspections
        } = data;

        const {
            showSlaughter,
            showProcessing,
            showBreeders,
            showExhibitors,
            showLabs,
            showDealers
        } = this.getFilterState();

        let stats = [];
        let total = 0;
        
        if (showSlaughter && slaughterhouses.length > 0) {
            stats.push(`${slaughterhouses.length.toLocaleString()} Slaughterhouses`);
            total += slaughterhouses.length;
        }
        if (showProcessing && processingPlants.length > 0) {
            stats.push(`${processingPlants.length.toLocaleString()} Processing Plants`);
            total += processingPlants.length;
        }
        if (showBreeders && breedingFacilities.length > 0) {
            stats.push(`${breedingFacilities.length.toLocaleString()} Production Facilities`);
            total += breedingFacilities.length;
        }
        if (showExhibitors && exhibitionFacilities.length > 0) {
            stats.push(`${exhibitionFacilities.length.toLocaleString()} Exhibition Facilities`);
            total += exhibitionFacilities.length;
        }
        if (showLabs && filteredLabs.length > 0) {
            stats.push(`${filteredLabs.length.toLocaleString()} Animal Labs`);
            total += filteredLabs.length;
        }
        if ((showBreeders || showDealers || showExhibitors) && filteredInspections.length > 0) {
            stats.push(`${filteredInspections.length.toLocaleString()} Other Locations`);
            total += filteredInspections.length;
        }
        
        const statsText = stats.length > 0 ? `Showing: ${stats.join(', ')}` : 'No facilities match the current filters.';
        const totalText = total > 0 ? `<br><strong>Total: ${total.toLocaleString()}</strong>` : '';
        
        if (this.elements.statsContainer) {
            this.elements.statsContainer.innerHTML = statsText + totalText;
        }
    }
}

export const filterManager = new FilterManager();
