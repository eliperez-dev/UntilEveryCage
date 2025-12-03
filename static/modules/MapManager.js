/**
 * Map Manager Module
 * 
 * Handles map initialization, layer management, and marker plotting.
 */

import { MAP_CONFIG } from './constants.js';
import { 
    iconForType, 
    mapFacilityType, 
    updateAllMarkerIcons 
} from './iconUtils.js';
import { 
    buildLocationPopup, 
    buildLabPopup, 
    buildInspectionReportPopup 
} from './popupBuilder.js';
import { initializeCustomControls } from './leafletControls.js';

export class MapManager {
    constructor() {
        this.map = null;
        this.unifiedClusterLayer = null;
        this.slaughterhouseFeatureLayer = null;
        this.processingFeatureLayer = null;
        this.labFeatureLayer = null;
        this.inspectionReportFeatureLayer = null;
        
        this.streetMap = null;
        this.satelliteMap = null;
        this.defaultViewLayer = null;
        
        this.isDefaultViewActive = true;
        this.currentActiveLayer = null;
        this.isAutoSwitching = false;
        this.SATELLITE_ZOOM_THRESHOLD = 13;
    }

    init(mapId) {
        // Define boundaries
        const southWest = L.latLng(MAP_CONFIG.southWest[0], MAP_CONFIG.southWest[1]);
        const northEast = L.latLng(MAP_CONFIG.northEast[0], MAP_CONFIG.northEast[1]);
        // const worldBounds = L.latLngBounds(southWest, northEast); // Unused in original code

        // Initialize map
        this.map = L.map(mapId, {
            zoomControl: false,
            maxZoom: 19
        }).setView(MAP_CONFIG.center, MAP_CONFIG.zoom).setMinZoom(MAP_CONFIG.minZoom).setZoom(MAP_CONFIG.zoom);

        this.setupLayers();
        this.setupControls();
        this.setupEvents();
        
        return this.map;
    }

    setupLayers() {
        // Base layers
        this.streetMap = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '© OpenStreetMap contributors'
        });

        const satelliteBase = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            maxZoom: 19,
            attribution: 'Tiles &copy; Esri'
        });

        const transportationOverlay = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}', {
            maxZoom: 19,
            attribution: ''
        });

        this.satelliteMap = L.layerGroup([satelliteBase, transportationOverlay]);
        this.defaultViewLayer = L.layerGroup();

        // Feature layers
        this.unifiedClusterLayer = L.markerClusterGroup({ 
            chunkedLoading: true, 
            maxClusterRadius: MAP_CONFIG.maxClusterRadius, 
            disableClusteringAtZoom: MAP_CONFIG.disableClusteringAtZoom,
            spiderfyOnMaxZoom: false,
            showCoverageOnHover: false
        });

        this.slaughterhouseFeatureLayer = L.layerGroup();
        this.processingFeatureLayer = L.layerGroup();
        this.labFeatureLayer = L.layerGroup();
        this.inspectionReportFeatureLayer = L.layerGroup();

        // Initialize with Default View
        this.defaultViewLayer.addTo(this.map);
        this.applyZoomBasedLayer();
    }

    setupControls() {
        // Zoom control
        L.control.zoom({ position: 'bottomright' }).addTo(this.map);
        
        // Custom controls
        initializeCustomControls(this.map);
        
        // Note: initializeDrawer is imported but might need to be called from app.js if it depends on other things
        // For now, we'll assume it's fine here or handled externally if needed.
        // In original app.js, it was called after custom controls.
    }

    setupEvents() {
        this.map.on('moveend', () => this.correctMapView());
        this.map.on('dragend', () => this.correctMapView());
        this.map.on('zoomend', () => this.applyZoomBasedLayer());
        
        this.map.on('baselayerchange', (e) => {
            if (this.isAutoSwitching) return;
            
            if (e.name === 'Default View') {
                this.isDefaultViewActive = true;
                this.map.removeLayer(this.defaultViewLayer);
                this.applyZoomBasedLayer();
            } else if (e.name === 'Street View' || e.name === 'Satellite View') {
                this.isDefaultViewActive = false;
                this.currentActiveLayer = e.layer;
            }
        });
    }

    correctCoordinates(lat, lng) {
        while (lng > 180) lng -= 360;
        while (lng < -180) lng += 360;
        lat = Math.max(-85, Math.min(85, lat));
        return [lat, lng];
    }

    correctMapView() {
        const center = this.map.getCenter();
        const [correctedLat, correctedLng] = this.correctCoordinates(center.lat, center.lng);
        
        if (Math.abs(center.lat - correctedLat) > 0.001 || Math.abs(center.lng - correctedLng) > 0.001) {
            this.map.setView([correctedLat, correctedLng], this.map.getZoom(), { animate: false });
        }
    }

    applyZoomBasedLayer() {
        if (!this.isDefaultViewActive) return;
        
        const currentZoom = this.map.getZoom();
        let targetLayer;
        
        if (currentZoom > this.SATELLITE_ZOOM_THRESHOLD) {
            targetLayer = this.satelliteMap;
        } else {
            targetLayer = this.streetMap;
        }
        
        if (this.currentActiveLayer !== targetLayer) {
            this.isAutoSwitching = true;
            this.map.removeLayer(this.streetMap);
            this.map.removeLayer(this.satelliteMap);
            this.map.addLayer(targetLayer);
            this.currentActiveLayer = targetLayer;
            this.isAutoSwitching = false;
        }
    }

    clearLayers() {
        this.unifiedClusterLayer.clearLayers();
        [this.slaughterhouseFeatureLayer, this.processingFeatureLayer, this.labFeatureLayer, this.inspectionReportFeatureLayer]
            .forEach(layer => layer.clearLayers());
        
        this.map.removeLayer(this.unifiedClusterLayer);
        [this.slaughterhouseFeatureLayer, this.processingFeatureLayer, this.labFeatureLayer, this.inspectionReportFeatureLayer]
            .forEach(layer => this.map.removeLayer(layer));
    }

    plotMarker(data, type) {
        let lat, lng, iconType, popupContent;

        if (type === 'lab') {
            lat = data.latitude;
            lng = data.longitude;
            iconType = 'lab';
            popupContent = () => buildLabPopup(data);
        } else if (type === 'inspection') {
            lat = parseFloat(data['Geocodio Latitude']);
            lng = parseFloat(data['Geocodio Longitude']);
            
            const licenseType = data['License Type'];
            if (licenseType === 'Class A - Breeder') {
                iconType = 'breeder';
            } else if (licenseType === 'Class B - Dealer') {
                iconType = 'dealer';
            } else if (licenseType === 'Class C - Exhibitor') {
                iconType = 'exhibitor';
            } else {
                iconType = 'breeder';
            }
            
            popupContent = () => buildInspectionReportPopup(data);
        } else if (type === 'usda-facility') {
            lat = data.latitude;
            lng = data.longitude;
            const facilityMapping = mapFacilityType(data.type, data.establishment_name);
            iconType = facilityMapping.iconType;
            popupContent = () => buildLocationPopup(data, facilityMapping.displayLabel);
        } else {
            lat = data.latitude;
            lng = data.longitude;
            const isSlaughterhouse = type === true;
            iconType = isSlaughterhouse ? 'slaughter' : 'processing';
            popupContent = () => buildLocationPopup(data, isSlaughterhouse);
        }

        if (lat && lng) {
            const marker = L.marker([lat, lng], { icon: iconForType(iconType) });
            marker._iconType = iconType;
            marker.bindPopup(popupContent);
            return marker;
        }
        return null;
    }

    updateMarkers(data, options) {
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
            showDealers, // Used for inspections filtering logic inside plotMarker/addMarker? No, filteredInspections is already filtered.
            useClustering,
            isAllStatesView,
            shouldCenterOnCountry,
            shouldUpdateView,
            selectedCountry
        } = options;

        this.clearLayers();

        const markerBounds = [];
        const addMarkerToLayer = (marker, layer) => {
            if (marker) {
                layer.addLayer(marker);
                if (!isAllStatesView || shouldCenterOnCountry) markerBounds.push(marker.getLatLng());
            }
        };

        const slaughterLayer = useClustering ? this.unifiedClusterLayer : this.slaughterhouseFeatureLayer;
        const processingLayer = useClustering ? this.unifiedClusterLayer : this.processingFeatureLayer;
        const labLayer = useClustering ? this.unifiedClusterLayer : this.labFeatureLayer;
        const inspectionLayer = useClustering ? this.unifiedClusterLayer : this.inspectionReportFeatureLayer;

        if (showSlaughter) {
            slaughterhouses.forEach(loc => addMarkerToLayer(this.plotMarker(loc, 'usda-facility'), slaughterLayer));
        }
        if (showProcessing) {
            processingPlants.forEach(loc => addMarkerToLayer(this.plotMarker(loc, 'usda-facility'), processingLayer));
        }
        if (showBreeders) {
            breedingFacilities.forEach(loc => addMarkerToLayer(this.plotMarker(loc, 'usda-facility'), slaughterLayer));
        }
        if (showExhibitors) {
            exhibitionFacilities.forEach(loc => addMarkerToLayer(this.plotMarker(loc, 'usda-facility'), slaughterLayer));
        }
        if (showLabs) {
            filteredLabs.forEach(lab => addMarkerToLayer(this.plotMarker(lab, 'lab'), labLayer));
        }
        
        // filteredInspections are already filtered by license type in FilterManager
        filteredInspections.forEach(report => addMarkerToLayer(this.plotMarker(report, 'inspection'), inspectionLayer));

        if (useClustering) {
            this.map.addLayer(this.unifiedClusterLayer);
        } else {
            if (showSlaughter) this.map.addLayer(this.slaughterhouseFeatureLayer);
            if (showProcessing) this.map.addLayer(this.processingFeatureLayer);
            if (showLabs) this.map.addLayer(this.labFeatureLayer);
            if (filteredInspections.length > 0) this.map.addLayer(this.inspectionReportFeatureLayer);
        }

        if (shouldUpdateView) {
            if (!isAllStatesView && markerBounds.length > 0) {
                this.map.fitBounds(L.latLngBounds(markerBounds).pad(0.1));
            } else if (isAllStatesView) {
                if (shouldCenterOnCountry && selectedCountry !== 'all' && markerBounds.length > 0) {
                    this.map.fitBounds(L.latLngBounds(markerBounds).pad(0.1));
                } else {
                    this.map.setView([31.42841, -49.57343], 2).setZoom(2);
                }
            }
        }
    }

    updateIcons() {
        updateAllMarkerIcons([
            this.unifiedClusterLayer, 
            this.slaughterhouseFeatureLayer, 
            this.processingFeatureLayer, 
            this.labFeatureLayer, 
            this.inspectionReportFeatureLayer
        ]);
    }

    highlightLocation(lat, lng) {
        this.map.setView([lat, lng], 16);
        
        setTimeout(() => {
            const matchingMarkers = [];
            const checkLayer = (layer) => {
                if (layer.getLatLng && 
                    Math.abs(layer.getLatLng().lat - lat) < 0.001 && 
                    Math.abs(layer.getLatLng().lng - lng) < 0.001) {
                    matchingMarkers.push(layer);
                }
            };

            this.unifiedClusterLayer.eachLayer(checkLayer);
            
            if (matchingMarkers.length === 0) {
                [this.slaughterhouseFeatureLayer, this.processingFeatureLayer, this.labFeatureLayer, this.inspectionReportFeatureLayer]
                    .forEach(layer => layer.eachLayer(checkLayer));
            }
            
            if (matchingMarkers.length > 0) {
                matchingMarkers[0].openPopup();
            }
        }, 100);
    }
}

export const mapManager = new MapManager();
