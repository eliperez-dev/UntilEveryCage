// @ts-nocheck
/**
 * =============================================================================
 * ICON MANAGEMENT MODULE
 * =============================================================================
 * Handles all icon-related functionality including:
 * - Icon creation and scaling
 * - Facility type mapping and categorization
 * - Dynamic icon updates and caching
 * - Pin scale management
 * 
 * Note: This module relies on Leaflet (L) being available globally
 */

import { BASE_ICON_SPECS, PIN_SCALES } from './constants.js';

// =============================================================================
// ICON SCALING AND CREATION
// =============================================================================

/**
 * Current scale index for pin sizing
 * @type {number}
 */
let currentPinScaleIndex = PIN_SCALES.indexOf(1) !== -1 ? PIN_SCALES.indexOf(1) : PIN_SCALES.length - 1;

/**
 * Current custom scale value (overrides PIN_SCALES when set)
 * @type {number|null}
 */
let currentCustomScale = null;

/**
 * Rounds a number to at least 1
 * @param {number} n - Number to round
 * @returns {number} Rounded number, minimum 1
 */
const round = (n) => Math.max(1, Math.round(n));

/**
 * Creates a scaled Leaflet icon from a specification object
 * @param {Object} spec - Icon specification with iconSize, shadowSize, iconAnchor, popupAnchor properties
 * @param {number} scale - Scale factor to apply to the icon
 * @returns {L.Icon} Leaflet icon instance
 */
export function createScaledIcon(spec, scale) {
    const sz = spec.iconSize;
    const sh = spec.shadowSize;
    const ia = spec.iconAnchor;
    const pa = spec.popupAnchor;
    const s = scale;
    // @ts-ignore
    return L.icon({
        iconUrl: spec.iconUrl,
        shadowUrl: spec.shadowUrl,
        iconSize: [round(sz[0] * s), round(sz[1] * s)],
        shadowSize: [round(sh[0] * s), round(sh[1] * s)],
        iconAnchor: [round(ia[0] * s), round(ia[1] * s)],
        popupAnchor: [round(pa[0] * s), round(pa[1] * s)]
    });
}

/**
 * Gets the current scale factor for pins
 * @returns {number} Current scale factor
 */
export function getCurrentScale() { 
    return currentCustomScale !== null ? currentCustomScale : PIN_SCALES[currentPinScaleIndex]; 
}

/**
 * Gets the current scale index
 * @returns {number} Current scale index
 */
export function getCurrentScaleIndex() {
    return currentPinScaleIndex;
}

/**
 * Sets the current scale index
 * @param {number} index - New scale index
 */
export function setCurrentScaleIndex(index) {
    if (index >= 0 && index < PIN_SCALES.length) {
        currentPinScaleIndex = index;
        currentCustomScale = null;
    }
}

/**
 * Sets a custom scale value (0.5 to 2.0)
 * @param {number} scale - New scale value
 */
export function setCustomScale(scale) {
    if (scale >= 0.5 && scale <= 2.0) {
        currentCustomScale = scale;
    }
}

/**
 * Cycles to the next pin scale
 * @returns {number} New scale factor
 */
export function cycleToNextScale() {
    currentPinScaleIndex = (currentPinScaleIndex + 1) % PIN_SCALES.length;
    return getCurrentScale();
}

// =============================================================================
// ICON INSTANCES AND MANAGEMENT
// =============================================================================

/**
 * Live icon instances used when plotting markers
 * These are updated when the scale changes
 */
let slaughterhouseIcon = createScaledIcon(BASE_ICON_SPECS.slaughter, getCurrentScale());
let processingIcon = createScaledIcon(BASE_ICON_SPECS.processing, getCurrentScale());
let labIcon = createScaledIcon(BASE_ICON_SPECS.lab, getCurrentScale());
let breederIcon = createScaledIcon(BASE_ICON_SPECS.breeder, getCurrentScale());
let dealerIcon = createScaledIcon(BASE_ICON_SPECS.dealer, getCurrentScale());
let exhibitorIcon = createScaledIcon(BASE_ICON_SPECS.exhibitor, getCurrentScale());

/**
 * Refreshes all global icon instances with the current scale
 */
export function refreshGlobalIcons() {
    const s = getCurrentScale();
    slaughterhouseIcon = createScaledIcon(BASE_ICON_SPECS.slaughter, s);
    processingIcon = createScaledIcon(BASE_ICON_SPECS.processing, s);
    labIcon = createScaledIcon(BASE_ICON_SPECS.lab, s);
    breederIcon = createScaledIcon(BASE_ICON_SPECS.breeder, s);
    dealerIcon = createScaledIcon(BASE_ICON_SPECS.dealer, s);
    exhibitorIcon = createScaledIcon(BASE_ICON_SPECS.exhibitor, s);
}

/**
 * Gets the appropriate icon for a facility type
 * @param {string} type - Facility type ('slaughter', 'processing', 'lab', 'breeder', 'dealer', 'exhibitor')
 * @returns {L.Icon} Leaflet icon instance
 */
export function iconForType(type) {
    switch (type) {
        case 'slaughter': return slaughterhouseIcon;
        case 'processing': return processingIcon;
        case 'lab': return labIcon;
        case 'breeder': return breederIcon;
        case 'dealer': return dealerIcon;
        case 'exhibitor': return exhibitorIcon;
        default: return processingIcon;
    }
}

// =============================================================================
// FACILITY TYPE MAPPING
// =============================================================================

/**
 * Maps facility type strings from the backend to icon types and display labels
 * @param {string} facilityTypeString - Raw facility type string from backend
 * @param {string} establishmentName - Name of the establishment (optional, for additional context)
 * @returns {Object} Object with iconType, displayLabel, and category properties
 */
// @ts-ignore
export function mapFacilityType(facilityTypeString, establishmentName) {
    if (!facilityTypeString) {
        return { iconType: 'processing', displayLabel: 'Processing Facility', category: 'processing' };
    }
    
    const type = facilityTypeString.toLowerCase();
    
    // Check for UK specific facility types (more specific classifications)
    // Dairy farms
    // @ts-ignore
    if (type.includes('dairy farm')) {
        return { iconType: 'breeder', displayLabel: 'Dairy Farm', category: 'breeder' };
    }
    
    // Intensive farms
    // @ts-ignore
    if (type.includes('intensive pig farm')) {
        return { iconType: 'breeder', displayLabel: 'Intensive Pig Farm', category: 'breeder' };
    }
    
    // @ts-ignore
    if (type.includes('intensive poultry farm')) {
        return { iconType: 'breeder', displayLabel: 'Intensive Poultry Farm', category: 'breeder' };
    }
    
    // @ts-ignore
    if (type.includes('intensive sow pig farm')) {
        return { iconType: 'breeder', displayLabel: 'Intensive Sow Pig Farm', category: 'breeder' };
    }
    
    // @ts-ignore
    if (type.includes('finishing unit')) {
        return { iconType: 'breeder', displayLabel: 'Finishing Unit', category: 'breeder' };
    }
    
    // Mixed farms (UK specific) - handle the new format
    // @ts-ignore
    if (type.includes('mixed farm')) {
        // Extract the farm types from the parentheses for a cleaner display
        const match = type.match(/mixed farm \(([^)]+)\)/i);
        if (match) {
            return { iconType: 'breeder', displayLabel: `Mixed Farm (${match[1]})`, category: 'breeder' };
        }
        return { iconType: 'breeder', displayLabel: 'Mixed Farm', category: 'breeder' };
    }
    
    // Specific slaughterhouse types (UK)
    // @ts-ignore
    if (type.includes('cattle slaughterhouse')) {
        return { iconType: 'slaughter', displayLabel: 'Cattle Slaughterhouse', category: 'slaughter' };
    }
    
    // @ts-ignore
    if (type.includes('pig slaughterhouse')) {
        return { iconType: 'slaughter', displayLabel: 'Pig Slaughterhouse', category: 'slaughter' };
    }
    
    // @ts-ignore
    if (type.includes('poultry slaughterhouse')) {
        return { iconType: 'slaughter', displayLabel: 'Poultry Slaughterhouse', category: 'slaughter' };
    }
    
    // @ts-ignore
    if (type.includes('sheep & lamb slaughterhouse')) {
        return { iconType: 'slaughter', displayLabel: 'Sheep & Lamb Slaughterhouse', category: 'slaughter' };
    }
    
    // @ts-ignore
    if (type.includes('goat slaughterhouse')) {
        return { iconType: 'slaughter', displayLabel: 'Goat Slaughterhouse', category: 'slaughter' };
    }
    
    // @ts-ignore
    if (type.includes('horse slaughterhouse')) {
        return { iconType: 'slaughter', displayLabel: 'Horse Slaughterhouse', category: 'slaughter' };
    }
    
    // @ts-ignore
    if (type.includes('other mammal slaughterhouse')) {
        return { iconType: 'slaughter', displayLabel: 'Other Mammal Slaughterhouse', category: 'slaughter' };
    }
    
    // @ts-ignore
    if (type.includes('large bird slaughterhouse')) {
        return { iconType: 'slaughter', displayLabel: 'Large Bird Slaughterhouse', category: 'slaughter' };
    }
    
    // @ts-ignore
    if (type.includes('wild bird slaughterhouse')) {
        return { iconType: 'slaughter', displayLabel: 'Wild Bird Slaughterhouse', category: 'slaughter' };
    }
    
    // @ts-ignore
    if (type.includes('wild rabbit slaughterhouse')) {
        return { iconType: 'slaughter', displayLabel: 'Wild Rabbit Slaughterhouse', category: 'slaughter' };
    }
    
    // Mixed slaughterhouses (UK specific) - handle the new format
    // @ts-ignore
    if (type.includes('mixed slaughterhouse')) {
        // Extract the animal types from the parentheses for a cleaner display
        const match = type.match(/mixed slaughterhouse \(([^)]+)\)/i);
        if (match) {
            return { iconType: 'slaughter', displayLabel: `Mixed Slaughterhouse (${match[1]})`, category: 'slaughter' };
        }
        return { iconType: 'slaughter', displayLabel: 'Mixed Slaughterhouse', category: 'slaughter' };
    }
    
    // Check for general slaughter facilities (broader check)
    // @ts-ignore
    if (type.includes('meat slaughter') || type.includes('slaughter')) {
        return { iconType: 'slaughter', displayLabel: 'Slaughterhouse', category: 'slaughter' };
    }
    
    // Check for specific Spanish facility types
    // @ts-ignore
    if (type.includes('pig breeding farm')) {
        return { iconType: 'breeder', displayLabel: 'Pig Breeding Farm', category: 'breeder' };
    }
    
    // @ts-ignore
    if (type.includes('pig farm')) {
        return { iconType: 'breeder', displayLabel: 'Pig Farm', category: 'breeder' };
    }
    
    // @ts-ignore
    if (type.includes('poultry farm')) {
        return { iconType: 'breeder', displayLabel: 'Poultry Farm', category: 'breeder' };
    }
    
    // @ts-ignore
    if (type.includes('aquaculture')) {
        return { iconType: 'breeder', displayLabel: 'Aquaculture Facility', category: 'breeder' };
    }
    
    // Generic farm type detection for any remaining farm types
    // @ts-ignore
    if (type.includes('farm') && !type.includes('slaughter')) {
        // Extract specific animal type if mentioned
        const animalTypes = ['dairy', 'pig', 'poultry', 'cattle', 'beef', 'sheep', 'goat', 'chicken', 'duck', 'turkey', 'lamb', 'horse', 'deer', 'rabbit', 'pheasant', 'quail', 'ostrich', 'emu', 'bison', 'buffalo', 'elk', 'goose'];
        
        for (const animal of animalTypes) {
            // @ts-ignore
            if (type.includes(animal)) {
                const displayName = animal.charAt(0).toUpperCase() + animal.slice(1);
                return { iconType: 'breeder', displayLabel: `${displayName} Farm`, category: 'breeder' };
            }
        }
        
        // Check for intensive farms without specific animal type
        // @ts-ignore
        if (type.includes('intensive')) {
            return { iconType: 'breeder', displayLabel: 'Intensive Farm', category: 'breeder' };
        }
        
        // If no specific animal type found, use "Farm" 
        return { iconType: 'breeder', displayLabel: 'Farm', category: 'breeder' };
    }
    
    // Check for breeding/production facilities
    // @ts-ignore
    if (type.includes('animal production')) {
        // @ts-ignore
        if (type.includes('hunting') || type.includes('game')) {
            return { iconType: 'breeder', displayLabel: 'Game/Hunting Facility', category: 'breeder' };
        } else {
            return { iconType: 'breeder', displayLabel: 'Animal Farm', category: 'breeder' };
        }
    }
    
    // Check for exhibition facilities
    // @ts-ignore
    if (type.includes('exhibition')) {
        return { iconType: 'exhibitor', displayLabel: 'Exhibition Facility', category: 'exhibitor' };
    }
    
    // Check for aquatic facilities
    // @ts-ignore
    if (type.includes('aquatic')) {
        // @ts-ignore
        if (type.includes('processing')) {
            return { iconType: 'slaughter', displayLabel: 'Aquatic Processing Facility', category: 'slaughter' };
        } else {
            return { iconType: 'breeder', displayLabel: 'Aquatic Production Facility', category: 'breeder' };
        }
    }
    
    // Default to processing
    return { iconType: 'processing', displayLabel: 'Processing Facility', category: 'processing' };
}

// =============================================================================
// MARKER UPDATE UTILITIES
// =============================================================================

/**
 * Updates all marker icons to use the current scale
 * Requires access to map layers, so this function will need to be called from app.js
 * @param {Array} layers - Array of Leaflet layer groups to update
 */
export function updateAllMarkerIcons(layers) {
    // Recreate live icons for the new scale
    refreshGlobalIcons();
    
    const updateMarker = (m) => {
        if (m && m.setIcon && m._iconType) {
            m.setIcon(iconForType(m._iconType));
        }
    };
    
    // Update markers across all layers
    layers.forEach(layer => {
        if (!layer) return;
        layer.eachLayer(l => {
            // l may be a marker or a group; try to update directly
            if (l && l.eachLayer) {
                l.eachLayer(inner => updateMarker(inner));
            } else {
                updateMarker(l);
            }
        });
    });
}