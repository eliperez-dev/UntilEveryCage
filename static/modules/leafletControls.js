// @ts-nocheck
/**
 * =============================================================================
 * LEAFLET CONTROLS MODULE
 * =============================================================================
 * Custom Leaflet controls for the Until Every Cage is Empty map application.
 * Includes fullscreen, location finder, pin scaling, and control positioning utilities.
 * 
 * Dependencies: Leaflet.js (L global), iconUtils for scale management
 */

import { getCurrentScale, cycleToNextScale } from './iconUtils.js';

// =============================================================================
// CUSTOM FULLSCREEN CONTROL
// =============================================================================

/**
 * Custom Fullscreen Control for Leaflet.
 * Provides fullscreen toggle functionality with fallback to pseudo-fullscreen.
 */
L.Control.CustomFullscreen = L.Control.extend({
    options: {
        position: 'bottomright',
        enterText: 'Fullscreen',
        exitText: 'Exit'
    },
    
    onAdd: function (map) {
        const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control leaflet-control-custom-fullscreen');
        this.link = L.DomUtil.create('a', '', container);
        this.link.href = '#';
        this.link.innerHTML = this.options.enterText;
        this.link.setAttribute('aria-label', this.options.enterText);
        this._map = map;
        
        // Set up fullscreen change event listeners for different browsers
        L.DomEvent.on(document, 'fullscreenchange', this._onFullscreenChange, this);
        L.DomEvent.on(document, 'webkitfullscreenchange', this._onFullscreenChange, this);
        L.DomEvent.on(document, 'mozfullscreenchange', this._onFullscreenChange, this);
        L.DomEvent.on(document, 'msfullscreenchange', this._onFullscreenChange, this);
        
        // Set up click handlers
        L.DomEvent.on(container, 'click', L.DomEvent.stop);
        L.DomEvent.on(container, 'click', this._toggleFullscreen, this);
        
        return container;
    },
    
    onRemove: function (map) {
        // Clean up event listeners
        L.DomEvent.off(document, 'fullscreenchange', this._onFullscreenChange, this);
        L.DomEvent.off(document, 'webkitfullscreenchange', this._onFullscreenChange, this);
        L.DomEvent.off(document, 'mozfullscreenchange', this._onFullscreenChange, this);
        L.DomEvent.off(document, 'msfullscreenchange', this._onFullscreenChange, this);
    },
    
    _toggleFullscreen: function () {
        const container = this._map.getContainer();
        
        // Check if we're in pseudo-fullscreen mode
        if (L.DomUtil.hasClass(container, 'map-pseudo-fullscreen')) {
            L.DomUtil.removeClass(container, 'map-pseudo-fullscreen');
            this.link.innerHTML = this.options.enterText;
            this._map.invalidateSize();
            return;
        }
        
        // Check if we're already in native fullscreen
        const fullscreenElement = document.fullscreenElement || 
                                 document.webkitFullscreenElement || 
                                 document.mozFullScreenElement || 
                                 document.msFullscreenElement;
        
        if (fullscreenElement) {
            // Exit fullscreen
            const exitMethod = document.exitFullscreen || 
                              document.webkitExitFullscreen || 
                              document.mozCancelFullScreen || 
                              document.msExitFullscreen;
            if (exitMethod) exitMethod.call(document);
        } else {
            // Enter fullscreen
            const requestMethod = container.requestFullscreen || 
                                 container.webkitRequestFullscreen || 
                                 container.mozRequestFullScreen || 
                                 container.msRequestFullscreen;
            if (requestMethod) {
                requestMethod.call(container);
            } else {
                // Fallback to pseudo-fullscreen
                L.DomUtil.addClass(container, 'map-pseudo-fullscreen');
                this.link.innerHTML = this.options.exitText;
                this._map.invalidateSize();
            }
        }
    },
    
    _onFullscreenChange: function () {
        const fullscreenElement = document.fullscreenElement || 
                                 document.webkitFullscreenElement || 
                                 document.mozFullScreenElement || 
                                 document.msFullscreenElement;
        this.link.innerHTML = fullscreenElement ? this.options.exitText : this.options.enterText;
    }
});

// =============================================================================
// FIND ME CONTROL
// =============================================================================

/**
 * Custom Find Me Control for Leaflet.
 * Provides geolocation functionality to center map on user's location.
 */
L.Control.FindMe = L.Control.extend({
    options: {
        position: 'bottomright'
    },
    
    onAdd: function(map) {
        const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control leaflet-control-find-me');
        const link = L.DomUtil.create('a', '', container);
        link.href = '#';
        link.title = 'Find my location';
        link.setAttribute('aria-label', 'Find my location');

        L.DomEvent.on(link, 'click', L.DomEvent.stop)
                  .on(link, 'click', () => {
                      map.locate({ setView: true, maxZoom: 12 });
                  });
        
        return container;
    }
});

// =============================================================================
// PIN SCALE CONTROL
// =============================================================================

/**
 * Control to cycle through different pin scales.
 * Integrates with iconUtils module for scale management.
 */
L.Control.PinScale = L.Control.extend({
    options: { 
        position: 'bottomright' 
    },
    
    onAdd: function(map) {
        const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control leaflet-control-pin-scale');
        const link = L.DomUtil.create('a', '', container);
        link.href = '#';
        link.title = 'Toggle pin size';
        link.setAttribute('aria-label', 'Toggle pin size');
        link.style.minWidth = '44px';
        link.style.textAlign = 'center';
        
        const setLabel = () => { 
            link.textContent = `${getCurrentScale()}x`; 
        };
        setLabel();
        
        L.DomEvent.on(link, 'click', L.DomEvent.stop)
                 .on(link, 'click', () => {
                     cycleToNextScale();
                     setLabel();
                     // Function will be defined later when layers are available
                     if (typeof window.updateMapMarkerIcons === 'function') {
                         window.updateMapMarkerIcons();
                     }
                 });
        
        return container;
    }
});

// =============================================================================
// CONTROL POSITIONING UTILITIES
// =============================================================================

/**
 * Moves all map controls from top positions to bottom positions
 * to avoid overlap with the filter panel.
 */
export function moveControlsToBottom() {
    const leftControls = document.querySelector('.leaflet-top.leaflet-left');
    const rightControls = document.querySelector('.leaflet-top.leaflet-right');
    
    if (leftControls) {
        leftControls.classList.remove('leaflet-top');
        leftControls.classList.add('leaflet-bottom');
    }
    if (rightControls) {
        rightControls.classList.remove('leaflet-top');
        rightControls.classList.add('leaflet-bottom');
    }
}

// =============================================================================
// CONTROL INITIALIZATION FUNCTIONS
// =============================================================================

/**
 * Initializes all custom controls on the provided map instance
 * @param {L.Map} map - The Leaflet map instance
 */
export function initializeCustomControls(map) {
    // Add custom controls
    map.addControl(new L.Control.CustomFullscreen());
    map.addControl(new L.Control.FindMe());
    map.addControl(new L.Control.PinScale());
    
    // Set up location events for Find Me control
    map.on('locationfound', e => {
        L.marker(e.latlng).addTo(map)
         .bindPopup("You are here.").openPopup();
    });
    
    map.on('locationerror', e => {
        alert(e.message);
    });
    
    // Move controls to bottom after a short delay to ensure they're rendered
    setTimeout(moveControlsToBottom, 100);
}

/**
 * Factory function to create a custom fullscreen control
 * @returns {L.Control.CustomFullscreen} New fullscreen control instance
 */
export function createFullscreenControl() {
    return new L.Control.CustomFullscreen();
}

/**
 * Factory function to create a find me control
 * @returns {L.Control.FindMe} New find me control instance
 */
export function createFindMeControl() {
    return new L.Control.FindMe();
}

/**
 * Factory function to create a pin scale control
 * @returns {L.Control.PinScale} New pin scale control instance
 */
export function createPinScaleControl() {
    return new L.Control.PinScale();
}