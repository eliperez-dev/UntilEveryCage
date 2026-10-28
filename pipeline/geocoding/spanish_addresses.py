"""Deterministic Spanish address formatting; no fuzzy names or number guessing."""
from __future__ import annotations

import re
import unicodedata

from pipeline.sources.spain_rgseaa.location_enrichment import official_province_key

RULESET = "spanish-address-format-v2"
HOUSE = r"[0-9]+(?:[ -]?[a-z])?(?:\s*[-/]\s*[0-9]+[a-z]?)?"
UNIT = r"(?:nave|nau|local|piso|planta|puerta|baixos|bajo|bajos|edificio|edifici|bloque)"

# Province membership verified against the retained IGN 2026 PROVINCIAS.csv.
# Region spellings include the provider's Spanish/English names and ISO codes.
# A broader region can corroborate a province; it cannot override a conflicting
# explicit province. Street, house number, locality and any postcode still match.
REGIONS = (
    (("andalucia", "andalusia", "AN"), "almeria cadiz cordoba granada huelva jaen malaga sevilla"),
    (("aragon", "AR"), "huesca teruel zaragoza"),
    (("canarias", "canary islands", "CN"), "laspalmas santacruzdetenerife"),
    (("cantabria", "CB"), "cantabria"),
    (("castilla la mancha", "castile la mancha", "CM"), "albacete ciudadreal cuenca guadalajara toledo"),
    (("castilla y leon", "castile and leon", "CL"), "avila burgos leon palencia salamanca segovia soria valladolid zamora"),
    (("cataluna", "catalunya", "cataluna catalunya", "catalonia", "CT"), "barcelona gerona lerida tarragona"),
    (("ciudad autonoma de ceuta", "ceuta", "CE"), "ceuta"),
    (("ciudad autonoma de melilla", "melilla", "ML"), "melilla"),
    (("comunidad de madrid", "community of madrid", "madrid", "MD"), "madrid"),
    (("comunidad foral de navarra", "navarra", "navarre", "NC"), "comunidadforaldenavarra"),
    (("comunitat valenciana", "comunidad valenciana", "valencian community", "VC"), "alacantalicante castellocastellon valencia"),
    (("extremadura", "EX"), "badajoz caceres"),
    (("galicia", "GA"), "acoruna lugo orense pontevedra"),
    (("illes balears", "islas baleares", "balearic islands", "IB"), "baleares"),
    (("la rioja", "RI"), "larioja"),
    (("pais vasco", "euskadi", "pais vasco euskadi", "basque country", "PV"), "alava gipuzkoa bizkaia"),
    (("principado de asturias", "asturias", "AS"), "asturias"),
    (("region de murcia", "murcia", "MC"), "murcia"),
)


def text(value: object) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return ""
    folded = unicodedata.normalize("NFKD", str(value).casefold())
    return " ".join(
        re.sub(r"[^a-z0-9]+", " ", "".join(c for c in folded if not unicodedata.combining(c))).split())


def road_key(value: object) -> str:
    normalized = text(value)
    return re.sub(r"^(calle|carrer|cl|c) ", "street ",
        re.sub(r"^(avenida|avinguda|avda|av) ", "avenue ",
        re.sub(r"^(carretera|ctra) ", "road ",
        re.sub(r"^(camino|cami) ", "path ",
        re.sub(r"^(paseo|passeig|pg) ", "promenade ",
        re.sub(r"^(plaza|placa|pl) ", "square ", normalized))))))


def house_key(value: object) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return ""
    raw = str(value).strip().casefold()
    if re.fullmatch(HOUSE, raw) is None:
        return ""
    raw = re.sub(r"\s+", "", raw)
    return re.sub(r"(?<=[0-9])-(?=[a-z]$)", "", raw)


def address_parts(source: str) -> set[tuple[str, str]]:
    """Parse number-first/last, including a comma before the house number."""
    if not isinstance(source, str) or not source.strip() or len(source) > 1200:
        return set()
    fragments = [part.strip().casefold() for part in re.split(r"[,;]", source) if part.strip()]
    candidates = fragments + [f"{left} {right}" for left, right in zip(fragments, fragments[1:])]
    found = set()
    for part in candidates:
        # Drop only explicitly labeled sub-building units, never another street.
        part = re.sub(rf"\s+{UNIT}\b(?!.*\b(?:calle|carrer|avenida|avinguda|carretera)\b).*$", "", part)
        match = re.fullmatch(rf"(.+?)\s+(?:n[úu]m(?:ero)?\.?\s*|n[ºo°]\s*)?({HOUSE})", part)
        if match:
            road, house = match.groups()
        else:
            match = re.fullmatch(rf"({HOUSE})\s+(.+)", part)
            if not match:
                continue
            house, road = match.groups()
        road, house = road_key(road), house_key(house)
        if road and house:
            found.add((road, house))
    return found


def street_matches(source: str, road: object, house: object) -> bool:
    pair = (road_key(road), house_key(house))
    return bool(all(pair) and pair in address_parts(source))


def provider_address(source: str) -> str:
    """Strip unit/estate clutter only when one typed numbered road is explicit.

    Keep the original structured query in storage. This changes only the text
    sent to the provider; two different roads never produce an arbitrary choice.
    """
    road_types = {"street": "calle", "avenue": "avenida", "road": "carretera",
                  "path": "camino", "promenade": "paseo", "square": "plaza"}
    numbered = {(road, house) for road, house in address_parts(source)
                if road.partition(" ")[0] in road_types}
    if len(numbered) != 1:
        return source
    road, house = next(iter(numbered))
    prefix, _, name = road.partition(" ")
    return f"{road_types[prefix]} {name} {house}"


def locality_key(value: object) -> str:
    if not isinstance(value, str):
        return ""
    # Published Spanish/Catalan names sometimes put the article last.
    match = re.fullmatch(r"(.+?)(?:,\s*|\s*\(\s*)(el|la|los|las|els|les|l')\s*\)?", value.strip(), re.I)
    return text(f"{match[2]} {match[1]}" if match else value)


def province_key(value: object) -> str:
    if not isinstance(value, str):
        return ""
    key = official_province_key(re.sub(r"^provincia\s+de\s+", "", value.strip(), flags=re.I))
    return {"comunidaddemadrid": "madrid", "principadodeasturias": "asturias",
            "regiondemurcia": "murcia"}.get(key, key)


def province_matches(address: dict, region: str | None, source_postcode: str | None) -> bool:
    if not region:
        return True
    region_sets = {text(alias): frozenset(provinces.split())
                   for aliases, provinces in REGIONS for alias in aliases}
    wanted = region_sets.get(text(region), frozenset({province_key(region)}))
    states = [region_sets[text(address.get(k))] for k in ("state", "state_code")
              if text(address.get(k)) in region_sets]
    if states and any(wanted.isdisjoint(provinces) for provinces in states):
        return False
    if address.get("province"):
        return province_key(address["province"]) in wanted
    if any(province_key(address.get(k)) in wanted for k in ("state", "state_code", "county", "state_district")):
        return True
    # A postcode never overrides missing or contradictory administrative evidence.
    return bool(states)
