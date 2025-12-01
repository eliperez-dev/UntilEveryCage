#!/usr/bin/env python3
import csv
import os
import re
from pathlib import Path

ITALY_PROVINCE_CODES = {
    'AG': 'Agrigento', 'AL': 'Alessandria', 'AN': 'Ancona', 'AO': 'Aosta', 'AP': "Ascoli Piceno",
    'AQ': "L'Aquila", 'AR': 'Arezzo', 'AT': 'Asti', 'AV': 'Avellino', 'BA': 'Bari',
    'BL': 'Belluno', 'BN': 'Benevento', 'BO': 'Bologna', 'BR': 'Brindisi', 'BS': 'Brescia',
    'BT': 'Barletta-Andria-Trani', 'BZ': 'Bolzano', 'CA': 'Cagliari', 'CB': 'Campobasso',
    'CE': 'Caserta', 'CH': 'Chieti', 'CI': 'Carbonia-Iglesias', 'CL': 'Caltanissetta',
    'CN': 'Cuneo', 'CO': 'Como', 'CR': 'Cremona', 'CS': 'Cosenza', 'CT': 'Catania',
    'CZ': 'Catanzaro', 'EN': 'Enna', 'EO': 'East Liguria', 'FE': 'Ferrara', 'FG': 'Foggia',
    'FI': 'Firenze', 'FM': 'Fermo', 'FR': 'Frosinone', 'FS': 'Pesaro e Urbino', 'FU': 'Forlì-Cesena',
    'GE': 'Genova', 'GO': 'Gorizia', 'GR': 'Grosseto', 'IM': 'Imperia', 'IS': 'Isernia',
    'KR': 'Crotone', 'LC': 'Lecco', 'LE': 'Lecce', 'LI': 'Livorno', 'LO': 'Lodi', 'LT': 'Latina',
    'LU': 'Lucca', 'MB': 'Monza e Brianza', 'MC': 'Macerata', 'ME': 'Messina', 'MI': 'Milano',
    'MN': 'Mantova', 'MO': 'Modena', 'MS': 'Massa-Carrara', 'MT': 'Matera', 'NA': 'Napoli',
    'NO': 'Novara', 'NU': 'Nuoro', 'OG': 'Ogliastra', 'OR': 'Oristano', 'OT': 'Olbia-Tempio',
    'PA': 'Palermo', 'PC': 'Piacenza', 'PD': 'Padova', 'PE': 'Pescara', 'PG': 'Perugia',
    'PI': 'Pisa', 'PN': 'Pordenone', 'PO': 'Prato', 'PR': 'Parma', 'PS': 'Pesaro e Urbino',
    'PT': 'Pistoia', 'PU': 'Pesaro e Urbino', 'PV': 'Pavia', 'PZ': 'Potenza', 'RA': 'Ravenna',
    'RC': 'Reggio di Calabria', 'RE': 'Reggio Emilia', 'RG': 'Ragusa', 'RI': 'Rieti',
    'RM': 'Roma', 'RN': 'Rimini', 'RO': 'Rovigo', 'SA': 'Salerno', 'SI': 'Siena',
    'SO': 'Sondrio', 'SP': 'La Spezia', 'SR': 'Siracusa', 'SS': 'Sassari', 'SV': 'Savona',
    'TA': 'Taranto', 'TE': 'Teramo', 'TN': 'Trento', 'TO': 'Torino', 'TP': 'Trapani',
    'TR': 'Terni', 'TS': 'Trieste', 'TV': 'Treviso', 'UA': 'Urbania', 'UD': 'Udine',
    'VA': 'Varese', 'VB': 'Verbania', 'VC': 'Vercelli', 'VE': 'Venezia', 'VI': 'Vicenza',
    'VR': 'Verona', 'VS': 'Medio Campidano', 'VT': 'Viterbo', 'VV': 'Vibo Valentia',
}

def parse_address(town_region_str):
    """
    Parse Italy address format: "VIA/CONTRADA/etc, CITY (PROVINCE_CODE)"
    Returns dict with street, city, state (province)
    """
    if not town_region_str:
        return {'street': '', 'city': '', 'state': ''}
    
    street = ''
    city = ''
    state = ''
    
    pattern = r'^(.+?),\s*(.+?)\s*\(([A-Z]{2})\)$'
    match = re.match(pattern, town_region_str.strip())
    
    if match:
        street = match.group(1).strip()
        city = match.group(2).strip()
        province_code = match.group(3).strip()
        state = ITALY_PROVINCE_CODES.get(province_code, province_code)
    else:
        street = town_region_str.strip()
    
    return {'street': street, 'city': city, 'state': state}

def parse_activities(associated_activities, species_str):
    """
    Parse activities and species into facility type classification
    CP = Cutting/Processing
    SH = Slaughter
    """
    activities = []
    
    if 'CP' in str(associated_activities):
        activities.append('Meat Processing')
    
    if 'SH' in str(associated_activities):
        activities.append('Meat Slaughter')
    
    if not activities:
        activities.append('Meat Production')
    
    return '; '.join(activities)

def parse_species(species_str):
    """
    Parse species codes into animal types
    B = Beef (Cattle)
    C = Chicken/Poultry
    O = Other
    P = Pork (Pig)
    S = Sheep
    """
    if not species_str or species_str == '-':
        return {}
    
    codes = [c.strip() for c in str(species_str).split('|')]
    
    species_dict = {
        'cattle': 'B' in codes,
        'poultry': 'C' in codes,
        'pork': 'P' in codes,
        'sheep': 'S' in codes,
        'other': 'O' in codes,
    }
    
    return species_dict

def get_animals_slaughtered(activities, species_dict):
    """Determine slaughtered animals"""
    animals = []
    
    if 'SH' not in str(activities):
        return 'N/A'
    
    if species_dict.get('cattle'):
        animals.append('Cattle (Cows, Bulls)')
    if species_dict.get('pork'):
        animals.append('Pigs')
    if species_dict.get('poultry'):
        animals.append('Chickens')
    if species_dict.get('sheep'):
        animals.append('Sheep & Lambs')
    if species_dict.get('other'):
        animals.append('Other')
    
    return ', '.join(animals) if animals else 'N/A'

def convert_italy_data(input_csv, output_csv):
    """Convert Italy CSV to standardized format"""
    
    print(f"Reading Italy data from: {input_csv}")
    
    with open(input_csv, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f"Found {len(rows)} facilities")
    
    us_columns = [
        'establishment_id', 'establishment_number', 'establishment_name', 'duns_number',
        'street', 'city', 'state', 'zip', 'phone', 'grant_date', 'type', 'dbas',
        'district', 'circuit', 'size', 'latitude', 'longitude', 'county', 'fips_code',
        'meat_exemption_custom_slaughter', 'poultry_exemption_custom_slaughter', 'slaughter',
        'meat_slaughter', 'beef_cow_slaughter', 'steer_slaughter', 'heifer_slaughter',
        'bull_stag_slaughter', 'dairy_cow_slaughter', 'heavy_calf_slaughter', 'bob_veal_slaughter',
        'formula_fed_veal_slaughter', 'non_formula_fed_veal_slaughter', 'market_swine_slaughter',
        'sow_slaughter', 'roaster_swine_slaughter', 'boar_stag_swine_slaughter', 
        'stag_swine_slaughter', 'feral_swine_slaughter', 'goat_slaughter', 'young_goat_slaughter',
        'adult_goat_slaughter', 'sheep_slaughter', 'lamb_slaughter', 'deer_reindeer_slaughter',
        'antelope_slaughter', 'elk_slaughter', 'bison_slaughter', 'buffalo_slaughter',
        'water_buffalo_slaughter', 'cattalo_slaughter', 'yak_slaughter', 
        'other_voluntary_livestock_slaughter', 'rabbit_slaughter', 'poultry_slaughter',
        'young_chicken_slaughter', 'light_fowl_slaughter', 'heavy_fowl_slaughter',
        'capon_slaughter', 'young_turkey_slaughter', 'young_breeder_turkey_slaughter',
        'old_breeder_turkey_slaughter', 'fryer_roaster_turkey_slaughter', 'duck_slaughter',
        'goose_slaughter', 'pheasant_slaughter', 'quail_slaughter', 'guinea_slaughter',
        'ostrich_slaughter', 'emu_slaughter', 'rhea_slaughter', 'squab_slaughter',
        'other_voluntary_poultry_slaughter', 'slaughter_or_processing_only', 'slaughter_only_class',
        'slaughter_only_species', 'meat_slaughter_only_species', 'poultry_slaughter_only_species',
        'slaughter_volume_category', 'processing_volume_category',
        'beef_processing', 'pork_processing', 'antelope_processing', 'bison_processing',
        'buffalo_processing', 'deer_processing', 'elk_processing', 'goat_processing',
        'other_voluntary_livestock_processing', 'rabbit_processing', 'reindeer_processing',
        'sheep_processing', 'yak_processing', 'chicken_processing', 'duck_processing',
        'goose_processing', 'pigeon_processing', 'ratite_processing', 'turkey_processing',
        'exotic_poultry_processing', 'other_voluntary_poultry_processing'
    ]
    
    output_rows = []
    
    for idx, italy_row in enumerate(rows):
        facility_name = italy_row['NAME'][:30] if italy_row['NAME'] else 'Unknown'
        print(f"Processing facility {idx + 1}/{len(rows)}")
        
        approval_number = italy_row.get('APPROVAL NUMBER', '').strip()
        if not approval_number:
            continue
        
        address_parts = parse_address(italy_row.get('TOWN/REGION', ''))
        species_dict = parse_species(italy_row.get('SPECIES', ''))
        activities = italy_row.get('ASSOCIATED ACTIVITIES', '')
        activities_str = parse_activities(activities, italy_row.get('SPECIES', ''))
        
        us_row = {}
        
        us_row['establishment_id'] = approval_number
        us_row['establishment_number'] = approval_number
        us_row['establishment_name'] = italy_row.get('NAME', '').strip()
        us_row['duns_number'] = italy_row.get('VAT', '').strip()
        
        us_row['street'] = address_parts['street']
        us_row['city'] = address_parts['city']
        us_row['state'] = address_parts['state']
        us_row['zip'] = ''
        us_row['phone'] = ''
        
        us_row['grant_date'] = ''
        us_row['type'] = activities_str
        us_row['dbas'] = ''
        
        us_row['district'] = ''
        us_row['circuit'] = ''
        us_row['size'] = 'Unknown'
        us_row['latitude'] = 0.0
        us_row['longitude'] = 0.0
        us_row['county'] = address_parts['state']
        us_row['fips_code'] = ''
        
        us_row['meat_exemption_custom_slaughter'] = ''
        us_row['poultry_exemption_custom_slaughter'] = ''
        
        slaughter_fields = [
            'slaughter', 'meat_slaughter', 'beef_cow_slaughter', 'steer_slaughter', 'heifer_slaughter',
            'bull_stag_slaughter', 'dairy_cow_slaughter', 'heavy_calf_slaughter', 'bob_veal_slaughter',
            'formula_fed_veal_slaughter', 'non_formula_fed_veal_slaughter', 'market_swine_slaughter',
            'sow_slaughter', 'roaster_swine_slaughter', 'boar_stag_swine_slaughter', 
            'stag_swine_slaughter', 'feral_swine_slaughter', 'goat_slaughter', 'young_goat_slaughter',
            'adult_goat_slaughter', 'sheep_slaughter', 'lamb_slaughter', 'deer_reindeer_slaughter',
            'antelope_slaughter', 'elk_slaughter', 'bison_slaughter', 'buffalo_slaughter',
            'water_buffalo_slaughter', 'cattalo_slaughter', 'yak_slaughter', 
            'other_voluntary_livestock_slaughter', 'rabbit_slaughter', 'poultry_slaughter',
            'young_chicken_slaughter', 'light_fowl_slaughter', 'heavy_fowl_slaughter',
            'capon_slaughter', 'young_turkey_slaughter', 'young_breeder_turkey_slaughter',
            'old_breeder_turkey_slaughter', 'fryer_roaster_turkey_slaughter', 'duck_slaughter',
            'goose_slaughter', 'pheasant_slaughter', 'quail_slaughter', 'guinea_slaughter',
            'ostrich_slaughter', 'emu_slaughter', 'rhea_slaughter', 'squab_slaughter',
            'other_voluntary_poultry_slaughter', 'slaughter_or_processing_only', 'slaughter_only_class',
            'slaughter_only_species', 'meat_slaughter_only_species', 'poultry_slaughter_only_species',
            'slaughter_volume_category'
        ]
        
        for field in slaughter_fields:
            us_row[field] = ''
        
        us_row['processing_volume_category'] = 'Unknown'
        
        processing_fields = [
            'beef_processing', 'pork_processing', 'antelope_processing', 'bison_processing',
            'buffalo_processing', 'deer_processing', 'elk_processing', 'goat_processing',
            'other_voluntary_livestock_processing', 'rabbit_processing', 'reindeer_processing',
            'sheep_processing', 'yak_processing', 'chicken_processing', 'duck_processing',
            'goose_processing', 'pigeon_processing', 'ratite_processing', 'turkey_processing',
            'exotic_poultry_processing', 'other_voluntary_poultry_processing'
        ]
        
        for field in processing_fields:
            us_row[field] = ''
        
        output_rows.append(us_row)
    
    print(f"Writing {len(output_rows)} facilities to: {output_csv}")
    
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    
    with open(output_csv, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=us_columns)
        writer.writeheader()
        writer.writerows(output_rows)
    
    print(f"Conversion complete! Processed {len(output_rows)} facilities.")

if __name__ == "__main__":
    input_file = "dirty-datasets/italy_locations.csv"
    output_file = "static_data/it/locations.csv"
    
    convert_italy_data(input_file, output_file)
    print(f"\nOutput file: {output_file}")
