/**
 * Search Manager Module
 * 
 * Handles search functionality and results display.
 */

import { initializeDOMElements } from './constants.js';

export class SearchManager {
    constructor() {
        this.elements = initializeDOMElements();
        this.setupGlobalClickListener();
    }

    setupGlobalClickListener() {
        document.addEventListener('click', (e) => {
            const resultsDropdown = document.getElementById('search-results-dropdown');
            const searchInput = document.getElementById('name-search-input');
            
            if (resultsDropdown && searchInput && !resultsDropdown.contains(e.target) && e.target !== searchInput) {
                resultsDropdown.classList.remove('active');
            }
        });
    }

    updateSearchResults(searchTerm, allLocations, allLabLocations, mapManager) {
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
                
                resultsDropdown.classList.remove('active');
                this.elements.nameSearchInput.value = facilityName;
                
                mapManager.highlightLocation(lat, lng);
            });
        });
    }
}

export const searchManager = new SearchManager();
