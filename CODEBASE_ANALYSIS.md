# Until Every Cage is Empty - Codebase Analysis

## Executive Summary

This document provides a comprehensive technical overview of the "Until Every Cage is Empty" project. The application is a full-stack web platform for visualizing facilities involved in animal exploitation across the United States and internationally. It uses a decoupled architecture with a Rust backend API and a vanilla JavaScript frontend deployed separately.

---

## 1. Project Architecture Overview

### 1.1 Architecture Pattern
- **Pattern**: Decoupled Frontend/Backend (SPA + RESTful API)
- **Backend**: Rust (Axum framework) deployed on Shuttle
- **Frontend**: Vanilla HTML/CSS/JavaScript deployed on Netlify
- **Data**: CSV-based, embedded at compile-time via `include_dir!` macro
- **Hosting**: Shuttle (backend) + Netlify (frontend)

### 1.2 Deployment & Runtime
- **Backend**: Shuttle.rs (Rust-focused deployment platform)
- **Frontend**: Netlify (static site hosting)
- **API Base URL (Prod)**: `https://untileverycage-ikbq.shuttle.app`
- **Data Storage**: Static CSV files in `static_data/{country_code}/` directories
- **Data Embedding**: CSV files are compiled into the binary via `include_dir!` crate

### 1.3 Multi-Country Support
The application supports multiple countries with separate data sources:
- `us/` - United States (USDA, APHIS)
- `uk/` - United Kingdom
- `de/` - Germany
- `es/` - Spain
- `fr/` - France
- `dk/` - Denmark

---

## 2. Backend Architecture (Rust)

### 2.1 Project Structure
```
src/
├── main.rs           # Entry point, route definitions
├── lib.rs            # Core API handlers & CSV parsing logic
└── location.rs       # Data models & animal categorization logic
```

### 2.2 Dependencies
```toml
axum = "0.8.4"                    # Web framework
tokio = "1.37.0"                  # Async runtime
tower-http = "0.6.6"              # HTTP middleware (CORS, compression)
serde = "1.0"                     # Serialization
csv = "1.3.0"                     # CSV parsing
include_dir = "0.7.4"             # Embed files at compile-time
shuttle-runtime = "0.55.0"        # Shuttle platform integration
serde-xml-rs = "0.8.1"            # XML parsing (legacy support)
```

### 2.3 API Endpoints

#### `/api/locations` (GET)
- **Parameters**: `country_code` (optional, e.g., "us", "uk", "de")
- **Response**: Array of `LocationResponse` objects
- **Logic**: 
  - Reads from `static_data/{country_code}/locations.csv`
  - Filters by country if specified; returns all countries if omitted
  - Computes aggregated animal fields (slaughtered/processed animals)
  - Returns only relevant fields (subset of full Location struct)

#### `/api/aphis-reports` (GET)
- **Parameters**: None
- **Response**: Array of `AphisReport` objects
- **Data Source**: `static_data/us/aphis_data_final.csv`
- **Purpose**: Animal testing laboratory data (APHIS certified facilities)

#### `/api/inspection-reports` (GET)
- **Parameters**: None
- **Response**: Array of `InspectionReport` objects
- **Data Source**: `static_data/us/inspection_reports.csv`
- **Purpose**: Animal dealer/breeder/exhibitor inspection data

### 2.4 Data Models

#### Location Struct (location.rs)
- **File**: `src/location.rs` (409 lines)
- **Fields**: 126 fields covering basic info, slaughter operations, processing operations, and administrative data
- **Key Fields**:
  - Basic: `establishment_id`, `establishment_name`, `address`, `city`, `state`, `zip`, `phone`, `grant_date`
  - Slaughter Categories: 46 boolean fields (beef, pork, poultry, etc.)
  - Processing Categories: 23 boolean fields (by animal type)
  - Volume Metrics: `slaughter_volume_category`, `processing_volume_category`

#### Animal Aggregation Functions
- `get_slaughtered_animals(location)` - Converts 46 slaughter fields into readable list
- `get_processed_animals(location)` - Converts 23 processing fields into readable list

#### AphisReport & InspectionReport Structs
- **APHIS**: Research facility data with animal counts and certification details
- **Inspection**: Dealer/breeder/exhibitor data with license types and coordinates

### 2.5 Key Backend Patterns

#### Data Loading
1. CSV files embedded at compile-time using `include_dir!` macro
2. No database - pure in-memory CSV parsing on request
3. Each API call reads and deserializes CSV data
4. No caching mechanism

#### Response Strategy
- Multiple response types depending on endpoint
- Computed fields added during deserialization
- Compression applied via `tower-http::CompressionLayer`
- CORS enabled with permissive policy

---

## 3. Frontend Architecture (Vanilla JavaScript)

### 3.1 Project Structure
```
static/
├── index.html              # Main map page
├── about.html              # About page
├── howtouse.html           # How-to guide
├── app.js                  # Main application (1250 lines)
├── style.css               # Global styles
├── map-filter-styles.css   # Map/filter UI styles
└── modules/
    ├── constants.js        # Configuration & DOM selectors
    ├── geoUtils.js         # Geo helpers & state mappings
    ├── iconUtils.js        # Marker icon management
    ├── leafletControls.js  # Map controls
    ├── popupBuilder.js     # Dynamic popup content generation
    └── drawerManager.js    # Slide-out filter drawer
```

### 3.2 Dependencies
- **Leaflet.js** v1.9.4 - Interactive mapping (CDN)
- **Leaflet.markercluster** v1.5.3 - Marker clustering (CDN)
- **Jest** 29.7.0 - Testing framework (dev only)
- **No runtime frameworks** (React, Vue, etc.)

### 3.3 API Integration

#### Endpoint Configuration
```javascript
API_ENDPOINTS = {
  production: {
    locations: 'https://untileverycage-ikbq.shuttle.app/api/locations',
    aphisReports: 'https://untileverycage-ikbq.shuttle.app/api/aphis-reports',
    inspectionReports: 'https://untileverycage-ikbq.shuttle.app/api/inspection-reports'
  }
}
```

#### Data Fetching Pattern
- Fetches all data on page load (3 API calls, no pagination)
- Filters applied client-side
- Data cached in memory for filtering operations

### 3.4 Map Configuration
- Center: World view (31.42841, -49.57343)
- Zoom: 2 (global view)
- Marker clustering at 50px radius
- Uncluster at zoom level 10+

### 3.5 Marker Icons
- **slaughter**: Red markers
- **processing**: Grey markers
- **lab**: Violet markers (APHIS)
- **breeder**: Yellow markers
- **dealer**: Orange markers
- **exhibitor**: Green markers

### 3.6 Popup Content Generation

#### Functions in `popupBuilder.js`
- `buildLocationPopup()` - Slaughterhouses, processing plants
- `buildLabPopup()` - APHIS research facilities
- `buildInspectionReportPopup()` - Animal dealer/breeder/exhibitor facilities

#### Popup Features
- Dynamic HTML generation based on available data
- Copyable text fields (address, ID, phone)
- Links to Google Maps directions
- Links to official source databases
- Conditional rendering (omits empty fields)

### 3.7 Filtering & Controls
- **Facility Type Filters**: 6 checkboxes (slaughterhousehouses, processing, labs, etc.)
- **Country Selector**: Dropdown with cascading state selector
- **Name Search**: Text input filter
- **Controls**: Marker cluster threshold, icon size slider, fullscreen, find-me, pin scale cycling
- **URL State**: Parameters updated for shareable links

### 3.8 JavaScript Module Architecture

#### Module Responsibilities
- **constants.js**: Configuration, icon specs, API endpoints, DOM selectors, state mappings
- **geoUtils.js**: State/country validation, location normalization, CSV export
- **iconUtils.js**: Icon creation, size management, scaling
- **leafletControls.js**: Custom Leaflet controls
- **drawerManager.js**: Filter panel open/close logic
- **popupBuilder.js**: Dynamic popup HTML generation

---

## 4. Data Structure & Content

### 4.1 Data File Sizes
```
US:
- locations.csv: 4.1 MB (7,102 rows)
- aphis_data_final.csv: 199 KB
- inspection_reports.csv: 769 KB

International:
- uk/locations.csv: 2.2 MB
- de/locations.csv: 3.8 MB
- es/locations.csv: 1.1 MB
- fr/locations.csv: 626 KB
- dk/locations.csv: 323 KB

Total: ~13.2 MB
```

### 4.2 US Locations CSV
- **Header Fields**: 126 total
- **Basic Info**: establishment_id, name, address, coordinates
- **Slaughter Operations**: 46 boolean fields (by animal type)
- **Processing Operations**: 23 boolean fields (by animal type)
- **Volume Categories**: Categorical fields (1.0-5.0 scale)

### 4.3 APHIS Data CSV
- **Facilities**: ~1,000+ research labs
- **Key Fields**: Certificate number, registration type, animal counts, coordinates
- **Animal Types Tracked**: Dogs, Cats, Guinea Pigs, Rabbits, Primates, Sheep, Pigs, etc.

### 4.4 Inspection Reports CSV
- **Facilities**: ~10,000+ breeders/dealers/exhibitors
- **License Types**: Class A (Breeder), Class B (Dealer), Class C (Exhibitor)
- **Coordinates**: Geocodio latitude/longitude (approximate)

### 4.5 Data Records Summary
- **US Locations**: ~7,100
- **APHIS Facilities**: ~1,000
- **Inspection Reports**: ~10,000
- **International Locations**: ~30,000+
- **Total**: ~48,000+ facilities

---

## 5. Code Conventions & Patterns

### 5.1 Rust Conventions
- Uses `serde` with `#[serde(rename = "...")]` for CSV headers
- Error handling: `Result<T, Box<dyn Error>>`
- Async: `tokio` runtime with `async/await`
- Module exports via `pub use`
- Default implementations with `#[derive(Default)]`

### 5.2 JavaScript Conventions
- Type annotations via `// @ts-nocheck` (no TypeScript enforcement)
- ES modules with `import/export`
- DOM selectors cached in `constants.js`
- camelCase for functions/variables
- Functional programming patterns (no classes)
- Direct `addEventListener` on cached elements

### 5.3 Build & Deployment
- **Backend**: Deployed via `cargo shuttle deploy`
- **Frontend**: Static files deployed to Netlify
- **Data Embedding**: CSV files compiled into Rust binary via `include_dir!`
- **Configuration**: `Shuttle.toml` specifies assets

### 5.4 Error Handling
- **Backend**: HTTP status codes, error messages in response body
- **Frontend**: Try-catch around fetch calls, user feedback via loading indicators

### 5.5 Code Organization
- **Separation of Concerns**: Backend (data) vs Frontend (presentation)
- **Modular JS**: Utilities split into separate modules
- **Centralized Configuration**: All in `constants.js`
- **Reusable Helpers**: Animal categorization, state mappings, etc.

---

## 6. Development Workflow

### 6.1 Local Development

**Terminal 1 - Backend:**
```bash
cargo shuttle run --port 8001
```

**Terminal 2 - Frontend:**
```bash
python3 -m http.server 8000
```

**Frontend Config**: Update `constants.js` to use local API
```javascript
locations: 'http://127.0.0.1:8001/api/locations'
```

### 6.2 Build Process
- **No build step for frontend** (vanilla JS)
- **Backend build**: Rust compilation + CSV embedding at compile-time
- **Total backend data**: 13.2 MB embedded in binary

### 6.3 Deployment
- **Backend**: Push to GitHub → Shuttle auto-deploys (assumed)
- **Frontend**: Push to GitHub → Netlify auto-deploys (assumed)
- **Data Updates**: Update CSV files, redeploy backend

### 6.4 Testing
```bash
npm test              # Run tests once
npm test:watch       # Run in watch mode
npm test:coverage    # Generate coverage
```

---

## 7. Performance Characteristics

### 7.1 Data Loading
- **Cold Start**: All data fetched on page load (3 API calls)
- **Compression**: Gzip applied by `tower-http::CompressionLayer`
- **Parsing**: Client-side JSON deserialization
- **Memory Usage**: All facilities held in JavaScript arrays

### 7.2 Rendering
- **Marker Clustering**: Leaflet.markercluster for large datasets
- **Max Cluster Radius**: 50 pixels
- **Uncluster at Zoom**: Level 10+
- **Client-Side Filtering**: No server-side optimization

### 7.3 Optimization Techniques
- Gzip compression on responses
- Marker clustering reduces visual clutter
- Dynamic icon scaling without re-rendering
- CSS minification

---

## 8. Key Features & Current Capabilities

### 8.1 Map Features
✅ Multi-layer visualization (6 facility types)
✅ Interactive markers with detailed popups
✅ Marker clustering for performance
✅ Shareable URLs (with map state)
✅ Fullscreen mode
✅ Geolocation ("find me")
✅ Icon size adjustment

### 8.2 Filtering
✅ By facility type (6 checkboxes)
✅ By country (dropdown)
✅ By state/province (cascading dropdown)
✅ By facility name (text search)
✅ Dynamic statistics display

### 8.3 Data Presentation
✅ Color-coded markers by facility type
✅ Rich popup content (address, phone, animals, volumes)
✅ Links to official databases (FSIS, APHIS)
✅ Links to Google Maps directions
✅ Copyable contact information
✅ Mobile-responsive design

---

## 9. Integration Points & Extension Hooks

### 9.1 Adding New Facilities
1. Update CSV file: `static_data/{country}/locations.csv`
2. Redeploy backend (Shuttle auto-discovers)

### 9.2 Adding New Facility Types
1. Extend `Location` struct in `location.rs`
2. Add aggregation function
3. Update `mapFacilityType()` in `app.js`
4. Add icon to `BASE_ICON_SPECS`
5. Extend `popupBuilder.js`

### 9.3 Adding New Countries
1. Create `static_data/{country_code}/locations.csv`
2. Update state mappings in `constants.js`
3. Add validators in `geoUtils.js`
4. Add country option to UI
5. Redeploy backend

---

## 10. Security & Privacy

### 10.1 Data Security
- **Public Data**: All from official government sources
- **No Secrets**: No API keys, passwords in repo
- **License**: AGPLv3 (code must be open-sourced if deployed)
- **CORS**: Wide-open (intentional for public API)

### 10.2 User Privacy
- **No Analytics**: No tracking code
- **No Cookies**: No user data stored
- **Geolocation**: Optional, user-initiated
- **No Forms**: No user input collection

### 10.3 Data Integrity
- **Read-Only**: No create/update/delete endpoints
- **Version Control**: Changes tracked in Git
- **Manual Auditing**: No automated validation

---

## 11. Known Limitations

### 11.1 Scalability
- No pagination (all data loaded at once)
- No server-side filtering
- No database (pure CSV files)
- No indexing or query optimization

### 11.2 Data Updates
- Manual CSV file updates required
- Full backend redeployment needed for data changes
- Data tracked in Git (version control, not ideal for large datasets)

### 11.3 International Data
- Approximate coordinates (many locations)
- Data quality varies by country
- No multilingual support (English only)

### 11.4 SEO & Individual Facility Pages
- Current SPA has no per-facility URLs
- No facility-specific meta tags
- Entire map is single page
- Would require new static page generation for individual facilities

---

## 12. Testing Infrastructure

### 12.1 Frontend Testing
- **Framework**: Jest 29.7.0 with jsdom
- **Location**: `static/modules/__tests__/`
- **Commands**: `npm test`, `npm test:watch`, `npm test:coverage`

### 12.2 Backend Testing
- **Status**: No test files found
- **Framework**: None configured

### 12.3 Testing Gaps
- Critical paths untested
- No integration tests
- No load/performance tests
- No E2E tests

---

## 13. Code Statistics

### 13.1 File Sizes
- `app.js`: 1,250 lines
- `location.rs`: 409 lines
- `geoUtils.js`: 279 lines
- `constants.js`: 285 lines
- `popupBuilder.js`: 188 lines
- **Total Code**: ~3,000 lines

### 13.2 Data Volume
- **Facilities**: ~48,000+ total
- **Countries**: 6 (US, UK, DE, ES, FR, DK)
- **CSV Data Size**: 13.2 MB total

### 13.3 Code Quality
- No automated tests for production code
- Rust provides compile-time safety
- JavaScript has no type checking
- Basic documentation (no JSDoc/Rust docs)
- No linting configuration (ESLint, clippy)

---

## 14. Technical Decisions & Rationale

### 14.1 Architecture Choices
- **Rust + Axum**: Performance, memory safety, excellent async support
- **Shuttle**: Simplified Rust deployment, built-in asset embedding
- **Vanilla JS**: No dependencies, direct DOM control, educational
- **Client-Side Filtering**: Lower server overhead, works offline
- **Leaflet**: Lightweight, extensible, excellent plugin ecosystem

### 14.2 Data Approach
- **CSV Files**: Simple, version-controllable, no schema migrations
- **Compile-Time Embedding**: No runtime file reads, immutable data
- **In-Memory Parsing**: Fast API responses, trades memory for speed

---

## 15. Readiness for Individual Facility Pages Implementation

### 15.1 Existing Infrastructure
✅ Clean data models with complete facility information
✅ RESTful API architecture ready for extension
✅ Popup content generation logic reusable
✅ Multi-country support framework in place
✅ Mobile-responsive design patterns established
✅ URL parameter handling for state sharing

### 15.2 What Needs Building
❌ Facility detail page template
❌ Single facility API endpoint (`/api/facility/:id`)
❌ Static page generation pipeline (100k+ files)
❌ URL routing for individual facilities
❌ Links from markers to detail pages
❌ SEO meta tag generation per facility

### 15.3 Implementation Complexity
- **Estimated Effort**: 2-3 days of development
- **Complexity**: Medium (straightforward but volume is large)
- **Scalability**: Rust/Shuttle can generate 100k+ pages (~30 min build)
- **Storage**: ~5-10 GB for 100k HTML files (Netlify can handle)

### 15.4 Technical Approach Recommendation
**Static Page Generation** (optimal for activism/SEO):
1. Rust build script reads all facilities
2. Generates `facility/{id}.html` for each
3. Uses reusable template + facility data
4. Deploys with frontend to Netlify
5. Individual facility pages rank in Google searches
6. Permanent, shareable URLs
7. No server overhead for individual facility views

---

## 16. Future Enhancement Opportunities

### 16.1 Planned Features (from notes.md)
- [ ] Add mini tutorial on beginning page
- [ ] Add Italy dataset

### 16.2 Potential Improvements
- **Caching**: Redis or in-process cache for CSV parsing
- **Database**: Replace CSVs with PostgreSQL for easier updates
- **Pagination**: Implement server-side pagination
- **Search**: Full-text search index for facility names
- **Export**: Bulk data export functionality
- **Analytics**: Optional analytics (respecting privacy)
- **Internationalization**: Multilingual support
- **Advanced Filters**: Complex query builders
- **Data Validation**: Automated data quality checks
- **User Submissions**: Community-contributed data/corrections

---

## Appendix A: Complete File Inventory

```
PROJECT ROOT
├── src/
│   ├── main.rs (45 lines)
│   ├── lib.rs (175 lines)
│   ├── location.rs (409 lines)
│   └── bin/
│       └── da-foedevarestyrelsen/main.rs
├── static/
│   ├── index.html
│   ├── about.html
│   ├── howtouse.html
│   ├── contribute.html
│   ├── app.js (1,250 lines)
│   ├── footer.js
│   ├── footer.html
│   ├── style.css
│   ├── map-filter-styles.css
│   ├── assets/
│   │   └── icon.png
│   └── modules/
│       ├── constants.js (285 lines)
│       ├── geoUtils.js (279 lines)
│       ├── iconUtils.js
│       ├── leafletControls.js
│       ├── popupBuilder.js (188 lines)
│       ├── drawerManager.js
│       └── __tests__/
├── static_data/
│   ├── us/
│   │   ├── locations.csv (4.1 MB)
│   │   ├── aphis_data_final.csv (199 KB)
│   │   └── inspection_reports.csv (769 KB)
│   ├── uk/locations.csv (2.2 MB)
│   ├── de/locations.csv (3.8 MB)
│   ├── es/locations.csv (1.1 MB)
│   ├── fr/locations.csv (626 KB)
│   └── dk/locations.csv (323 KB)
├── Cargo.toml
├── Cargo.lock
├── package.json
├── jest.config.js
├── jest.setup.js
├── Shuttle.toml
├── README.md
├── LICENSE (AGPLv3)
├── DATA_LICENSE (CC-BY-NC-SA)
└── notes.md
```

---

## Appendix B: API Response Examples

### GET /api/locations?country_code=us

**Response** (array of LocationResponse):
```json
[
  {
    "country": "us",
    "establishment_id": "6407",
    "establishment_name": "(Lebanon) - Godshall's Quality Meats, Inc.",
    "latitude": 40.357434,
    "longitude": -76.39405099,
    "type": "Meat Processing; Poultry Processing",
    "state": "PA",
    "city": "Lebanon",
    "street": "1415 Weavertown Road",
    "zip": "17046",
    "slaughter": "",
    "animals_slaughtered": "N/A",
    "animals_processed": "Beef, Pork, Chicken",
    "slaughter_volume_category": "",
    "processing_volume_category": "4.0",
    "dbas": "Godshall's Quality Meats; Kutztown Brand; Millside Brand; Weaver's Famous Brand",
    "phone": "(717) 274-6100",
    "grant_date": "11/2/2021"
  }
]
```

---

## Appendix C: Environment & Dependencies

### System Requirements
- **Rust**: 1.70+ (2024 edition is unstable)
- **Node.js**: 14+ (for npm)
- **Python 3**: 3.7+ (for local server)

### Development Commands
```bash
# Rust
cargo build
cargo shuttle run --port 8001
cargo shuttle deploy

# JavaScript
npm install
npm test
npm test:watch

# Local server
python3 -m http.server 8000
```

---

**Analysis Date**: November 30, 2025
**Scope**: Production code only
**Total Lines of Code**: ~3,000
**Data Volume**: 48,000+ facilities across 6 countries
