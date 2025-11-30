// @ts-nocheck
/**
 * =============================================================================
 * UNTIL EVERY CAGE IS EMPTY - MAP APPLICATION SCRIPT
 * =============================================================================
 * * This script powers the interactive map for the "Until Every Cage is Empty" project.
 * It handles:
 * - Initializing the Leaflet map and its controls.
 * - Fetching multiple datasets from the backend API.
 * - Creating and managing different map layers for each data type.
 * - Applying user filters (by state and data type).
 * - Dynamically generating detailed popups for each map marker.
 * - Updating the browser URL to allow for shareable map views.
 * * Main Dependencies: Leaflet.js, Leaflet.markercluster
 */

// Import constants and configuration
import { 
    BASE_ICON_SPECS, 
    PIN_SCALES, 
    API_ENDPOINTS,
    MAP_CONFIG,
    initializeDOMElements,
    EXTERNAL_URLS
} from './modules/constants.js';

// Import geographic utilities
import { 
    getStateDisplayName,
    isUSState,
    isGermanState,
    isSpanishState,
    isFrenchState,
    isCanadianProvince,
    isMexicanState,
    isFrenchLocation,
    isCanadianLocation,
    isDanishLocation,
    isMexicanLocation,
    isUKState,
    getSelectedCountryForState,
    getSelectedCountryForLocation,
    normalizeUsdaRow,
    normalizeLabRow,
    normalizeInspectionRow,
    toCsv,
    downloadText
} from './modules/geoUtils.js';

// Import icon management utilities
import { 
    createScaledIcon,
    getCurrentScale,
    getCurrentScaleIndex,
    setCurrentScaleIndex,
    setCustomScale,
    cycleToNextScale,
    refreshGlobalIcons,
    iconForType,
    mapFacilityType,
    updateAllMarkerIcons
} from './modules/iconUtils.js';

// Import Leaflet controls
import { 
    initializeCustomControls,
    moveControlsToBottom,
    createFullscreenControl,
    createFindMeControl,
    createPinScaleControl
} from './modules/leafletControls.js';

// Import popup builders
import { 
    buildLocationPopup,
    buildLabPopup,
    buildInspectionReportPopup
} from './modules/popupBuilder.js';

// Import drawer manager
import { initializeDrawer } from './modules/drawerManager.js';

if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js').catch((error) => {
        console.warn('ServiceWorker registration failed:', error);
    });
}

// =============================================================================
//  MAP INITIALIZATION & CONFIGURATION
// =============================================================================


// Define the absolute geographical boundaries of the map to prevent scrolling too far.
const southWest = L.latLng(MAP_CONFIG.southWest[0], MAP_CONFIG.southWest[1]);
const northEast = L.latLng(MAP_CONFIG.northEast[0], MAP_CONFIG.northEast[1]);
const worldBounds = L.latLngBounds(southWest, northEast);

// Create the main Leaflet map instance, centered on the continental US.
const map = L.map('map', {
    //maxBounds: worldBounds,
    //maxBoundsViscosity: 0.0, // Makes the map "bounce back" at the edges.
    zoomControl: false, // Disable default zoom control, we'll add it to bottom
    maxZoom: 19 // Set consistent maxZoom with tile layers
}).setView(MAP_CONFIG.center, MAP_CONFIG.zoom).setMinZoom(MAP_CONFIG.minZoom).setZoom(MAP_CONFIG.zoom);

// =============================================================================
//  WORLD WRAPPING FUNCTIONALITY
// =============================================================================

/**
 * Corrects coordinates to ensure they stay within world bounds by wrapping longitude
 * and clamping latitude, creating a seamless looping effect.
 */
function correctCoordinates(lat, lng) {
    // Wrap longitude: if it goes outside ±180, bring it back into range
    while (lng > 180) lng -= 360;
    while (lng < -180) lng += 360;
    
    // Clamp latitude to valid range (can't wrap north-south)
    lat = Math.max(-85, Math.min(85, lat)); // Using 85 instead of 90 to match web mercator limits
    
    return [lat, lng];
}

/**
 * Applies coordinate correction to the current map view
 */
function correctMapView() {
    const center = map.getCenter();
    const [correctedLat, correctedLng] = correctCoordinates(center.lat, center.lng);
    
    // Only update if coordinates actually changed
    if (Math.abs(center.lat - correctedLat) > 0.001 || Math.abs(center.lng - correctedLng) > 0.001) {
        map.setView([correctedLat, correctedLng], map.getZoom(), { animate: false });
    }
}

// Apply coordinate correction on map move events
map.on('moveend', correctMapView);

// Also apply correction on drag end for smoother experience
map.on('dragend', correctMapView);

// Add zoom control to bottom-right
L.control.zoom({ position: 'bottomright' }).addTo(map);

// Define the base map tile layers (the map imagery itself).
const streetMap = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap contributors'
});
// Create satellite base layer
const satelliteBase = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19,
    attribution: 'Tiles &copy; Esri'
});

// Create transportation overlay (roads, highways, major boundaries only - no POIs)
const transportationOverlay = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19,
    attribution: ''
});

// Combine satellite base with clean transportation overlay
const satelliteMap = L.layerGroup([satelliteBase, transportationOverlay]);

// Don't add any layer initially - Default View will handle this

// =============================================================================
//  DEFAULT VIEW CONTROL
// =============================================================================

// Track default view state
let isDefaultViewActive = true; // Start with Default View active
let currentActiveLayer = null; // Track which layer is currently active - start with null to force initial layer addition
let isAutoSwitching = false; // Flag to prevent event interference during automatic switching

// Configuration: Zoom threshold for switching to satellite view
// CHANGE THIS VALUE to adjust when satellite view activates
const SATELLITE_ZOOM_THRESHOLD = 13;

// Create a dummy layer for "Default View" option
const defaultViewLayer = L.layerGroup();

// Function to apply the appropriate layer based on zoom level
function applyZoomBasedLayer() {
    if (!isDefaultViewActive) return;
    
    const currentZoom = map.getZoom();
    let targetLayer;
    
    if (currentZoom > SATELLITE_ZOOM_THRESHOLD) {
        targetLayer = satelliteMap;
    } else {
        targetLayer = streetMap;
    }
    
    // Only switch if we need to change layers
    if (currentActiveLayer !== targetLayer) {
        isAutoSwitching = true; // Set flag to prevent event interference
        
        // Remove all base layers first to avoid conflicts
        map.removeLayer(streetMap);
        map.removeLayer(satelliteMap);
        
        // Add the target layer
        map.addLayer(targetLayer);
        currentActiveLayer = targetLayer;
        

        
        isAutoSwitching = false; // Clear flag
        console.log(`Auto-switched to ${currentZoom > SATELLITE_ZOOM_THRESHOLD ? 'satellite' : 'street'} view at zoom ${currentZoom}`);
    }
}

// Listen for zoom changes to auto-switch layers when in default view mode
map.on('zoomend', function() {
    applyZoomBasedLayer();
});

// Map layer definitions (layer switching handled automatically based on zoom)
const baseMaps = {
    "Default View": defaultViewLayer,
    "Street View": streetMap,
    "Satellite View": satelliteMap
};

// Initialize with Default View active
defaultViewLayer.addTo(map); // This makes "Default View" show as selected
applyZoomBasedLayer(); // Apply the appropriate layer based on initial zoom level

// Handle layer control events
map.on('baselayerchange', function(e) {
    // Ignore events triggered by our automatic switching
    if (isAutoSwitching) return;
    
    if (e.name === 'Default View') {
        isDefaultViewActive = true;
        console.log('Default View activated');
        // Remove the dummy layer that was just added
        map.removeLayer(defaultViewLayer);
        // Apply zoom-based layer immediately
        applyZoomBasedLayer();
    } else if (e.name === 'Street View' || e.name === 'Satellite View') {
        // User manually selected a specific layer - deactivate default view
        isDefaultViewActive = false;
        currentActiveLayer = e.layer;
        console.log('Default View deactivated - manual selection:', e.name);
    }
});

// =============================================================================
//  CUSTOM LEAFLET CONTROLS
// =============================================================================

// Initialize all custom controls
initializeCustomControls(map);

// Initialize drawer interactions
initializeDrawer();

// =============================================================================
//  LAYER GROUPS
// =============================================================================

// --- Application State Management ---
let allLocations = [];
let allLabLocations = [];
let allInspectionReports = [];
let isInitialDataLoading = true;
let clusterThreshold = 2800;

// Geographic utilities are now imported from geoUtils module

// --- Hierarchical State Selection Functions ---
function populateCountrySelector(allStateValues) {
    const hasUSStates = allStateValues.some(state => isUSState(state));
    const hasGermanStates = allStateValues.some(state => isGermanState(state));
    const hasSpanishStates = allStateValues.some(state => isSpanishState(state));
    const hasFrenchStates = allLocations.some(location => isFrenchLocation(location));
    const hasCanadianStates = allLocations.some(location => isCanadianLocation(location));
    const hasMexicanStates = allLocations.some(location => isMexicanLocation(location));
    const hasDanishStates = allLocations.some(location => isDanishLocation(location));
    const hasUKStates = allStateValues.some(state => isUKState(state));
    
    countrySelector.innerHTML = '<option value="all">All Countries</option>';
    
    if (hasUSStates) {
        const usOption = document.createElement('option');
        usOption.value = 'US';
        usOption.textContent = 'United States';
        countrySelector.appendChild(usOption);
    }
    
    if (hasGermanStates) {
        const deOption = document.createElement('option');
        deOption.value = 'DE';
        deOption.textContent = 'Deutschland';
        countrySelector.appendChild(deOption);
    }
    
    if (hasSpanishStates) {
        const esOption = document.createElement('option');
        esOption.value = 'ES';
        esOption.textContent = 'España';
        countrySelector.appendChild(esOption);
    }
    
    if (hasFrenchStates) {
        const frOption = document.createElement('option');
        frOption.value = 'FR';
        frOption.textContent = 'France';
        countrySelector.appendChild(frOption);
    }
    
    if (hasCanadianStates) {
        const caOption = document.createElement('option');
        caOption.value = 'CA';
        caOption.textContent = 'Canada';
        countrySelector.appendChild(caOption);
    }
    
    if (hasMexicanStates) {
        const mxOption = document.createElement('option');
        mxOption.value = 'MX';
        mxOption.textContent = 'México';
        countrySelector.appendChild(mxOption);
    }
    
    if (hasDanishStates) {
        const dkOption = document.createElement('option');
        dkOption.value = 'DK';
        dkOption.textContent = 'Danmark';
        countrySelector.appendChild(dkOption);
    }
    
    if (hasUKStates) {
        const ukOption = document.createElement('option');
        ukOption.value = 'UK';
        ukOption.textContent = 'United Kingdom';
        countrySelector.appendChild(ukOption);
    }
}

function populateStateSelector(allStateValues, selectedCountry = 'all') {
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
        // Filter for actual French department codes
        filteredStates = allStateValues.filter(state => isFrenchState(state));
    } else if (selectedCountry === 'CA') {
        // Filter for Canadian provinces
        filteredStates = allStateValues.filter(state => isCanadianProvince(state));
    } else if (selectedCountry === 'MX') {
        // Filter for Mexican states and deduplicate by normalizing to uppercase
        const mexicanStateMap = new Map();
        allStateValues.filter(state => isMexicanState(state)).forEach(state => {
            const normalized = state.toUpperCase();
            if (!mexicanStateMap.has(normalized)) {
                mexicanStateMap.set(normalized, state);
            }
        });
        filteredStates = Array.from(mexicanStateMap.values());
    } else if (selectedCountry === 'DK') {
        // For Danish locations, get unique city/region names from the locations
        filteredStates = [...new Set(allLocations
            .filter(location => isDanishLocation(location))
            .map(location => location.city)
            .filter(city => city && city.trim() !== '')
        )].sort();
    } else if (selectedCountry === 'UK') {
        filteredStates = allStateValues.filter(state => isUKState(state));
    }
    
    stateSelector.innerHTML = '<option value="all">All States/Provinces</option>';
    
    if (filteredStates.length === 0 && selectedCountry === 'FR') {
        // Special message for France when no department codes are available in the data
        const noStatesOption = document.createElement('option');
        noStatesOption.value = 'none';
        noStatesOption.textContent = '(Region data not available)';
        noStatesOption.disabled = true;
        stateSelector.appendChild(noStatesOption);
    } else if (filteredStates.length === 0 && selectedCountry === 'DK') {
        // Special message for Denmark when no city data is available
        const noStatesOption = document.createElement('option');
        noStatesOption.value = 'none';
        noStatesOption.textContent = '(City data not available)';
        noStatesOption.disabled = true;
        stateSelector.appendChild(noStatesOption);
    } else {
        // Sort states alphabetically by display name
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

// getSelectedCountryForState and getSelectedCountryForLocation functions now imported from geoUtils

// --- Layer Groups ---
// A SINGLE cluster group for all marker types
const unifiedClusterLayer = L.markerClusterGroup({ 
    chunkedLoading: true, 
    maxClusterRadius: MAP_CONFIG.maxClusterRadius, 
    disableClusteringAtZoom: MAP_CONFIG.disableClusteringAtZoom,
    spiderfyOnMaxZoom: false,
    showCoverageOnHover: false
});

// Individual layers for when clustering is disabled
const slaughterhouseFeatureLayer = L.layerGroup();
const processingFeatureLayer = L.layerGroup();
const labFeatureLayer = L.layerGroup();
const inspectionReportFeatureLayer = L.layerGroup();

// Function to update all marker icons with current scale
// Called by the pin scale control
function updateMapMarkerIcons() {
    updateAllMarkerIcons([unifiedClusterLayer, slaughterhouseFeatureLayer, processingFeatureLayer, labFeatureLayer, inspectionReportFeatureLayer]);
}


// --- DOM Element References ---
// Initialize all DOM elements using the constants module
const {
    slaughterhouseCheckbox,
    meatProcessingCheckbox, 
    testingLabsCheckbox,
    breedersCheckbox,
    dealersCheckbox,
    exhibitorsCheckbox,
    countrySelector,
    stateSelector,
    nameSearchInput,
    shareViewBtn,
    statsContainer,
    resetFiltersBtn,
    downloadCsvBtn,
    loader,
    loadingText,
    progressFill,
    progressPercentage,
    filterHeader,
    clusterThresholdSlider,
    clusterValueDisplay,
    iconSizeSlider,
    iconSizeDisplay
} = initializeDOMElements();

function updateProgress(percentage, message) {
    // Instant updates for maximum performance
    if (loadingText) loadingText.textContent = message;
    if (progressFill) progressFill.style.width = `${percentage}%`;
    if (progressPercentage) progressPercentage.textContent = `${Math.round(percentage)}%`;
    
    // Return a resolved promise to maintain compatibility
    return Promise.resolve();
}

// CSV export helpers and normalization functions now imported from geoUtils
if (downloadCsvBtn) {
    downloadCsvBtn.addEventListener('click', () => {
        const lf = window.__lastFiltered || {};
        const includeSlaughter = slaughterhouseCheckbox.checked;
        const includeProcessing = meatProcessingCheckbox.checked;
        const includeLabs = testingLabsCheckbox.checked;
        const includeBreeders = breedersCheckbox.checked;
        const includeDealers = dealersCheckbox.checked;
        const includeExhibitors = exhibitorsCheckbox.checked;
        const rows = [];
        if (includeSlaughter && Array.isArray(lf.slaughterhouses)) rows.push(...lf.slaughterhouses.map(loc => normalizeUsdaRow(loc, true, mapFacilityType)));
        if (includeProcessing && Array.isArray(lf.processingPlants)) rows.push(...lf.processingPlants.map(loc => normalizeUsdaRow(loc, false, mapFacilityType)));
        if (includeBreeders && Array.isArray(lf.breedingFacilities)) rows.push(...lf.breedingFacilities.map(loc => normalizeUsdaRow(loc, 'breeding', mapFacilityType)));
        if (includeExhibitors && Array.isArray(lf.exhibitionFacilities)) rows.push(...lf.exhibitionFacilities.map(loc => normalizeUsdaRow(loc, 'exhibition', mapFacilityType)));
        if (includeLabs && Array.isArray(lf.filteredLabs)) rows.push(...lf.filteredLabs.map(lab => normalizeLabRow(lab)));
        if (Array.isArray(lf.filteredInspections)) {
            lf.filteredInspections.forEach(r => {
                if ((includeBreeders && r['License Type'] === 'Class A - Breeder') ||
                    (includeDealers && r['License Type'] === 'Class B - Dealer') ||
                    (includeExhibitors && r['License Type'] === 'Class C - Exhibitor')) {
                    rows.push(normalizeInspectionRow(r));
                }
            });
        }
        if (rows.length === 0) {
            alert('No data to export for current filters.');
            return;
        }
        const csv = toCsv(rows);
        const isComplete = stateSelector.value === 'all'
            && (nameSearchInput.value.trim() === '')
            && slaughterhouseCheckbox.checked
            && meatProcessingCheckbox.checked
            && testingLabsCheckbox.checked
            && breedersCheckbox.checked
            && dealersCheckbox.checked
            && exhibitorsCheckbox.checked;
        const now = new Date();
        const yyyy = now.getFullYear();
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const dd = String(now.getDate()).padStart(2, '0');
        const dateStr = `${yyyy}-${mm}-${dd}`;
        const suffix = isComplete ? 'complete' : 'filtered';
        const filename = `untileverycage-visible-${dateStr}-${suffix}.csv`;
        downloadText(filename, csv);
    });
}

// =============================================================================
//  CORE APPLICATION LOGIC
// =============================================================================

function updateUrlWithCurrentState() {
    if (isInitialDataLoading) return;
    
    const center = map.getCenter();
    const zoom = map.getZoom();
    const params = new URLSearchParams({
        lat: center.lat.toFixed(5),
        lng: center.lng.toFixed(5),
        zoom: zoom,
        country: countrySelector.value,
        state: stateSelector.value,
    });

    const searchTerm = nameSearchInput.value;
    if (searchTerm) params.set('search', searchTerm);

    let activeLayers = [];
    if (slaughterhouseCheckbox.checked) activeLayers.push('slaughter');
    if (meatProcessingCheckbox.checked) activeLayers.push('processing');
    if (testingLabsCheckbox.checked) activeLayers.push('labs');
    if (breedersCheckbox.checked) activeLayers.push('breeders');
    if (dealersCheckbox.checked) activeLayers.push('dealers');
    if (exhibitorsCheckbox.checked) activeLayers.push('exhibitors');

    if (activeLayers.length > 0) {
        params.set('layers', activeLayers.join(','));
    }

    const newUrl = `${window.location.pathname}?${params.toString()}`;
    history.pushState({}, '', newUrl);
}

function applyFilters(shouldUpdateView = false, shouldCenterOnCountry = false) {
    const selectedCountry = countrySelector.value;
    const selectedState = stateSelector.value;
    const searchTerm = nameSearchInput.value.toLowerCase().trim();
    const isAllStatesView = selectedState === 'all';

    // --- 1. Clear all layers ---
    unifiedClusterLayer.clearLayers();
    [slaughterhouseFeatureLayer, processingFeatureLayer, labFeatureLayer, inspectionReportFeatureLayer]
        .forEach(layer => layer.clearLayers());
    
    map.removeLayer(unifiedClusterLayer);
    [slaughterhouseFeatureLayer, processingFeatureLayer, labFeatureLayer, inspectionReportFeatureLayer]
        .forEach(layer => map.removeLayer(layer));

    // --- 2. Filter data sources ---
    const showBreeders = breedersCheckbox.checked;
    const showDealers = dealersCheckbox.checked;
    const showExhibitors = exhibitorsCheckbox.checked;
    
    // Handle search term synonyms
    const searchSynonyms = {
        'cow': 'cattle',
        'cows': 'cattle'
    };
    const effectiveSearchTerm = searchSynonyms[searchTerm] || searchTerm;

    const filteredUsdaLocations = allLocations.filter(loc => {
        // Country filtering
        let countryMatch = selectedCountry === 'all';
        if (!countryMatch) {
            if (selectedCountry === 'US' && isUSState(loc.state)) {
                countryMatch = true;
            } else if (selectedCountry === 'DE' && isGermanState(loc.state)) {
                countryMatch = true;
            } else if (selectedCountry === 'ES' && isSpanishState(loc.state)) {
                countryMatch = true;
            } else if (selectedCountry === 'FR' && isFrenchLocation(loc)) {
                countryMatch = true;
            } else if (selectedCountry === 'CA' && isCanadianLocation(loc)) {
                countryMatch = true;
            } else if (selectedCountry === 'MX' && isMexicanLocation(loc)) {
                countryMatch = true;
            } else if (selectedCountry === 'DK' && isDanishLocation(loc)) {
                countryMatch = true;
            } else if (selectedCountry === 'UK' && isUKState(loc.state)) {
                countryMatch = true;
            }
        }
        if (!countryMatch) return false;

        // State filtering (within the selected country)
        let stateMatch = isAllStatesView || loc.state === selectedState;
        // Special handling for French locations - since current data doesn't have department codes,
        // French locations match any state selection when France is the selected country
        if (selectedCountry === 'FR') {
            stateMatch = true;
        }
        // Special handling for Danish locations - use city names for regional filtering
        if (selectedCountry === 'DK') {
            stateMatch = isAllStatesView || loc.city === selectedState;
        }
        if (!stateMatch) return false;

        if (!searchTerm) return true; // If no search term, only filter by country and state

        const nameMatch = (loc.establishment_name && loc.establishment_name.toLowerCase().includes(searchTerm)) ||
                          (loc.dbas && loc.dbas.toLowerCase().includes(searchTerm));
        
        const animalMatch = (loc.animals_slaughtered && loc.animals_slaughtered.toLowerCase().includes(effectiveSearchTerm)) ||
                            (loc.animals_processed && loc.animals_processed.toLowerCase().includes(effectiveSearchTerm));

        // Add facility type label search
        const facilityType = mapFacilityType(loc.type, loc.establishment_name);
        const facilityTypeMatch = facilityType.displayLabel && facilityType.displayLabel.toLowerCase().includes(searchTerm);

        return nameMatch || animalMatch || facilityTypeMatch;
    });

    const filteredLabs = allLabLocations.filter(lab => {
        const labState = getStateFromCityStateZip(lab['City-State-Zip']);
        
        // Country filtering
        let countryMatch = selectedCountry === 'all';
        if (!countryMatch) {
            if (selectedCountry === 'US' && isUSState(labState)) {
                countryMatch = true;
            } else if (selectedCountry === 'DE' && isGermanState(labState)) {
                countryMatch = true;
            } else if (selectedCountry === 'ES' && isSpanishState(labState)) {
                countryMatch = true;
            } else if (selectedCountry === 'FR' && isFrenchState(labState)) {
                countryMatch = true;
            } else if (selectedCountry === 'UK' && isUKState(labState)) {
                countryMatch = true;
            }
        }
        if (!countryMatch) return false;

        // State filtering (within the selected country)
        const stateMatch = isAllStatesView || labState === selectedState;
        if (!stateMatch) return false;

        if (!searchTerm) return true;

        const nameMatch = lab['Account Name'] && lab['Account Name'].toLowerCase().includes(searchTerm);
        const animalMatch = lab['Animals Tested On'] && lab['Animals Tested On'].toLowerCase().includes(searchTerm);
        
        // Add facility type label search for labs
        const facilityTypeMatch = 'research laboratory'.includes(searchTerm) || 
                                 'laboratory'.includes(searchTerm) || 
                                 'research facility'.includes(searchTerm) ||
                                 'testing facility'.includes(searchTerm) ||
                                 'lab'.includes(searchTerm);

        return nameMatch || animalMatch || facilityTypeMatch;
    });

    const filteredInspections = allInspectionReports.filter(report => {
        const reportState = report['State'];
        
        // Country filtering
        let countryMatch = selectedCountry === 'all';
        if (!countryMatch) {
            if (selectedCountry === 'US' && isUSState(reportState)) {
                countryMatch = true;
            } else if (selectedCountry === 'DE' && isGermanState(reportState)) {
                countryMatch = true;
            } else if (selectedCountry === 'ES' && isSpanishState(reportState)) {
                countryMatch = true;
            } else if (selectedCountry === 'FR' && isFrenchState(reportState)) {
                countryMatch = true;
            } else if (selectedCountry === 'UK' && isUKState(reportState)) {
                countryMatch = true;
            }
        }
        if (!countryMatch) return false;

        // State filtering (within the selected country)
        const stateMatch = isAllStatesView || reportState === selectedState;
        const nameMatch = !searchTerm || (report['Account Name'] && report['Account Name'].toLowerCase().includes(searchTerm));
        
        // Add facility type search for inspection reports
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

    // Group facilities by category using the new type field
    const slaughterhouses = filteredUsdaLocations.filter(loc => {
        const facilityType = mapFacilityType(loc.type, loc.establishment_name);
        return facilityType.category === 'slaughter';
    });
    const processingPlants = filteredUsdaLocations.filter(loc => {
        const facilityType = mapFacilityType(loc.type, loc.establishment_name);
        return facilityType.category === 'processing';
    });
    const breedingFacilities = filteredUsdaLocations.filter(loc => {
        const facilityType = mapFacilityType(loc.type, loc.establishment_name);
        return facilityType.category === 'breeder';
    });
    const exhibitionFacilities = filteredUsdaLocations.filter(loc => {
        const facilityType = mapFacilityType(loc.type, loc.establishment_name);
        return facilityType.category === 'exhibitor';
    });
    
    // --- 3. Decide on clustering and update stats ---
    let totalMarkerCount = 0;
    if (slaughterhouseCheckbox.checked) totalMarkerCount += slaughterhouses.length;
    if (meatProcessingCheckbox.checked) totalMarkerCount += processingPlants.length;
    if (breedersCheckbox.checked) totalMarkerCount += breedingFacilities.length;
    if (exhibitorsCheckbox.checked) totalMarkerCount += exhibitionFacilities.length;
    if (testingLabsCheckbox.checked) totalMarkerCount += filteredLabs.length;
    totalMarkerCount += filteredInspections.length;

    const useClustering = totalMarkerCount >= clusterThreshold;

    updateStats(slaughterhouses.length, processingPlants.length, filteredLabs.length, filteredInspections.length, breedingFacilities.length, exhibitionFacilities.length);

    // --- 4. Plot markers and add to layers ---
    const markerBounds = [];
    const addMarkerToLayer = (marker, layer) => {
        if (marker) {
            layer.addLayer(marker);
            if (!isAllStatesView || shouldCenterOnCountry) markerBounds.push(marker.getLatLng());
        }
    };

    const slaughterLayer = useClustering ? unifiedClusterLayer : slaughterhouseFeatureLayer;
    const processingLayer = useClustering ? unifiedClusterLayer : processingFeatureLayer;
    const labLayer = useClustering ? unifiedClusterLayer : labFeatureLayer;
    const inspectionLayer = useClustering ? unifiedClusterLayer : inspectionReportFeatureLayer;

    if (slaughterhouseCheckbox.checked) {
        slaughterhouses.forEach(loc => addMarkerToLayer(plotMarker(loc, 'usda-facility'), slaughterLayer));
    }
    if (meatProcessingCheckbox.checked) {
        processingPlants.forEach(loc => addMarkerToLayer(plotMarker(loc, 'usda-facility'), processingLayer));
    }
    if (breedersCheckbox.checked) {
        breedingFacilities.forEach(loc => addMarkerToLayer(plotMarker(loc, 'usda-facility'), slaughterLayer));
    }
    if (exhibitorsCheckbox.checked) {
        exhibitionFacilities.forEach(loc => addMarkerToLayer(plotMarker(loc, 'usda-facility'), slaughterLayer));
    }
    if (testingLabsCheckbox.checked) {
        filteredLabs.forEach(lab => addMarkerToLayer(plotMarker(lab, 'lab'), labLayer));
    }
    filteredInspections.forEach(report => addMarkerToLayer(plotMarker(report, 'inspection'), inspectionLayer));
    
    // Expose last filtered sets for CSV export
    window.__lastFiltered = {
        slaughterhouses,
        processingPlants,
        breedingFacilities,
        exhibitionFacilities,
        filteredLabs,
        filteredInspections
    };

    // --- 5. Add layers to map ---
    if (useClustering) {
        map.addLayer(unifiedClusterLayer);
    } else {
        if (slaughterhouseCheckbox.checked) map.addLayer(slaughterhouseFeatureLayer);
        if (meatProcessingCheckbox.checked) map.addLayer(processingFeatureLayer);
        if (testingLabsCheckbox.checked) map.addLayer(labFeatureLayer);
        if (filteredInspections.length > 0) map.addLayer(inspectionReportFeatureLayer);
    }
    
    // --- 6. Adjust map view ---
    if (shouldUpdateView) {
        if (!isAllStatesView && markerBounds.length > 0) {
            map.fitBounds(L.latLngBounds(markerBounds).pad(0.1));
        } else if (isAllStatesView) {
            if (shouldCenterOnCountry && selectedCountry !== 'all' && markerBounds.length > 0) {
                map.fitBounds(L.latLngBounds(markerBounds).pad(0.1));
            } else {
                map.setView([31.42841, -49.57343], 2).setZoom(2);
            }
        }
    }
    updateUrlWithCurrentState();
}

function plotMarker(data, type) {
    let lat, lng, iconType, popupContent;

    if (type === 'lab') {
        lat = data.latitude;
        lng = data.longitude;
        iconType = 'lab';
        popupContent = buildLabPopup(data);
    } else if (type === 'inspection') {
        lat = parseFloat(data['Geocodio Latitude']);
        lng = parseFloat(data['Geocodio Longitude']);
        
        // Choose icon type based on license type
        const licenseType = data['License Type'];
        if (licenseType === 'Class A - Breeder') {
            iconType = 'breeder';
        } else if (licenseType === 'Class B - Dealer') {
            iconType = 'dealer';
        } else if (licenseType === 'Class C - Exhibitor') {
            iconType = 'exhibitor';
        } else {
            iconType = 'breeder'; // fallback
        }
        
        popupContent = buildInspectionReportPopup(data);
    } else if (type === 'usda-facility') { // USDA Location with new facility types
        lat = data.latitude;
        lng = data.longitude;
        const facilityMapping = mapFacilityType(data.type, data.establishment_name);
        iconType = facilityMapping.iconType;
        popupContent = buildLocationPopup(data, facilityMapping.displayLabel);
    } else { // Legacy fallback for old USDA locations
        lat = data.latitude;
        lng = data.longitude;
        const isSlaughterhouse = type === true;
        iconType = isSlaughterhouse ? 'slaughter' : 'processing';
        popupContent = buildLocationPopup(data, isSlaughterhouse ? 'Slaughterhouse' : 'Processing Facility');
    }

    if (lat && lng) {
        const marker = L.marker([lat, lng], { icon: iconForType(iconType) });
        // store marker type for future resizing
        marker._iconType = iconType;
        marker.bindPopup(popupContent);
        return marker;
    }
    return null; // Return null if no coordinates
}

function updateStats(slaughterhouses, processing, labs, inspections, breeding, exhibition) {
    let stats = [];
    let total = 0;
    
    if (slaughterhouseCheckbox.checked && slaughterhouses > 0) {
        stats.push(`${slaughterhouses.toLocaleString()} Slaughterhouses`);
        total += slaughterhouses;
    }
    if (meatProcessingCheckbox.checked && processing > 0) {
        stats.push(`${processing.toLocaleString()} Processing Plants`);
        total += processing;
    }
    if (breedersCheckbox.checked && breeding > 0) {
        stats.push(`${breeding.toLocaleString()} Production Facilities`);
        total += breeding;
    }
    if (exhibitorsCheckbox.checked && exhibition > 0) {
        stats.push(`${exhibition.toLocaleString()} Exhibition Facilities`);
        total += exhibition;
    }
    if (testingLabsCheckbox.checked && labs > 0) {
        stats.push(`${labs.toLocaleString()} Animal Labs`);
        total += labs;
    }
    if ((breedersCheckbox.checked || dealersCheckbox.checked || exhibitorsCheckbox.checked) && inspections > 0) {
        stats.push(`${inspections.toLocaleString()} Other Locations`);
        total += inspections;
    }
    
    const statsText = stats.length > 0 ? `Showing: ${stats.join(', ')}` : 'No facilities match the current filters.';
    const totalText = total > 0 ? `<br><strong>Total: ${total.toLocaleString()}</strong>` : '';
    
    statsContainer.innerHTML = statsText + totalText;
}


// =============================================================================
//  EVENT LISTENERS & UTILITY FUNCTIONS
// =============================================================================

[slaughterhouseCheckbox, meatProcessingCheckbox, testingLabsCheckbox, breedersCheckbox, dealersCheckbox, exhibitorsCheckbox]
.forEach(checkbox => checkbox.addEventListener('change', () => applyFilters(false)));

// Country selector event handler - updates state dropdown when country changes
countrySelector.addEventListener('change', () => {
    const selectedCountry = countrySelector.value;
    let allStateValues = [...new Set([
        ...allLocations.map(loc => loc.state),
        ...allLabLocations.map(lab => getStateFromCityStateZip(lab['City-State-Zip'])),
        ...allInspectionReports.map(report => report['State'])
    ].filter(Boolean))];
    
    // Show state selector only if a specific country is selected
    if (selectedCountry === 'all') {
        stateSelector.style.display = 'none';
    } else {
        stateSelector.style.display = 'block';
    }
    
    // Special handling for French locations since the current data doesn't include department codes
    // This filters for any actual French department codes that might exist in the data
    if (selectedCountry === 'FR') {
        // Get any actual French state codes from the data
        const frenchStatesInData = allStateValues.filter(state => isFrenchState(state));
        if (frenchStatesInData.length > 0) {
            allStateValues = frenchStatesInData;
        } else {
            // If no department codes found, indicate that regions are not available in current data
            allStateValues = [];
        }
    }
    
    populateStateSelector(allStateValues, selectedCountry);
    stateSelector.value = 'all';
    applyFilters(true, true);
});

stateSelector.addEventListener('change', () => applyFilters(true));

nameSearchInput.addEventListener('input', (e) => {
    applyFilters(false);
    updateSearchResults(e.target.value);
});

function updateSearchResults(searchTerm) {
    const resultsDropdown = document.getElementById('search-results-dropdown');
    
    if (!searchTerm || searchTerm.trim() === '') {
        resultsDropdown.classList.remove('active');
        resultsDropdown.innerHTML = '';
        return;
    }
    
    const term = searchTerm.toLowerCase().trim();
    const nameMatches = [];
    const dbaMatches = [];
    
    allLocations.forEach(loc => {
        const nameMatch = (loc.establishment_name && loc.establishment_name.toLowerCase().includes(term));
        const dbaMatch = (loc.dbas && loc.dbas.toLowerCase().includes(term));
        
        const item = {
            id: loc.establishment_id,
            name: loc.establishment_name || 'Unknown',
            dba: loc.dbas || '',
            location: `${loc.city}, ${loc.state}`,
            lat: loc.latitude,
            lng: loc.longitude,
            type: 'usda-facility'
        };
        
        if (nameMatch) {
            nameMatches.push(item);
        } else if (dbaMatch) {
            dbaMatches.push(item);
        }
    });
    
    allLabLocations.forEach(lab => {
        const nameMatch = (lab['Account Name'] && lab['Account Name'].toLowerCase().includes(term));
        
        if (nameMatch) {
            const cityState = lab['City-State-Zip'] || '';
            nameMatches.push({
                id: lab['Customer Number_x'],
                name: lab['Account Name'] || 'Unknown',
                dba: '',
                location: cityState,
                lat: lab.latitude,
                lng: lab.longitude,
                type: 'lab'
            });
        }
    });
    
    const results = [...nameMatches, ...dbaMatches].slice(0, 10);
    
    if (results.length === 0) {
        resultsDropdown.innerHTML = '<div class="search-result-item" style="color: #999; cursor: default;">No facilities found</div>';
        resultsDropdown.classList.add('active');
        return;
    }
    
    resultsDropdown.innerHTML = results.map(result => `
        <div class="search-result-item" data-lat="${result.lat}" data-lng="${result.lng}" data-type="${result.type}" data-name="${result.name}">
            <span class="search-result-name">${result.name}</span>
            ${result.dba ? `<span class="search-result-type">${result.dba}</span>` : ''}
            <span class="search-result-location">${result.location}</span>
        </div>
    `).join('');
    
    resultsDropdown.classList.add('active');
    
    resultsDropdown.querySelectorAll('.search-result-item').forEach(item => {
        item.addEventListener('click', () => {
            const lat = parseFloat(item.dataset.lat);
            const lng = parseFloat(item.dataset.lng);
            const facilityName = item.dataset.name;
            
            map.setView([lat, lng], 16);
            resultsDropdown.classList.remove('active');
            nameSearchInput.value = facilityName;
            
            setTimeout(() => {
                const matchingMarkers = [];
                unifiedClusterLayer.eachLayer(layer => {
                    if (layer.getLatLng && 
                        Math.abs(layer.getLatLng().lat - lat) < 0.001 && 
                        Math.abs(layer.getLatLng().lng - lng) < 0.001) {
                        matchingMarkers.push(layer);
                    }
                });
                
                if (matchingMarkers.length === 0) {
                    [slaughterhouseFeatureLayer, processingFeatureLayer, labFeatureLayer, inspectionReportFeatureLayer].forEach(layer => {
                        layer.eachLayer(marker => {
                            if (marker.getLatLng && 
                                Math.abs(marker.getLatLng().lat - lat) < 0.001 && 
                                Math.abs(marker.getLatLng().lng - lng) < 0.001) {
                                matchingMarkers.push(marker);
                            }
                        });
                    });
                }
                
                if (matchingMarkers.length > 0) {
                    matchingMarkers[0].openPopup();
                }
            }, 100);
        });
    });
}

document.addEventListener('click', (e) => {
    const resultsDropdown = document.getElementById('search-results-dropdown');
    const searchInput = document.getElementById('name-search-input');
    
    if (!resultsDropdown.contains(e.target) && e.target !== searchInput) {
        resultsDropdown.classList.remove('active');
    }
});

if (clusterThresholdSlider) {
    clusterThresholdSlider.addEventListener('input', (e) => {
        clusterThreshold = parseInt(e.target.value);
        if (clusterValueDisplay) {
            clusterValueDisplay.textContent = clusterThreshold.toLocaleString();
        }
        applyFilters(false);
    });
}

if (iconSizeSlider) {
    iconSizeSlider.addEventListener('input', (e) => {
        const scale = parseFloat(e.target.value);
        if (iconSizeDisplay) {
            iconSizeDisplay.textContent = scale.toFixed(1);
        }
        setCustomScale(scale);
        refreshGlobalIcons();
        updateMapMarkerIcons();
    });
}

map.on('moveend', updateUrlWithCurrentState);

function getStateFromCityStateZip(cityStateZip) {
    if (!cityStateZip || typeof cityStateZip !== 'string') return null;
    const match = cityStateZip.match(/, ([A-Z]{2})/);
    return match ? match[1] : null;
}

shareViewBtn.addEventListener('click', () => {
    navigator.clipboard.writeText(window.location.href).then(() => {
        shareViewBtn.textContent = 'Link Copied!';
        shareViewBtn.classList.add('copied');
        setTimeout(() => {
            shareViewBtn.textContent = 'Share View';
            shareViewBtn.classList.remove('copied');
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy URL: ', err);
    });
});

resetFiltersBtn.addEventListener('click', () => {
    countrySelector.value = 'all';
    
    // Hide state selector when resetting to all countries
    stateSelector.style.display = 'none';
    
    // Repopulate state selector with all states since country is reset to 'all'
    const allStateValues = [...new Set([
        ...allLocations.map(loc => loc.state),
        ...allLabLocations.map(lab => getStateFromCityStateZip(lab['City-State-Zip'])),
        ...allInspectionReports.map(report => report['State'])
    ].filter(Boolean))];
    populateStateSelector(allStateValues, 'all');
    
    stateSelector.value = 'all';
    nameSearchInput.value = '';
    slaughterhouseCheckbox.checked = true;
    meatProcessingCheckbox.checked = true;
    testingLabsCheckbox.checked = true;
    breedersCheckbox.checked = true;
    dealersCheckbox.checked = true;
    exhibitorsCheckbox.checked = true;
    applyFilters(true); // true to reset the map view
});




map.on('popupopen', function (e) {
    const popupNode = e.popup.getElement();
    if (!popupNode) return;

    // Use a unique ID to track if a message is already showing
    const popupId = `popup-${e.popup._leaflet_id}`;

    const copyableElements = popupNode.querySelectorAll('.copyable-text');
    copyableElements.forEach(el => {
        el.addEventListener('click', function (event) {
            event.stopPropagation(); // Stop click from propagating to the map
            const textToCopy = this.getAttribute('data-copy');
            
            // Prevent multiple "Copied!" messages from appearing
            const existingFeedback = popupNode.querySelector('.copy-feedback-message');
            if (existingFeedback) {
                existingFeedback.remove();
            }

            if (textToCopy && textToCopy !== 'N/A') {
                navigator.clipboard.writeText(textToCopy).then(() => {
                    const feedbackEl = document.createElement('span');
                    feedbackEl.className = 'copy-feedback-message';
                    feedbackEl.textContent = 'Copied!';
                    
                    // Position the tooltip based on the clicked element
                    feedbackEl.style.left = `${this.offsetLeft}px`;
                    feedbackEl.style.top = `${this.offsetTop}px`;

                    // Add it to the DOM and then remove it after a delay
                    this.parentNode.appendChild(feedbackEl);
                    
                    setTimeout(() => {
                        feedbackEl.remove();
                    }, 1200); // Message disappears after 1.2 seconds

                }).catch(err => {
                    console.error('Failed to copy: ', err);
                });
            }
        });
    });
});
// =============================================================================
//  APPLICATION INITIALIZATION
// =============================================================================

async function initializeApp() {
    let urlParams; // Declare urlParams here, in the higher scope
    let loaderTimeout;

    try {
        // Show loader immediately for better UX with progress bar
        if(loader) loader.style.display = 'flex';

        // Start fetching all data
        updateProgress(0, "Fetching facility data...");
        
        // Try production URLs first, fallback to local if they fail
        const productionUrls = [
            API_ENDPOINTS.production.locations,
            API_ENDPOINTS.production.aphisReports,
            API_ENDPOINTS.production.inspectionReports
        ];
        
        const localUrls = [
            API_ENDPOINTS.local.locations,
            API_ENDPOINTS.local.aphisReports,
            API_ENDPOINTS.local.inspectionReports
        ];
        
        let urls = localUrls;
        let usdaResponse, aphisResponse, inspectionsResponse;
        
        try {
            // Create AbortController for timeout handling
            const abortController = new AbortController();
            const timeoutId = setTimeout(() => abortController.abort(), 30000); // 30 second timeout
            
            [usdaResponse, aphisResponse, inspectionsResponse] = await Promise.all([
                fetch(urls[0], { 
                    signal: abortController.signal,
                    headers: { 'Accept': 'application/json' },
                    mode: 'cors'
                }),
                fetch(urls[1], { 
                    signal: abortController.signal,
                    headers: { 'Accept': 'application/json' },
                    mode: 'cors'
                }),
                fetch(urls[2], { 
                    signal: abortController.signal,
                    headers: { 'Accept': 'application/json' },
                    mode: 'cors'
                })
            ]);
            
            clearTimeout(timeoutId);
        } catch (error) {
            console.warn('Production API failed, trying local development server:', error);
            updateProgress(20, "Trying local server...");
            
            // Try local development URLs as fallback
            const abortController = new AbortController();
            const timeoutId = setTimeout(() => abortController.abort(), 10000); // 10 second timeout for local
            
            [usdaResponse, aphisResponse, inspectionsResponse] = await Promise.all([
                fetch(localUrls[0], { 
                    signal: abortController.signal,
                    headers: { 'Accept': 'application/json' }
                }),
                fetch(localUrls[1], { 
                    signal: abortController.signal,
                    headers: { 'Accept': 'application/json' }
                }),
                fetch(localUrls[2], { 
                    signal: abortController.signal,
                    headers: { 'Accept': 'application/json' }
                })
            ]);
            
            clearTimeout(timeoutId);
        }

        updateProgress(50, "Processing responses...");

        if (!usdaResponse.ok) throw new Error(`Data request failed`);
        if (!aphisResponse.ok) throw new Error(`APHIS data request failed`);
        if (!inspectionsResponse.ok) throw new Error(`Inspections data request failed`);

        updateProgress(30, "Loading facility locations...");
        allLocations = await usdaResponse.json();
        
        updateProgress(70, "Loading APHIS reports...");
        allLabLocations = await aphisResponse.json();
        
        updateProgress(80, "Loading inspection reports...");
        allInspectionReports = await inspectionsResponse.json();
                
        updateProgress(100, "Done!");

        // Process locations - set country codes and extract state information
        allLocations = allLocations.map(location => {
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
        
        const allStateValues = [...new Set([
            ...allLocations.map(loc => loc.state),
            ...allLabLocations.map(lab => getStateFromCityStateZip(lab['City-State-Zip'])),
            ...allInspectionReports.map(report => report['State'])
        ].filter(Boolean))];
        allStateValues.sort();
        
        // Populate country and state dropdowns
        populateCountrySelector(allStateValues);
        populateStateSelector(allStateValues, 'all');
        
        // Hide state selector initially since we start with "All Countries"
        stateSelector.style.display = 'none';

        urlParams = new URLSearchParams(window.location.search); // Assign the value here
        const layersParam = urlParams.get('layers');
        if (layersParam) {
            const visibleLayers = new Set(layersParam.split(','));
            slaughterhouseCheckbox.checked = visibleLayers.has('slaughter');
            meatProcessingCheckbox.checked = visibleLayers.has('processing');
            testingLabsCheckbox.checked = visibleLayers.has('labs');
            breedersCheckbox.checked = visibleLayers.has('breeders');
            dealersCheckbox.checked = visibleLayers.has('dealers');
            exhibitorsCheckbox.checked = visibleLayers.has('exhibitors');
        }
        
        const urlCountry = urlParams.get('country') || 'all';
        const urlState = urlParams.get('state') || 'all';
        
        countrySelector.value = urlCountry;
        
        // If a specific country is pre-selected or a specific state is requested, 
        // make sure state selector is properly filtered
        if (urlCountry !== 'all') {
            stateSelector.style.display = 'block';
            let stateValuesForCountry = allStateValues;
            // Special handling for French locations - filter for actual French department codes
            if (urlCountry === 'FR') {
                const frenchStatesInData = allStateValues.filter(state => isFrenchState(state));
                stateValuesForCountry = frenchStatesInData.length > 0 ? frenchStatesInData : [];
            }
            populateStateSelector(stateValuesForCountry, urlCountry);
        } else if (urlState !== 'all') {
            const stateCountry = getSelectedCountryForState(urlState);
            if (stateCountry !== 'all') {
                stateSelector.style.display = 'block';
                countrySelector.value = stateCountry;
                let stateValuesForCountry = allStateValues;
                // Special handling for French locations - filter for actual French department codes
                if (stateCountry === 'FR') {
                    const frenchStatesInData = allStateValues.filter(state => isFrenchState(state));
                    stateValuesForCountry = frenchStatesInData.length > 0 ? frenchStatesInData : [];
                }
                populateStateSelector(stateValuesForCountry, stateCountry);
            }
        }
        
        stateSelector.value = urlState;
        nameSearchInput.value = urlParams.get('search') || '';

        let shouldUpdateViewOnLoad = true;
        if (urlParams.has('lat') && urlParams.has('lng') && urlParams.has('zoom')) {
            map.setView([parseFloat(urlParams.get('lat')), parseFloat(urlParams.get('lng'))], parseInt(urlParams.get('zoom')));
            shouldUpdateViewOnLoad = false;
        }

        applyFilters(shouldUpdateViewOnLoad);


    } catch (error) {
        console.error('Failed to fetch initial data:', error);
        let errorMessage = 'Could not load map data. Please try refreshing the page.';
        
        if (error.name === 'AbortError') {
            errorMessage = 'Request timed out. Please check your internet connection and try refreshing the page.';
        } else if (error.message && (error.message.includes('Failed to fetch') || error.message.includes('NetworkError'))) {
            errorMessage = 'Network error. Please check your internet connection and try refreshing the page.';
        } else if (error.message && error.message.includes('CORS')) {
            errorMessage = 'Server configuration issue. Please try again later.';
        }
        
        if(statsContainer) statsContainer.innerHTML = errorMessage;
        updateProgress(0, "Error loading data");
    } finally {
        clearTimeout(loaderTimeout);
        if(loader) loader.style.display = 'none';
        isInitialDataLoading = false;
        if(urlParams && !urlParams.has('lat')) { // Check if urlParams exists before using it
            updateUrlWithCurrentState();
        }
    }
}
initializeApp();
