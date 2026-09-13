use std::io;

use serde::{Deserialize, Serialize};

use uec_api::Location;

#[derive(Debug, Serialize, Deserialize, PartialEq)]
struct Document(Vec<Row>);

#[derive(Debug, Serialize, Deserialize, PartialEq)]
struct Row {
    navnelbnr: usize,
    cvrnr: String,
    pnr: String,
    // region: (),
    #[serde(rename = "brancheKode")]
    industry_code: String,
    #[serde(rename = "branche")]
    industry: String,
    #[serde(rename = "virksomhedstype")]
    company_type: String,
    #[serde(rename = "navn1")]
    name: String,
    #[serde(rename = "adresse1")]
    address: String,
    #[serde(rename = "postnr")]
    zip: usize,
    #[serde(rename = "By")]
    city: String,
    // <seneste_kontrol>1</seneste_kontrol>
    // <seneste_kontrol_dato>27-11-2024 00:00:00</seneste_kontrol_dato>
    // <naestseneste_kontrol>1</naestseneste_kontrol>
    // <naestseneste_kontrol_dato>01-11-2023 00:00:00</naestseneste_kontrol_dato>
    // <tredjeseneste_kontrol>1</tredjeseneste_kontrol>
    // <tredjeseneste_kontrol_dato>02-11-2022 00:00:00</tredjeseneste_kontrol_dato>
    // <fjerdeseneste_kontrol>1</fjerdeseneste_kontrol>
    // <fjerdeseneste_kontrol_dato>09-08-2022 00:00:00</fjerdeseneste_kontrol_dato>
    // <URL>http://www.findsmiley.dk/da-DK/Searching/DetailsView.htm?virk=921228</URL>
    // <reklame_beskyttelse>0</reklame_beskyttelse>
    // <Elite_Smiley>0</Elite_Smiley>
    // <Kaedenavn></Kaedenavn>
    #[serde(rename = "Geo_Lng")]
    lng: String,
    #[serde(rename = "Geo_Lat")]
    lat: String,
    // <Pixibranche>Fiske- og vildtforretninger, fiskeafdelinger</Pixibranche>
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let stdin = io::stdin();
    let doc: Document = serde_xml_rs::from_reader(stdin).unwrap();
    // for row in doc.0 {
    //     println!("{} {}", row.branche, row.branche_kode);
    // }
    // return Ok(());
    let locs: Vec<_> = doc
        .0
        .into_iter()
        .filter(|row| {
            row.industry
                .to_lowercase()
                .starts_with("fremstilling af animalske produkter")
                || row.industry.to_lowercase().contains("slagter")
        })
        .enumerate()
        .map(|(i, row)| Location {
            county: "Denmark".to_string(),
            establishment_id: i.to_string(),
            establishment_name: row.name,
            city: row.city,
            street: row.address,
            zip: row.zip.to_string(),
            activities: match &row.industry[..] {
                "Fremstilling af animalske produkter - Fisk og muslinger m.v."
                | "Fremstilling af animalske produkter - Kød"
                | "Slagterier"
                | "Specialforretning - Slagter m.v."
                | "Virksomhed, foreløbig AUT: Slagteri, slagteri med fremstilli"
                | "Virksomhed, foreløbig: Slagter, slagterafdeling" => {
                    "Meat Processing; Meat Slaughter"
                }
                "Fremstilling af animalske produkter - Andre produkter"
                | "Fremstilling af animalske produkter - Mælk og ost"
                | "Fremstilling af animalske produkter - Æg" => "Meat Processing",
                b => todo!("{b:?}"),
            }
            .to_string(),
            latitude: row.lat.parse().unwrap_or(0.0),
            longitude: row.lng.parse().unwrap_or(0.0),
            ..Default::default()
        })
        .collect();

    let mut wtr = csv::Writer::from_writer(io::stdout());

    for loc in locs {
        wtr.serialize(loc).unwrap();
    }

    Ok(())
}
