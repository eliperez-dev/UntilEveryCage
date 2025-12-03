// Until Every Cage is Empty
// Copyright (C) 2025 Eli Perez
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program. If not, see <https://www.gnu.org/licenses/>.

// Contact the developer directly at untileverycageproject@protonmail.com
use serde::Deserialize;
use serde::Serialize;

#[derive(Serialize, Deserialize, Debug, Default)]
pub struct Location {
    pub establishment_id: String,
    #[serde(default)]
    pub establishment_number: String,
    pub establishment_name: String,
    #[serde(default)]
    pub duns_number: String,
    pub street: String,
    pub city: String,
    pub state: String,
    pub zip: String,
    pub phone: String,
    pub grant_date: String,
    #[serde(rename = "type")]
    pub activities: String,
    #[serde(default)]
    pub animals_slaughtered_list: String,
    #[serde(default)]
    pub animals_processed_list: String,
    pub dbas: String,
    #[serde(default)]
    pub district: String,
    #[serde(default)]
    pub circuit: String,
    #[serde(default)]
    pub size: String,
    pub latitude: f64,
    pub longitude: f64,
    #[serde(default)]
    pub county: String,
    #[serde(default)]
    pub fips_code: String,
    #[serde(default)]
    pub meat_exemption_custom_slaughter: String,
    #[serde(default)]
    pub poultry_exemption_custom_slaughter: String,
    pub slaughter: String,
    #[serde(default)]
    pub meat_slaughter: String,
    #[serde(default)]
    pub beef_cow_slaughter: String,
    #[serde(default)]
    pub steer_slaughter: String,
    #[serde(default)]
    pub heifer_slaughter: String,
    #[serde(default)]
    pub bull_stag_slaughter: String,
    #[serde(default)]
    pub dairy_cow_slaughter: String,
    #[serde(default)]
    pub heavy_calf_slaughter: String,
    #[serde(default)]
    pub bob_veal_slaughter: String,
    #[serde(default)]
    pub formula_fed_veal_slaughter: String,
    #[serde(default)]
    pub non_formula_fed_veal_slaughter: String,
    #[serde(default)]
    pub market_swine_slaughter: String,
    #[serde(default)]
    pub sow_slaughter: String,
    #[serde(default)]
    pub roaster_swine_slaughter: String,
    #[serde(default)]
    pub boar_stag_swine_slaughter: String,
    #[serde(default)]
    pub stag_swine_slaughter: String,
    #[serde(default)]
    pub feral_swine_slaughter: String,
    #[serde(default)]
    pub goat_slaughter: String,
    #[serde(default)]
    pub young_goat_slaughter: String,
    #[serde(default)]
    pub adult_goat_slaughter: String,
    #[serde(default)]
    pub sheep_slaughter: String,
    #[serde(default)]
    pub lamb_slaughter: String,
    #[serde(default)]
    pub deer_reindeer_slaughter: String,
    #[serde(default)]
    pub antelope_slaughter: String,
    #[serde(default)]
    pub elk_slaughter: String,
    #[serde(default)]
    pub bison_slaughter: String,
    #[serde(default)]
    pub buffalo_slaughter: String,
    #[serde(default)]
    pub water_buffalo_slaughter: String,
    #[serde(default)]
    pub cattalo_slaughter: String,
    #[serde(default)]
    pub yak_slaughter: String,
    #[serde(default)]
    pub other_voluntary_livestock_slaughter: String,
    #[serde(default)]
    pub rabbit_slaughter: String,
    #[serde(default)]
    pub poultry_slaughter: String,
    #[serde(default)]
    pub young_chicken_slaughter: String,
    #[serde(default)]
    pub light_fowl_slaughter: String,
    #[serde(default)]
    pub heavy_fowl_slaughter: String,
    #[serde(default)]
    pub capon_slaughter: String,
    #[serde(default)]
    pub young_turkey_slaughter: String,
    #[serde(default)]
    pub young_breeder_turkey_slaughter: String,
    #[serde(default)]
    pub old_breeder_turkey_slaughter: String,
    #[serde(default)]
    pub fryer_roaster_turkey_slaughter: String,
    #[serde(default)]
    pub duck_slaughter: String,
    #[serde(default)]
    pub goose_slaughter: String,
    #[serde(default)]
    pub pheasant_slaughter: String,
    #[serde(default)]
    pub quail_slaughter: String,
    #[serde(default)]
    pub guinea_slaughter: String,
    #[serde(default)]
    pub ostrich_slaughter: String,
    #[serde(default)]
    pub emu_slaughter: String,
    #[serde(default)]
    pub rhea_slaughter: String,
    #[serde(default)]
    pub squab_slaughter: String,
    #[serde(default)]
    pub other_voluntary_poultry_slaughter: String,
    #[serde(default)]
    pub slaughter_or_processing_only: String,
    #[serde(default)]
    pub slaughter_only_class: String,
    #[serde(default)]
    pub slaughter_only_species: String,
    #[serde(default)]
    pub meat_slaughter_only_species: String,
    #[serde(default)]
    pub poultry_slaughter_only_species: String,
    pub slaughter_volume_category: String,
    pub processing_volume_category: String,

    // --- PROCESSING FIELDS ---
    #[serde(default)]
    pub beef_processing: String,
    #[serde(default)]
    pub pork_processing: String,
    #[serde(default)]
    pub antelope_processing: String,
    #[serde(default)]
    pub bison_processing: String,
    #[serde(default)]
    pub buffalo_processing: String,
    #[serde(default)]
    pub deer_processing: String,
    #[serde(default)]
    pub elk_processing: String,
    #[serde(default)]
    pub goat_processing: String,
    #[serde(default)]
    pub other_voluntary_livestock_processing: String,
    #[serde(default)]
    pub rabbit_processing: String,
    #[serde(default)]
    pub reindeer_processing: String,
    #[serde(default)]
    pub sheep_processing: String,
    #[serde(default)]
    pub yak_processing: String,
    #[serde(default)]
    pub chicken_processing: String,
    #[serde(default)]
    pub duck_processing: String,
    #[serde(default)]
    pub goose_processing: String,
    #[serde(default)]
    pub pigeon_processing: String,
    #[serde(default)]
    pub ratite_processing: String,
    #[serde(default)]
    pub turkey_processing: String,
    #[serde(default)]
    pub exotic_poultry_processing: String,
    #[serde(default)]
    pub other_voluntary_poultry_processing: String,
}

// --- NEW HELPER FUNCTION FOR PROCESSED ANIMALS ---
pub fn get_processed_animals(location: &Location) -> String {
    if !location.animals_processed_list.is_empty() {
        return location.animals_processed_list.clone();
    }

    let mut processed_animals: Vec<&str> = Vec::new();

    // Helper closure to check the Option<String> fields safely
    let mut add_if_processed = |field: &str, name: &'static str| {
        if field == "Yes" {
            processed_animals.push(name);
        }
    };

    // --- Livestock Processing ---
    add_if_processed(&location.beef_processing, "Beef");
    add_if_processed(&location.pork_processing, "Pork");
    add_if_processed(&location.antelope_processing, "Antelope");
    add_if_processed(&location.bison_processing, "Bison");
    add_if_processed(&location.buffalo_processing, "Buffalo");
    add_if_processed(&location.deer_processing, "Deer");
    add_if_processed(&location.elk_processing, "Elk");
    add_if_processed(&location.goat_processing, "Goat");
    add_if_processed(
        &location.other_voluntary_livestock_processing,
        "Other Voluntary Livestock",
    );
    add_if_processed(&location.rabbit_processing, "Rabbit");
    add_if_processed(&location.reindeer_processing, "Reindeer");
    add_if_processed(&location.sheep_processing, "Sheep");
    add_if_processed(&location.yak_processing, "Yak");

    // --- Poultry Processing ---
    add_if_processed(&location.chicken_processing, "Chicken");
    add_if_processed(&location.duck_processing, "Duck");
    add_if_processed(&location.goose_processing, "Goose");
    add_if_processed(&location.pigeon_processing, "Pigeon");
    add_if_processed(&location.ratite_processing, "Ratite (Ostrich/Emu)");
    add_if_processed(&location.turkey_processing, "Turkey");
    add_if_processed(&location.exotic_poultry_processing, "Exotic Poultry");
    add_if_processed(
        &location.other_voluntary_poultry_processing,
        "Other Voluntary Poultry",
    );

    if processed_animals.is_empty() {
        "N/A".to_string()
    } else {
        processed_animals.join(", ")
    }
}

// --- UPDATED to use more common names ---
pub fn get_slaughtered_animals(location: &Location) -> String {
    if !location.animals_slaughtered_list.is_empty() {
        return location.animals_slaughtered_list.clone();
    }

    let mut killed_animals: Vec<&str> = Vec::new();

    if location.beef_cow_slaughter == "Yes"
        || location.steer_slaughter == "Yes"
        || location.heifer_slaughter == "Yes"
        || location.bull_stag_slaughter == "Yes"
        || location.dairy_cow_slaughter == "Yes"
    {
        killed_animals.push("Cattle (Cows, Bulls)");
    }
    if location.heavy_calf_slaughter == "Yes"
        || location.bob_veal_slaughter == "Yes"
        || location.formula_fed_veal_slaughter == "Yes"
        || location.non_formula_fed_veal_slaughter == "Yes"
    {
        killed_animals.push("Calves (Veal)");
    }
    if location.market_swine_slaughter == "Yes"
        || location.sow_slaughter == "Yes"
        || location.roaster_swine_slaughter == "Yes"
        || location.boar_stag_swine_slaughter == "Yes"
        || location.stag_swine_slaughter == "Yes"
        || location.feral_swine_slaughter == "Yes"
    {
        killed_animals.push("Pigs");
    }
    if location.goat_slaughter == "Yes"
        || location.young_goat_slaughter == "Yes"
        || location.adult_goat_slaughter == "Yes"
    {
        killed_animals.push("Goats");
    }
    if location.sheep_slaughter == "Yes" || location.lamb_slaughter == "Yes" {
        killed_animals.push("Sheep & Lambs");
    }
    if location.deer_reindeer_slaughter == "Yes" {
        killed_animals.push("Deer & Reindeer");
    }
    if location.antelope_slaughter == "Yes" {
        killed_animals.push("Antelope");
    }
    if location.elk_slaughter == "Yes" {
        killed_animals.push("Elk");
    }
    if location.bison_slaughter == "Yes"
        || location.buffalo_slaughter == "Yes"
        || location.water_buffalo_slaughter == "Yes"
        || location.cattalo_slaughter == "Yes"
    {
        killed_animals.push("Bison & Buffalo");
    }
    if location.yak_slaughter == "Yes" {
        killed_animals.push("Yak");
    }
    if location.other_voluntary_livestock_slaughter == "Yes" {
        killed_animals.push("Other Livestock");
    }
    if location.rabbit_slaughter == "Yes" {
        killed_animals.push("Rabbits");
    }

    // --- Poultry ---
    if location.young_chicken_slaughter == "Yes"
        || location.light_fowl_slaughter == "Yes"
        || location.heavy_fowl_slaughter == "Yes"
        || location.capon_slaughter == "Yes"
    {
        killed_animals.push("Chickens");
    }
    if location.young_turkey_slaughter == "Yes"
        || location.young_breeder_turkey_slaughter == "Yes"
        || location.old_breeder_turkey_slaughter == "Yes"
        || location.fryer_roaster_turkey_slaughter == "Yes"
    {
        killed_animals.push("Turkeys");
    }
    if location.duck_slaughter == "Yes" {
        killed_animals.push("Ducks");
    }
    if location.goose_slaughter == "Yes" {
        killed_animals.push("Geese");
    }
    if location.pheasant_slaughter == "Yes" {
        killed_animals.push("Pheasants");
    }
    if location.quail_slaughter == "Yes" {
        killed_animals.push("Quail");
    }
    if location.guinea_slaughter == "Yes" {
        killed_animals.push("Guinea Fowl");
    }
    if location.ostrich_slaughter == "Yes"
        || location.emu_slaughter == "Yes"
        || location.rhea_slaughter == "Yes"
    {
        killed_animals.push("Ratites (Ostrich, Emu, etc.)");
    }
    if location.squab_slaughter == "Yes" {
        killed_animals.push("Pigeons (Squab)");
    }
    if location.other_voluntary_poultry_slaughter == "Yes" {
        killed_animals.push("Other Poultry");
    }

    // Join the collected names with a comma and space
    killed_animals.join(", ")
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct AphisReport {
    #[serde(rename = "Account Name")]
    pub account_name: String,
    #[serde(rename = "Customer Number_x")]
    pub customer_number_x: String,
    #[serde(rename = "Certificate Number")]
    pub certificate_number: String,
    #[serde(rename = "Registration Type")]
    pub registration_type: String,
    #[serde(rename = "Certificate Status")]
    pub certificate_status: String,
    #[serde(rename = "Status Date")]
    pub status_date: String,
    #[serde(rename = "Address Line 1")]
    pub address_line_1: String,
    #[serde(rename = "Address Line 2")]
    pub address_line_2: String,
    #[serde(rename = "City-State-Zip")]
    pub city_state_zip: String,
    #[serde(rename = "County")]
    pub county: String,
    #[serde(rename = "Customer Number_y")]
    pub customer_number_y: String,
    #[serde(rename = "Year")]
    pub year: String,
    #[serde(rename = "Dogs")]
    pub dogs: String,
    #[serde(rename = "Cats")]
    pub cats: String,
    #[serde(rename = "Guinea Pigs")]
    pub guinea_pigs: String,
    #[serde(rename = "Hamsters")]
    pub hamsters: String,
    #[serde(rename = "Rabbits")]
    pub rabbits: String,
    #[serde(rename = "Non-Human Primates")]
    pub non_human_primates: String,
    #[serde(rename = "Sheep")]
    pub sheep: String,
    #[serde(rename = "Pigs")]
    pub pigs: String,
    #[serde(rename = "Other Farm Animals")]
    pub other_farm_animals: String,
    #[serde(rename = "All Other Animals")]
    pub all_other_animals: String,
    pub latitude: f64,
    pub longitude: f64,
    #[serde(rename = "Animals Tested On")]
    pub animals_tested: Option<String>,
}

// This function takes a reference to an AphisReport and returns the formatted string.
pub fn get_tested_animals(report: &AphisReport) -> String {
    let mut tested_animals: Vec<String> = Vec::new();

    // Helper closure to reduce code repetition.
    // It takes the count string and the animal name, and if valid, adds the formatted string to the list.
    let mut add_if_tested = |count_str: &str, name: &str| {
        // Attempt to parse the string into an integer.
        // If it succeeds and the number is > 0, format it and push to the vector.
        if let Ok(num) = count_str.parse::<f32>() {
            if num > 0.0 {
                tested_animals.push(format!("{} {}", num as i32, name));
            }
        }
    };

    // Call the helper for each animal type
    add_if_tested(&report.dogs, "Dogs");
    add_if_tested(&report.cats, "Cats");
    add_if_tested(&report.guinea_pigs, "Guinea Pigs");
    add_if_tested(&report.hamsters, "Hamsters");
    add_if_tested(&report.rabbits, "Rabbits");
    add_if_tested(&report.non_human_primates, "Non-Human Primates");
    add_if_tested(&report.sheep, "Sheep");
    add_if_tested(&report.pigs, "Pigs");
    add_if_tested(&report.other_farm_animals, "Other Farm Animals");
    add_if_tested(&report.all_other_animals, "All Other Animals");

    // If no animals were found, return "N/A". Otherwise, join the list.
    if tested_animals.is_empty() {
        "Unknown".to_string()
    } else {
        tested_animals.join(", ")
    }
}

// --- NEW STRUCT for Inspection Reports ---
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct InspectionReport {
    #[serde(rename = "Account Name")]
    pub account_name: String,
    #[serde(rename = "Customer Number")]
    pub customer_number: String,
    #[serde(rename = "Certificate Number")]
    pub certificate_number: String,
    #[serde(rename = "License Type")]
    pub license_type: String,
    #[serde(rename = "Certificate Status")]
    pub certificate_status: String,
    #[serde(rename = "Status Date")]
    pub status_date: String,
    #[serde(rename = "Address Line 1")]
    pub address_line_1: String,
    #[serde(rename = "Address Line 2")]
    pub address_line_2: String,
    #[serde(rename = "City-State-Zip")]
    pub city_state_zip: String,
    #[serde(rename = "County")]
    pub county: String,
    #[serde(rename = "City")]
    pub city: String,
    #[serde(rename = "State")]
    pub state: String,
    #[serde(rename = "Zip")]
    pub zip: String,
    #[serde(rename = "Geocodio Latitude")]
    pub latitude: f64,
    #[serde(rename = "Geocodio Longitude")]
    pub longitude: f64,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn create_default_location() -> Location {
        Location::default()
    }

    mod get_slaughtered_animals_tests {
        use super::*;

        #[test]
        fn test_empty_location_returns_empty_string() {
            let location = create_default_location();
            let result = get_slaughtered_animals(&location);
            assert_eq!(result, "");
        }

        #[test]
        fn test_cattle_slaughter_detection() {
            let mut location = create_default_location();
            location.beef_cow_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Cattle (Cows, Bulls)"));
        }

        #[test]
        fn test_steer_slaughter_detection() {
            let mut location = create_default_location();
            location.steer_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Cattle (Cows, Bulls)"));
        }

        #[test]
        fn test_veal_calf_slaughter_detection() {
            let mut location = create_default_location();
            location.heavy_calf_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Calves (Veal)"));
        }

        #[test]
        fn test_swine_slaughter_detection() {
            let mut location = create_default_location();
            location.market_swine_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Pigs"));
        }

        #[test]
        fn test_poultry_slaughter_detection() {
            let mut location = create_default_location();
            location.young_chicken_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Chickens"));
        }

        #[test]
        fn test_turkey_slaughter_detection() {
            let mut location = create_default_location();
            location.young_turkey_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Turkeys"));
        }

        #[test]
        fn test_sheep_and_lamb_slaughter_detection() {
            let mut location = create_default_location();
            location.sheep_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Sheep & Lambs"));
        }

        #[test]
        fn test_rabbit_slaughter_detection() {
            let mut location = create_default_location();
            location.rabbit_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Rabbits"));
        }

        #[test]
        fn test_duck_slaughter_detection() {
            let mut location = create_default_location();
            location.duck_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Ducks"));
        }

        #[test]
        fn test_goose_slaughter_detection() {
            let mut location = create_default_location();
            location.goose_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Geese"));
        }

        #[test]
        fn test_multiple_animals_comma_separated() {
            let mut location = create_default_location();
            location.beef_cow_slaughter = "Yes".to_string();
            location.market_swine_slaughter = "Yes".to_string();
            location.young_chicken_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Cattle (Cows, Bulls)"));
            assert!(result.contains("Pigs"));
            assert!(result.contains("Chickens"));
            assert!(result.contains(", "));
        }

        #[test]
        fn test_bison_and_buffalo_grouping() {
            let mut location = create_default_location();
            location.bison_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Bison & Buffalo"));
        }

        #[test]
        fn test_buffalo_slaughter_detection() {
            let mut location = create_default_location();
            location.buffalo_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Bison & Buffalo"));
        }

        #[test]
        fn test_ratite_slaughter_detection() {
            let mut location = create_default_location();
            location.ostrich_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Ratites (Ostrich, Emu, etc.)"));
        }

        #[test]
        fn test_emu_slaughter_detection() {
            let mut location = create_default_location();
            location.emu_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Ratites (Ostrich, Emu, etc.)"));
        }

        #[test]
        fn test_pheasant_slaughter_detection() {
            let mut location = create_default_location();
            location.pheasant_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Pheasants"));
        }

        #[test]
        fn test_quail_slaughter_detection() {
            let mut location = create_default_location();
            location.quail_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Quail"));
        }

        #[test]
        fn test_guinea_fowl_slaughter_detection() {
            let mut location = create_default_location();
            location.guinea_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Guinea Fowl"));
        }

        #[test]
        fn test_squab_slaughter_detection() {
            let mut location = create_default_location();
            location.squab_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Pigeons (Squab)"));
        }

        #[test]
        fn test_other_voluntary_poultry_slaughter() {
            let mut location = create_default_location();
            location.other_voluntary_poultry_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Other Poultry"));
        }

        #[test]
        fn test_antelope_slaughter_detection() {
            let mut location = create_default_location();
            location.antelope_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Antelope"));
        }

        #[test]
        fn test_elk_slaughter_detection() {
            let mut location = create_default_location();
            location.elk_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Elk"));
        }

        #[test]
        fn test_yak_slaughter_detection() {
            let mut location = create_default_location();
            location.yak_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(result.contains("Yak"));
        }

        #[test]
        fn test_case_sensitivity_yes_detection() {
            let mut location = create_default_location();
            location.beef_cow_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(!result.is_empty());
        }

        #[test]
        fn test_case_sensitivity_no_not_included() {
            let mut location = create_default_location();
            location.beef_cow_slaughter = "No".to_string();
            let result = get_slaughtered_animals(&location);
            assert!(!result.contains("Cattle (Cows, Bulls)"));
        }

        #[test]
        fn test_combination_cattle_types() {
            let mut location = create_default_location();
            location.beef_cow_slaughter = "Yes".to_string();
            location.steer_slaughter = "Yes".to_string();
            location.heifer_slaughter = "Yes".to_string();
            let result = get_slaughtered_animals(&location);
            assert_eq!(result.matches("Cattle (Cows, Bulls)").count(), 1);
        }
    }

    mod get_processed_animals_tests {
        use super::*;

        #[test]
        fn test_empty_location_returns_na() {
            let location = create_default_location();
            let result = get_processed_animals(&location);
            assert_eq!(result, "N/A");
        }

        #[test]
        fn test_beef_processing_detection() {
            let mut location = create_default_location();
            location.beef_processing = "Yes".to_string();
            let result = get_processed_animals(&location);
            assert!(result.contains("Beef"));
        }

        #[test]
        fn test_pork_processing_detection() {
            let mut location = create_default_location();
            location.pork_processing = "Yes".to_string();
            let result = get_processed_animals(&location);
            assert!(result.contains("Pork"));
        }

        #[test]
        fn test_chicken_processing_detection() {
            let mut location = create_default_location();
            location.chicken_processing = "Yes".to_string();
            let result = get_processed_animals(&location);
            assert!(result.contains("Chicken"));
        }

        #[test]
        fn test_turkey_processing_detection() {
            let mut location = create_default_location();
            location.turkey_processing = "Yes".to_string();
            let result = get_processed_animals(&location);
            assert!(result.contains("Turkey"));
        }

        #[test]
        fn test_duck_processing_detection() {
            let mut location = create_default_location();
            location.duck_processing = "Yes".to_string();
            let result = get_processed_animals(&location);
            assert!(result.contains("Duck"));
        }

        #[test]
        fn test_rabbit_processing_detection() {
            let mut location = create_default_location();
            location.rabbit_processing = "Yes".to_string();
            let result = get_processed_animals(&location);
            assert!(result.contains("Rabbit"));
        }

        #[test]
        fn test_deer_processing_detection() {
            let mut location = create_default_location();
            location.deer_processing = "Yes".to_string();
            let result = get_processed_animals(&location);
            assert!(result.contains("Deer"));
        }

        #[test]
        fn test_goat_processing_detection() {
            let mut location = create_default_location();
            location.goat_processing = "Yes".to_string();
            let result = get_processed_animals(&location);
            assert!(result.contains("Goat"));
        }

        #[test]
        fn test_sheep_processing_detection() {
            let mut location = create_default_location();
            location.sheep_processing = "Yes".to_string();
            let result = get_processed_animals(&location);
            assert!(result.contains("Sheep"));
        }

        #[test]
        fn test_multiple_processed_animals() {
            let mut location = create_default_location();
            location.beef_processing = "Yes".to_string();
            location.pork_processing = "Yes".to_string();
            location.chicken_processing = "Yes".to_string();
            let result = get_processed_animals(&location);
            assert!(result.contains("Beef"));
            assert!(result.contains("Pork"));
            assert!(result.contains("Chicken"));
        }

        #[test]
        fn test_exotic_poultry_processing() {
            let mut location = create_default_location();
            location.exotic_poultry_processing = "Yes".to_string();
            let result = get_processed_animals(&location);
            assert!(result.contains("Exotic Poultry"));
        }

        #[test]
        fn test_ratite_processing() {
            let mut location = create_default_location();
            location.ratite_processing = "Yes".to_string();
            let result = get_processed_animals(&location);
            assert!(result.contains("Ratite (Ostrich/Emu)"));
        }

        #[test]
        fn test_no_processing_returns_na() {
            let mut location = create_default_location();
            location.beef_processing = "No".to_string();
            location.pork_processing = "No".to_string();
            let result = get_processed_animals(&location);
            assert_eq!(result, "N/A");
        }
    }

    mod get_tested_animals_tests {
        use super::*;

        #[test]
        fn test_all_zero_animals_returns_unknown() {
            let report = AphisReport {
                account_name: String::new(),
                customer_number_x: String::new(),
                certificate_number: String::new(),
                registration_type: String::new(),
                certificate_status: String::new(),
                status_date: String::new(),
                address_line_1: String::new(),
                address_line_2: String::new(),
                city_state_zip: String::new(),
                county: String::new(),
                customer_number_y: String::new(),
                year: String::new(),
                dogs: "0".to_string(),
                cats: "0".to_string(),
                guinea_pigs: "0".to_string(),
                hamsters: "0".to_string(),
                rabbits: "0".to_string(),
                non_human_primates: "0".to_string(),
                sheep: "0".to_string(),
                pigs: "0".to_string(),
                other_farm_animals: "0".to_string(),
                all_other_animals: "0".to_string(),
                latitude: 0.0,
                longitude: 0.0,
                animals_tested: None,
            };
            let result = get_tested_animals(&report);
            assert_eq!(result, "Unknown");
        }

        #[test]
        fn test_single_dog_count() {
            let report = AphisReport {
                account_name: String::new(),
                customer_number_x: String::new(),
                certificate_number: String::new(),
                registration_type: String::new(),
                certificate_status: String::new(),
                status_date: String::new(),
                address_line_1: String::new(),
                address_line_2: String::new(),
                city_state_zip: String::new(),
                county: String::new(),
                customer_number_y: String::new(),
                year: String::new(),
                dogs: "5".to_string(),
                cats: "0".to_string(),
                guinea_pigs: "0".to_string(),
                hamsters: "0".to_string(),
                rabbits: "0".to_string(),
                non_human_primates: "0".to_string(),
                sheep: "0".to_string(),
                pigs: "0".to_string(),
                other_farm_animals: "0".to_string(),
                all_other_animals: "0".to_string(),
                latitude: 0.0,
                longitude: 0.0,
                animals_tested: None,
            };
            let result = get_tested_animals(&report);
            assert!(result.contains("5 Dogs"));
        }

        #[test]
        fn test_multiple_animal_types() {
            let report = AphisReport {
                account_name: String::new(),
                customer_number_x: String::new(),
                certificate_number: String::new(),
                registration_type: String::new(),
                certificate_status: String::new(),
                status_date: String::new(),
                address_line_1: String::new(),
                address_line_2: String::new(),
                city_state_zip: String::new(),
                county: String::new(),
                customer_number_y: String::new(),
                year: String::new(),
                dogs: "10".to_string(),
                cats: "15".to_string(),
                guinea_pigs: "20".to_string(),
                hamsters: "0".to_string(),
                rabbits: "0".to_string(),
                non_human_primates: "0".to_string(),
                sheep: "0".to_string(),
                pigs: "0".to_string(),
                other_farm_animals: "0".to_string(),
                all_other_animals: "0".to_string(),
                latitude: 0.0,
                longitude: 0.0,
                animals_tested: None,
            };
            let result = get_tested_animals(&report);
            assert!(result.contains("10 Dogs"));
            assert!(result.contains("15 Cats"));
            assert!(result.contains("20 Guinea Pigs"));
        }

        #[test]
        fn test_primate_testing_detection() {
            let report = AphisReport {
                account_name: String::new(),
                customer_number_x: String::new(),
                certificate_number: String::new(),
                registration_type: String::new(),
                certificate_status: String::new(),
                status_date: String::new(),
                address_line_1: String::new(),
                address_line_2: String::new(),
                city_state_zip: String::new(),
                county: String::new(),
                customer_number_y: String::new(),
                year: String::new(),
                dogs: "0".to_string(),
                cats: "0".to_string(),
                guinea_pigs: "0".to_string(),
                hamsters: "0".to_string(),
                rabbits: "0".to_string(),
                non_human_primates: "3".to_string(),
                sheep: "0".to_string(),
                pigs: "0".to_string(),
                other_farm_animals: "0".to_string(),
                all_other_animals: "0".to_string(),
                latitude: 0.0,
                longitude: 0.0,
                animals_tested: None,
            };
            let result = get_tested_animals(&report);
            assert!(result.contains("3 Non-Human Primates"));
        }

        #[test]
        fn test_comma_separated_output() {
            let report = AphisReport {
                account_name: String::new(),
                customer_number_x: String::new(),
                certificate_number: String::new(),
                registration_type: String::new(),
                certificate_status: String::new(),
                status_date: String::new(),
                address_line_1: String::new(),
                address_line_2: String::new(),
                city_state_zip: String::new(),
                county: String::new(),
                customer_number_y: String::new(),
                year: String::new(),
                dogs: "1".to_string(),
                cats: "2".to_string(),
                guinea_pigs: "0".to_string(),
                hamsters: "0".to_string(),
                rabbits: "0".to_string(),
                non_human_primates: "0".to_string(),
                sheep: "0".to_string(),
                pigs: "0".to_string(),
                other_farm_animals: "0".to_string(),
                all_other_animals: "0".to_string(),
                latitude: 0.0,
                longitude: 0.0,
                animals_tested: None,
            };
            let result = get_tested_animals(&report);
            assert!(result.contains(", "));
        }

        #[test]
        fn test_invalid_number_format_ignored() {
            let report = AphisReport {
                account_name: String::new(),
                customer_number_x: String::new(),
                certificate_number: String::new(),
                registration_type: String::new(),
                certificate_status: String::new(),
                status_date: String::new(),
                address_line_1: String::new(),
                address_line_2: String::new(),
                city_state_zip: String::new(),
                county: String::new(),
                customer_number_y: String::new(),
                year: String::new(),
                dogs: "invalid".to_string(),
                cats: "0".to_string(),
                guinea_pigs: "0".to_string(),
                hamsters: "0".to_string(),
                rabbits: "0".to_string(),
                non_human_primates: "0".to_string(),
                sheep: "0".to_string(),
                pigs: "0".to_string(),
                other_farm_animals: "0".to_string(),
                all_other_animals: "0".to_string(),
                latitude: 0.0,
                longitude: 0.0,
                animals_tested: None,
            };
            let result = get_tested_animals(&report);
            assert_eq!(result, "Unknown");
        }

        #[test]
        fn test_float_counts_converted_to_integer() {
            let report = AphisReport {
                account_name: String::new(),
                customer_number_x: String::new(),
                certificate_number: String::new(),
                registration_type: String::new(),
                certificate_status: String::new(),
                status_date: String::new(),
                address_line_1: String::new(),
                address_line_2: String::new(),
                city_state_zip: String::new(),
                county: String::new(),
                customer_number_y: String::new(),
                year: String::new(),
                dogs: "5.9".to_string(),
                cats: "0".to_string(),
                guinea_pigs: "0".to_string(),
                hamsters: "0".to_string(),
                rabbits: "0".to_string(),
                non_human_primates: "0".to_string(),
                sheep: "0".to_string(),
                pigs: "0".to_string(),
                other_farm_animals: "0".to_string(),
                all_other_animals: "0".to_string(),
                latitude: 0.0,
                longitude: 0.0,
                animals_tested: None,
            };
            let result = get_tested_animals(&report);
            assert!(result.contains("5 Dogs"));
        }

        #[test]
        fn test_all_animal_types_maximum_counts() {
            let report = AphisReport {
                account_name: String::new(),
                customer_number_x: String::new(),
                certificate_number: String::new(),
                registration_type: String::new(),
                certificate_status: String::new(),
                status_date: String::new(),
                address_line_1: String::new(),
                address_line_2: String::new(),
                city_state_zip: String::new(),
                county: String::new(),
                customer_number_y: String::new(),
                year: String::new(),
                dogs: "100".to_string(),
                cats: "200".to_string(),
                guinea_pigs: "300".to_string(),
                hamsters: "400".to_string(),
                rabbits: "500".to_string(),
                non_human_primates: "600".to_string(),
                sheep: "700".to_string(),
                pigs: "800".to_string(),
                other_farm_animals: "900".to_string(),
                all_other_animals: "1000".to_string(),
                latitude: 0.0,
                longitude: 0.0,
                animals_tested: None,
            };
            let result = get_tested_animals(&report);
            assert!(result.contains("100 Dogs"));
            assert!(result.contains("200 Cats"));
            assert!(result.contains("300 Guinea Pigs"));
            assert!(result.contains("400 Hamsters"));
            assert!(result.contains("500 Rabbits"));
            assert!(result.contains("600 Non-Human Primates"));
            assert!(result.contains("700 Sheep"));
            assert!(result.contains("800 Pigs"));
            assert!(result.contains("900 Other Farm Animals"));
            assert!(result.contains("1000 All Other Animals"));
        }
    }

    mod location_struct_tests {
        use super::*;

        #[test]
        fn test_location_default_creation() {
            let location = Location::default();
            assert_eq!(location.establishment_id, "");
            assert_eq!(location.establishment_name, "");
            assert_eq!(location.city, "");
            assert_eq!(location.state, "");
        }

        #[test]
        fn test_location_creation_with_values() {
            let mut location = Location::default();
            location.establishment_id = "12345".to_string();
            location.establishment_name = "Test Facility".to_string();
            location.city = "Test City".to_string();
            location.state = "TS".to_string();
            
            assert_eq!(location.establishment_id, "12345");
            assert_eq!(location.establishment_name, "Test Facility");
            assert_eq!(location.city, "Test City");
            assert_eq!(location.state, "TS");
        }

        #[test]
        fn test_location_coordinates() {
            let mut location = Location::default();
            location.latitude = 40.7128;
            location.longitude = -74.0060;
            
            assert_eq!(location.latitude, 40.7128);
            assert_eq!(location.longitude, -74.0060);
        }
    }

    mod aphis_report_struct_tests {
        use super::*;

        #[test]
        fn test_aphis_report_creation() {
            let report = AphisReport {
                account_name: "Test Lab".to_string(),
                customer_number_x: "123".to_string(),
                certificate_number: "ABC123".to_string(),
                registration_type: "Research".to_string(),
                certificate_status: "Active".to_string(),
                status_date: "2024-01-01".to_string(),
                address_line_1: "123 Test St".to_string(),
                address_line_2: "Suite 100".to_string(),
                city_state_zip: "Test City, TS 12345".to_string(),
                county: "Test County".to_string(),
                customer_number_y: "456".to_string(),
                year: "2024".to_string(),
                dogs: "10".to_string(),
                cats: "5".to_string(),
                guinea_pigs: "20".to_string(),
                hamsters: "15".to_string(),
                rabbits: "8".to_string(),
                non_human_primates: "3".to_string(),
                sheep: "2".to_string(),
                pigs: "1".to_string(),
                other_farm_animals: "0".to_string(),
                all_other_animals: "0".to_string(),
                latitude: 40.0,
                longitude: -75.0,
                animals_tested: None,
            };
            
            assert_eq!(report.account_name, "Test Lab");
            assert_eq!(report.certificate_number, "ABC123");
            assert_eq!(report.dogs, "10");
        }
    }

    mod inspection_report_struct_tests {
        use super::*;

        #[test]
        fn test_inspection_report_creation() {
            let report = InspectionReport {
                account_name: "Test Facility".to_string(),
                customer_number: "123".to_string(),
                certificate_number: "ABC123".to_string(),
                license_type: "Type A".to_string(),
                certificate_status: "Active".to_string(),
                status_date: "2024-01-01".to_string(),
                address_line_1: "123 Test St".to_string(),
                address_line_2: "Suite 100".to_string(),
                city_state_zip: "Test City, TS 12345".to_string(),
                county: "Test County".to_string(),
                city: "Test City".to_string(),
                state: "TS".to_string(),
                zip: "12345".to_string(),
                latitude: 40.0,
                longitude: -75.0,
            };
            
            assert_eq!(report.account_name, "Test Facility");
            assert_eq!(report.certificate_number, "ABC123");
            assert_eq!(report.city, "Test City");
            assert_eq!(report.latitude, 40.0);
        }
    }
}
