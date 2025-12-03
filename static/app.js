// @ts-nocheck
/**
 * =============================================================================
 * UNTIL EVERY CAGE IS EMPTY - MAP APPLICATION SCRIPT
 * =============================================================================
 * Refactored to use modular managers.
 */

import { dataManager } from './modules/DataManager.js';
import { mapManager } from './modules/MapManager.js';
import { filterManager } from './modules/FilterManager.js';
import { searchManager } from './modules/SearchManager.js';
import { exportManager } from './modules/ExportManager.js';
import { i18n } from './modules/translationManager.js';
import { initializeWelcomeModal } from './modules/welcomeModal.js';
import { initializeDrawer } from './modules/drawerManager.js';
import { initializeDOMElements } from './modules/constants.js';
import { 
    getSelectedCountryForState,
    isFrenchState
} from './modules/geoUtils.js';
import { 
    setCustomScale, 
    refreshGlobalIcons,
    mapFacilityType
} from './modules/iconUtils.js';

// Service Worker Registration
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js').catch((error) => {
        console.warn('ServiceWorker registration failed:', error);
    });
}

// Initialize DOM elements
const elements = initializeDOMElements();
let lastFilteredData = {};

// Progress Update Function
function updateProgress(percentage, message) {
    if (elements.loadingText) elements.loadingText.textContent = message;
    if (elements.progressFill) elements.progressFill.style.width = `${percentage}%`;
    if (elements.progressPercentage) elements.progressPercentage.textContent = `${Math.round(percentage)}%`;
    return Promise.resolve();
}

document.addEventListener('DOMContentLoaded', async () => {
    await i18n.init();
    initializeWelcomeModal();

    // Initialize Map
    const map = mapManager.init('map');
    initializeDrawer();

    // Expose updateMapMarkerIcons for PinScale control
    window.updateMapMarkerIcons = () => mapManager.updateIcons();

    // Subscribe to language changes
    i18n.subscribe(() => {
        map.eachLayer(layer => {
            if (layer instanceof L.Popup) {
                const source = layer._source;
                if (source && source.getPopup) {
                    const popup = source.getPopup();
                    const content = popup.getContent();
                    if (typeof content === 'function') {
                        layer.setContent(content);
                        layer.update();
                    }
                }
            }
        });
        
        const langSelector = document.getElementById('language-selector');
        if (langSelector) langSelector.value = i18n.currentLocale;
    });

    const langSelector = document.getElementById('language-selector');
    if (langSelector) {
        langSelector.value = i18n.currentLocale;
        langSelector.addEventListener('change', (e) => {
            i18n.setLanguage(e.target.value);
        });
    }

    // Initialize Application Data
    await initializeApp();

    // Event Listeners
    setupEventListeners();
});

async function initializeApp() {
    try {
        if (elements.loader) elements.loader.style.display = 'flex';

        // Fetch Data
        await dataManager.fetchData(updateProgress);

        // Populate Selectors
        const allStateValues = dataManager.getAllStateValues();
        filterManager.populateCountrySelector(allStateValues, dataManager.getAllLocations());
        filterManager.populateStateSelector(allStateValues, dataManager.getAllLocations(), 'all');
        
        elements.stateSelector.style.display = 'none';

        // Handle URL Params
        const urlParams = new URLSearchParams(window.location.search);
        const layersParam = urlParams.get('layers');
        if (layersParam) {
            const visibleLayers = new Set(layersParam.split(','));
            elements.slaughterhouseCheckbox.checked = visibleLayers.has('slaughter');
            elements.meatProcessingCheckbox.checked = visibleLayers.has('processing');
            elements.testingLabsCheckbox.checked = visibleLayers.has('labs');
            elements.breedersCheckbox.checked = visibleLayers.has('breeders');
            elements.dealersCheckbox.checked = visibleLayers.has('dealers');
            elements.exhibitorsCheckbox.checked = visibleLayers.has('exhibitors');
        }

        const urlCountry = urlParams.get('country') || 'all';
        const urlState = urlParams.get('state') || 'all';

        elements.countrySelector.value = urlCountry;

        if (urlCountry !== 'all') {
            elements.stateSelector.style.display = 'block';
            let stateValuesForCountry = allStateValues;
            if (urlCountry === 'FR') {
                const frenchStatesInData = allStateValues.filter(state => isFrenchState(state));
                stateValuesForCountry = frenchStatesInData.length > 0 ? frenchStatesInData : [];
            }
            filterManager.populateStateSelector(stateValuesForCountry, dataManager.getAllLocations(), urlCountry);
        } else if (urlState !== 'all') {
            const stateCountry = getSelectedCountryForState(urlState);
            if (stateCountry !== 'all') {
                elements.stateSelector.style.display = 'block';
                elements.countrySelector.value = stateCountry;
                let stateValuesForCountry = allStateValues;
                if (stateCountry === 'FR') {
                    const frenchStatesInData = allStateValues.filter(state => isFrenchState(state));
                    stateValuesForCountry = frenchStatesInData.length > 0 ? frenchStatesInData : [];
                }
                filterManager.populateStateSelector(stateValuesForCountry, dataManager.getAllLocations(), stateCountry);
            }
        }

        elements.stateSelector.value = urlState;
        elements.nameSearchInput.value = urlParams.get('search') || '';

        let shouldUpdateViewOnLoad = true;
        if (urlParams.has('lat') && urlParams.has('lng') && urlParams.has('zoom')) {
            mapManager.map.setView([parseFloat(urlParams.get('lat')), parseFloat(urlParams.get('lng'))], parseInt(urlParams.get('zoom')));
            shouldUpdateViewOnLoad = false;
        }

        applyFilters(shouldUpdateViewOnLoad);

    } catch (error) {
        console.error('Failed to initialize app:', error);
        if (elements.statsContainer) elements.statsContainer.innerHTML = 'Error loading data. Please refresh.';
        updateProgress(0, "Error loading data");
    } finally {
        if (elements.loader) elements.loader.style.display = 'none';
        const urlParams = new URLSearchParams(window.location.search);
        if (!urlParams.has('lat')) {
            updateUrlWithCurrentState();
        }
    }
}

function applyFilters(shouldUpdateView = false, shouldCenterOnCountry = false) {
    const filteredData = filterManager.filterData(
        dataManager.getAllLocations(),
        dataManager.getAllLabLocations(),
        dataManager.getAllInspectionReports()
    );

    lastFilteredData = filteredData;

    filterManager.updateStats(filteredData);

    const filterState = filterManager.getFilterState();
    
    mapManager.updateMarkers(filteredData, {
        ...filterState,
        useClustering: (
            (filterState.showSlaughter ? filteredData.slaughterhouses.length : 0) +
            (filterState.showProcessing ? filteredData.processingPlants.length : 0) +
            (filterState.showBreeders ? filteredData.breedingFacilities.length : 0) +
            (filterState.showExhibitors ? filteredData.exhibitionFacilities.length : 0) +
            (filterState.showLabs ? filteredData.filteredLabs.length : 0) +
            filteredData.filteredInspections.length
        ) >= filterState.clusterThreshold,
        isAllStatesView: filterState.selectedState === 'all',
        shouldCenterOnCountry,
        shouldUpdateView,
        selectedCountry: filterState.selectedCountry
    });

    updateUrlWithCurrentState();
}

function updateUrlWithCurrentState() {
    if (dataManager.isInitialDataLoading) return;
    
    const center = mapManager.map.getCenter();
    const zoom = mapManager.map.getZoom();
    const params = new URLSearchParams({
        lat: center.lat.toFixed(5),
        lng: center.lng.toFixed(5),
        zoom: zoom,
        country: elements.countrySelector.value,
        state: elements.stateSelector.value,
    });

    const searchTerm = elements.nameSearchInput.value;
    if (searchTerm) params.set('search', searchTerm);

    let activeLayers = [];
    if (elements.slaughterhouseCheckbox.checked) activeLayers.push('slaughter');
    if (elements.meatProcessingCheckbox.checked) activeLayers.push('processing');
    if (elements.testingLabsCheckbox.checked) activeLayers.push('labs');
    if (elements.breedersCheckbox.checked) activeLayers.push('breeders');
    if (elements.dealersCheckbox.checked) activeLayers.push('dealers');
    if (elements.exhibitorsCheckbox.checked) activeLayers.push('exhibitors');

    if (activeLayers.length > 0) {
        params.set('layers', activeLayers.join(','));
    }

    const newUrl = `${window.location.pathname}?${params.toString()}`;
    history.pushState({}, '', newUrl);
}

function setupEventListeners() {
    // Checkboxes
    [
        elements.slaughterhouseCheckbox, 
        elements.meatProcessingCheckbox, 
        elements.testingLabsCheckbox, 
        elements.breedersCheckbox, 
        elements.dealersCheckbox, 
        elements.exhibitorsCheckbox
    ].forEach(checkbox => {
        if (checkbox) checkbox.addEventListener('change', () => applyFilters(false));
    });

    // Country Selector
    elements.countrySelector.addEventListener('change', () => {
        const selectedCountry = elements.countrySelector.value;
        let allStateValues = dataManager.getAllStateValues();
        
        if (selectedCountry === 'all') {
            elements.stateSelector.style.display = 'none';
        } else {
            elements.stateSelector.style.display = 'block';
        }
        
        if (selectedCountry === 'FR') {
            const frenchStatesInData = allStateValues.filter(state => isFrenchState(state));
            if (frenchStatesInData.length > 0) {
                allStateValues = frenchStatesInData;
            } else {
                allStateValues = [];
            }
        }
        
        filterManager.populateStateSelector(allStateValues, dataManager.getAllLocations(), selectedCountry);
        elements.stateSelector.value = 'all';
        applyFilters(true, true);
    });

    // State Selector
    elements.stateSelector.addEventListener('change', () => applyFilters(true));

    // Debounce function
    const debounce = (func, wait) => {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    };

    // Search Input with Debounce
    const handleSearch = debounce((e) => {
        applyFilters(false);
        searchManager.updateSearchResults(
            e.target.value, 
            dataManager.getAllLocations(), 
            dataManager.getAllLabLocations(), 
            mapManager
        );
    }, 300);

    elements.nameSearchInput.addEventListener('input', handleSearch);

    // Sliders
    if (elements.clusterThresholdSlider) {
        elements.clusterThresholdSlider.addEventListener('input', (e) => {
            filterManager.clusterThreshold = parseInt(e.target.value);
            if (elements.clusterValueDisplay) {
                elements.clusterValueDisplay.textContent = filterManager.clusterThreshold.toLocaleString();
            }
            applyFilters(false);
        });
    }

    if (elements.iconSizeSlider) {
        elements.iconSizeSlider.addEventListener('input', (e) => {
            const scale = parseFloat(e.target.value);
            if (elements.iconSizeDisplay) {
                elements.iconSizeDisplay.textContent = scale.toFixed(1);
            }
            setCustomScale(scale);
            refreshGlobalIcons();
            mapManager.updateIcons();
        });
    }

    // Map Move
    mapManager.map.on('moveend', updateUrlWithCurrentState);

    // Share Button
    elements.shareViewBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(window.location.href).then(() => {
            elements.shareViewBtn.textContent = 'Link Copied!';
            elements.shareViewBtn.classList.add('copied');
            setTimeout(() => {
                elements.shareViewBtn.textContent = 'Share View';
                elements.shareViewBtn.classList.remove('copied');
            }, 2000);
        }).catch(err => {
            console.error('Failed to copy URL: ', err);
        });
    });

    // Reset Button
    elements.resetFiltersBtn.addEventListener('click', () => {
        elements.countrySelector.value = 'all';
        elements.stateSelector.style.display = 'none';
        
        const allStateValues = dataManager.getAllStateValues();
        filterManager.populateStateSelector(allStateValues, dataManager.getAllLocations(), 'all');
        
        elements.stateSelector.value = 'all';
        elements.nameSearchInput.value = '';
        elements.slaughterhouseCheckbox.checked = true;
        elements.meatProcessingCheckbox.checked = true;
        elements.testingLabsCheckbox.checked = true;
        elements.breedersCheckbox.checked = true;
        elements.dealersCheckbox.checked = true;
        elements.exhibitorsCheckbox.checked = true;
        
        applyFilters(true);
    });

    // Download CSV
    if (elements.downloadCsvBtn) {
        elements.downloadCsvBtn.addEventListener('click', () => {
            const lf = lastFilteredData || {};
            const includeSlaughter = elements.slaughterhouseCheckbox.checked;
            const includeProcessing = elements.meatProcessingCheckbox.checked;
            const includeLabs = elements.testingLabsCheckbox.checked;
            const includeBreeders = elements.breedersCheckbox.checked;
            const includeDealers = elements.dealersCheckbox.checked;
            const includeExhibitors = elements.exhibitorsCheckbox.checked;
            
            const isComplete = elements.stateSelector.value === 'all'
                && (elements.nameSearchInput.value.trim() === '')
                && includeSlaughter && includeProcessing && includeLabs 
                && includeBreeders && includeDealers && includeExhibitors;

            exportManager.exportData(lf, {
                includeSlaughter,
                includeProcessing,
                includeLabs,
                includeBreeders,
                includeDealers,
                includeExhibitors,
                isComplete
            }, mapFacilityType);
        });
    }

    // Popup Copy Functionality
    mapManager.map.on('popupopen', function (e) {
        const popupNode = e.popup.getElement();
        if (!popupNode) return;

        const copyableElements = popupNode.querySelectorAll('.copyable-text');
        copyableElements.forEach(el => {
            el.addEventListener('click', function (event) {
                event.stopPropagation();
                const textToCopy = this.getAttribute('data-copy');
                
                const existingFeedback = popupNode.querySelector('.copy-feedback-message');
                if (existingFeedback) existingFeedback.remove();

                if (textToCopy && textToCopy !== 'N/A') {
                    navigator.clipboard.writeText(textToCopy).then(() => {
                        const feedbackEl = document.createElement('span');
                        feedbackEl.className = 'copy-feedback-message';
                        feedbackEl.textContent = 'Copied!';
                        feedbackEl.style.left = `${this.offsetLeft}px`;
                        feedbackEl.style.top = `${this.offsetTop}px`;
                        this.parentNode.appendChild(feedbackEl);
                        setTimeout(() => feedbackEl.remove(), 1200);
                    }).catch(err => console.error('Failed to copy: ', err));
                }
            });
        });
    });
}
