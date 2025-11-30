/**
 * =============================================================================
 * CONSTANTS AND CONFIGURATION
 * =============================================================================
 * Centralized constants, DOM selectors, and configuration values
 * for the Until Every Cage is Empty map application.
 */

// =============================================================================
// ICON SPECIFICATIONS
// =============================================================================

export const BASE_ICON_SPECS = {
    slaughter: {
        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
        iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
    },
    processing: {
        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-grey.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
        iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
    },
    lab: {
        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-violet.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
        iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
    },
    breeder: {
        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-yellow.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
        iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
    },
    dealer: {
        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-orange.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
        iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
    },
    exhibitor: {
        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
        iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
    }
};

// =============================================================================
// SCALING AND CONFIGURATION
// =============================================================================

export const PIN_SCALES = [0.5, 0.75, 1];

// =============================================================================
// API ENDPOINTS
// =============================================================================

export const API_ENDPOINTS = {
    production: {
        locations: 'https://untileverycage-ikbq.shuttle.app/api/locations',
        aphisReports: 'https://untileverycage-ikbq.shuttle.app/api/aphis-reports', 
        inspectionReports: 'https://untileverycage-ikbq.shuttle.app/api/inspection-reports'
    },
    local: {
        locations: 'http://127.0.0.1:8000/api/locations',
        aphisReports: 'http://127.0.0.1:8000/api/aphis-reports',
        inspectionReports: 'http://127.0.0.1:8000/api/inspection-reports'
    }
};

// =============================================================================
// MAP CONFIGURATION
// =============================================================================

export const MAP_CONFIG = {
    // Initial map view
    center: [31.42841, -49.57343],
    zoom: 2,
    minZoom: 2,
    
    // World bounds
    southWest: [-90, -180],
    northEast: [90, 180],
    
    // Cluster settings
    maxClusterRadius: 50,
    disableClusteringAtZoom: 10
};

// =============================================================================
// DOM ELEMENT SELECTORS
// =============================================================================

export const DOM_SELECTORS = {
    // Map container
    map: 'map',
    
    // Filter checkboxes
    slaughterhousesCheckbox: 'slaughterhousesCheckbox',
    meatProcessingPlantsCheckbox: 'meatProcessingPlantsCheckbox', 
    testingLabsCheckbox: 'testingLabsCheckbox',
    breedersCheckbox: 'breedersCheckbox',
    dealersCheckbox: 'dealersCheckbox',
    exhibitorsCheckbox: 'exhibitorsCheckbox',
    
    // Filter controls
    countrySelector: 'country-selector',
    stateSelector: 'state-selector',
    nameSearchInput: 'name-search-input',
    
    // Action buttons
    shareViewBtn: 'share-view-btn',
    resetFiltersBtn: 'reset-filters-btn', 
    downloadCsvBtn: 'download-csv-btn',
    
    // Status and loading
    statsContainer: 'stats-container',
    loadingIndicator: 'loading-indicator',
    
    // Progress elements (query selectors)
    loadingText: '.loading-text',
    progressFill: '.progress-fill',
    progressPercentage: '.progress-percentage',
    
    // Filter UI
    filterHeader: '.drawer-header'
};

// =============================================================================
// DOM ELEMENT GETTERS
// =============================================================================
// Helper functions to get DOM elements - called once on app initialization

export function initializeDOMElements() {
    return {
        // Filter checkboxes
        slaughterhouseCheckbox: document.getElementById(DOM_SELECTORS.slaughterhousesCheckbox),
        meatProcessingCheckbox: document.getElementById(DOM_SELECTORS.meatProcessingPlantsCheckbox),
        testingLabsCheckbox: document.getElementById(DOM_SELECTORS.testingLabsCheckbox), 
        breedersCheckbox: document.getElementById(DOM_SELECTORS.breedersCheckbox),
        dealersCheckbox: document.getElementById(DOM_SELECTORS.dealersCheckbox),
        exhibitorsCheckbox: document.getElementById(DOM_SELECTORS.exhibitorsCheckbox),
        
        // Animal filter checkboxes
        cattleCheckbox: document.getElementById(DOM_SELECTORS.cattleCheckbox),
        pigsCheckbox: document.getElementById(DOM_SELECTORS.pigsCheckbox),
        chickensCheckbox: document.getElementById(DOM_SELECTORS.chickensCheckbox),
        turkeysCheckbox: document.getElementById(DOM_SELECTORS.turkeysCheckbox),
        sheepCheckbox: document.getElementById(DOM_SELECTORS.sheepCheckbox),
        goatsCheckbox: document.getElementById(DOM_SELECTORS.goatsCheckbox),
        duckCheckbox: document.getElementById(DOM_SELECTORS.duckCheckbox),
        rabbitCheckbox: document.getElementById(DOM_SELECTORS.rabbitCheckbox),
        dogsCheckbox: document.getElementById(DOM_SELECTORS.dogsCheckbox),
        catsCheckbox: document.getElementById(DOM_SELECTORS.catsCheckbox),
        guineaPigsCheckbox: document.getElementById(DOM_SELECTORS.guineaPigsCheckbox),
        hamstersCheckbox: document.getElementById(DOM_SELECTORS.hamstersCheckbox),
        primatesCheckbox: document.getElementById(DOM_SELECTORS.primatesCheckbox),
        otherFarmCheckbox: document.getElementById(DOM_SELECTORS.otherFarmCheckbox),
        otherAnimalsCheckbox: document.getElementById(DOM_SELECTORS.otherAnimalsCheckbox),
        
        // Filter controls
        countrySelector: document.getElementById(DOM_SELECTORS.countrySelector),
        stateSelector: document.getElementById(DOM_SELECTORS.stateSelector),
        nameSearchInput: document.getElementById(DOM_SELECTORS.nameSearchInput),
        
        // Action buttons
        shareViewBtn: document.getElementById(DOM_SELECTORS.shareViewBtn),
        resetFiltersBtn: document.getElementById(DOM_SELECTORS.resetFiltersBtn),
        downloadCsvBtn: document.getElementById(DOM_SELECTORS.downloadCsvBtn),
        
        // Status and loading
        statsContainer: document.getElementById(DOM_SELECTORS.statsContainer),
        loader: document.getElementById(DOM_SELECTORS.loadingIndicator),
        
        // Progress elements
        loadingText: document.querySelector(DOM_SELECTORS.loadingText),
        progressFill: document.querySelector(DOM_SELECTORS.progressFill), 
        progressPercentage: document.querySelector(DOM_SELECTORS.progressPercentage),
        
        // Filter UI
        filterHeader: document.querySelector(DOM_SELECTORS.filterHeader)
    };
}

// =============================================================================
// EXTERNAL URLS
// =============================================================================

export const EXTERNAL_URLS = {
    aphis: {
        inspectionReports: 'https://aphis.my.site.com/PublicSearchTool/s/inspection-reports',
        annualReports: 'https://aphis.my.site.com/PublicSearchTool/s/annual-reports'
    },
    eFileAphis: {
        inspectionReports: 'https://efile.aphis.usda.gov/PublicSearchTool/s/inspection-reports',
        annualReports: 'https://efile.aphis.usda.gov/PublicSearchTool/s/annual-reports'
    }
};

// =============================================================================
// STATE AND COUNTRY NAME MAPPINGS
// =============================================================================

export const US_STATE_NAMES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California',
    'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware', 'FL': 'Florida', 'GA': 'Georgia',
    'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa',
    'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
    'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri',
    'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey',
    'NM': 'New Mexico', 'NY': 'New York', 'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio',
    'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
    'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont',
    'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming',
    'DC': 'District of Columbia', 'AS': 'American Samoa', 'GU': 'Guam', 'MP': 'Northern Mariana Islands',
    'PR': 'Puerto Rico', 'VI': 'U.S. Virgin Islands'
};

export const GERMAN_STATE_NAMES = {
    'BW': 'Baden-Württemberg', 'BY': 'Bayern', 'BE': 'Berlin', 'BB': 'Brandenburg',
    'HB': 'Bremen', 'HH': 'Hamburg', 'HE': 'Hessen', 'MV': 'Mecklenburg-Vorpommern',
    'NI': 'Niedersachsen', 'NW': 'Nordrhein-Westfalen', 'RP': 'Rheinland-Pfalz',
    'SL': 'Saarland', 'SN': 'Sachsen', 'ST': 'Sachsen-Anhalt', 'SH': 'Schleswig-Holstein', 'TH': 'Thüringen',
    'DE_UNKNOWN': 'Deutschland (Unspecified)'
};

export const SPANISH_STATE_NAMES = {
    'Andalucía': 'Andalucía',
    'Aragón': 'Aragón',
    'Asturias': 'Asturias',
    'Cantabria': 'Cantabria',
    'Castilla-La Mancha': 'Castilla-La Mancha',
    'Castilla y León': 'Castilla y León',
    'Cataluña': 'Cataluña',
    'Ceuta': 'Ceuta',
    'Comunidad de Madrid': 'Comunidad de Madrid',
    'Comunidad Valenciana': 'Comunidad Valenciana',
    'Extremadura': 'Extremadura',
    'Galicia': 'Galicia',
    'Ililles Balears': 'Illes Balears',
    'La Coruña': 'La Coruña',
    'La Rioja': 'La Rioja',
    'Navarra': 'Navarra',
    'País Vasco': 'País Vasco',
    'Región de Murcia': 'Región de Murcia',
    'ES_UNKNOWN': 'España (Unspecified)'
};

export const FRENCH_STATE_NAMES = {
    '01': 'Ain', '02': 'Aisne', '03': 'Allier', '04': 'Alpes-de-Haute-Provence', '05': 'Hautes-Alpes',
    '06': 'Alpes-Maritimes', '07': 'Ardèche', '08': 'Ardennes', '09': 'Ariège', '10': 'Aube',
    '11': 'Aude', '12': 'Aveyron', '13': 'Bouches-du-Rhône', '14': 'Calvados', '15': 'Cantal',
    '16': 'Charente', '17': 'Charente-Maritime', '18': 'Cher', '19': 'Corrèze', '21': 'Côte-d\'Or',
    '22': 'Côtes-d\'Armor', '23': 'Creuse', '24': 'Dordogne', '25': 'Doubs', '26': 'Drôme',
    '27': 'Eure', '28': 'Eure-et-Loir', '29': 'Finistère', '30': 'Gard', '31': 'Haute-Garonne',
    '32': 'Gers', '33': 'Gironde', '34': 'Hérault', '35': 'Ille-et-Vilaine', '36': 'Indre',
    '37': 'Indre-et-Loire', '38': 'Isère', '39': 'Jura', '40': 'Landes', '41': 'Loir-et-Cher',
    '42': 'Loire', '43': 'Haute-Loire', '44': 'Loire-Atlantique', '45': 'Loiret', '46': 'Lot',
    '47': 'Lot-et-Garonne', '48': 'Lozère', '49': 'Maine-et-Loire', '50': 'Manche', '51': 'Marne',
    '52': 'Haute-Marne', '53': 'Mayenne', '54': 'Meurthe-et-Moselle', '55': 'Meuse', '56': 'Morbihan',
    '57': 'Moselle', '58': 'Nièvre', '59': 'Nord', '60': 'Oise', '61': 'Orne',
    '62': 'Pas-de-Calais', '63': 'Puy-de-Dôme', '64': 'Pyrénées-Atlantiques', '65': 'Hautes-Pyrénées',
    '66': 'Pyrénées-Orientales', '67': 'Bas-Rhin', '68': 'Haut-Rhin', '69': 'Rhône', '70': 'Haute-Saône',
    '71': 'Saône-et-Loire', '72': 'Sarthe', '73': 'Savoie', '74': 'Haute-Savoie', '75': 'Paris',
    '76': 'Seine-Maritime', '77': 'Seine-et-Marne', '78': 'Yvelines', '79': 'Deux-Sèvres', '80': 'Somme',
    '81': 'Tarn', '82': 'Tarn-et-Garonne', '83': 'Var', '84': 'Vaucluse', '85': 'Vendée', '86': 'Vienne',
    '87': 'Haute-Vienne', '88': 'Vosges', '89': 'Yonne', '90': 'Territoire de Belfort',
    '91': 'Essonne', '92': 'Hauts-de-Seine', '93': 'Seine-Saint-Denis', '94': 'Val-de-Marne',
    '95': 'Val-d\'Oise', '971': 'Guadeloupe', '972': 'Martinique', '973': 'Guyane',
    '974': 'La Réunion', '976': 'Mayotte', 'FR_UNKNOWN': 'France (Unspecified)'
};