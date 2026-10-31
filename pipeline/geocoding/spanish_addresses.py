"""Deterministic Spanish address formatting; no fuzzy names or number guessing."""
from __future__ import annotations

import re
import unicodedata

from pipeline.sources.spain_rgseaa.location_enrichment import official_province_key

RULESET = "spanish-address-format-v7"
HOUSE = r"[0-9]+(?:[ -]?[a-z])?(?:\s*[-/]\s*[0-9]+[a-z]?)?"
UNIT = r"(?:nave|nau|local|piso|planta|puerta|baixos|bajo|bajos|edificio|edifici|bloque)"
ROAD_TYPES = frozenset({"street", "avenue", "road", "path", "promenade", "square"})
# An unfamiliar/ambiguous road or estate abbreviation is not an omitted type.
EXPLICIT_PREFIXES = ROAD_TYPES | frozenset({
    "cr", "cm", "ps", "pz", "tr", "pj", "pg", "pol", "poligono", "poligon",
    "pasaje", "travesia", "ronda", "rambla", "urbanizacion", "urb", "plg",
    "lugar", "lg", "barrio", "bo", "poblado", "pb", "rua", "estrada", "ct",
    "glorieta", "gta", "rot", "rotonda", "prolongacion", "prol", "via", "vial",
    "vr", "partida", "pra", "praza", "pza",
    "calle", "carrer", "cl", "c", "avenida", "avinguda", "avda", "av", "carretera", "ctra",
    "camino", "cami", "paseo", "passeig", "plaza", "placa", "pl",
    "nave", "nau", "local", "piso", "planta", "puerta", "baixos", "bajo", "bajos",
    "edificio", "edifici", "bloque", "parcela", "parc", "plot", "km", "kilometro", "kilometros",
})


def _postal_spaces(value: str) -> str:
    return value.translate({0xA0: " ", 0x202F: " ", 0x2007: " "})

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
    typed = re.sub(r"^(calle|carrer|cl|c) ", "street ",
        re.sub(r"^(avenida|avinguda|avda|av) ", "avenue ",
        re.sub(r"^(carretera|ctra) ", "road ",
        re.sub(r"^(camino|cami) ", "path ",
        re.sub(r"^(paseo|passeig|pg) ", "promenade ",
        re.sub(r"^(plaza|placa|pl) ", "square ", normalized))))))
    # Normalize only the linking preposition immediately after a typed road.
    # Preserve articles, words inside the name, initials and road-type conflicts.
    return re.sub(r"^(street|avenue|road|path|promenade|square) de ", r"\1 ", typed)


def house_key(value: object) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return ""
    raw = _postal_spaces(str(value)).strip().casefold()
    if re.fullmatch(HOUSE, raw) is None:
        return ""
    raw = re.sub(r"\s+", "", raw)
    return re.sub(r"(?<=[0-9])-(?=[a-z]$)", "", raw)


def address_parts(source: str) -> set[tuple[str, str]]:
    """Parse number-first/last, including a comma before the house number."""
    if not isinstance(source, str) or not source.strip() or len(source) > 1200:
        return set()
    fragments = [part.strip().casefold() for part in re.split(r"[,;]", _postal_spaces(source)) if part.strip()]
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
    found.update(_explicit_number_parts(source))
    return found


def _explicit_number_parts(source: str) -> set[tuple[str, str]]:
    """Read explicit house markers before labeled estate/building details.

    Keep numeric plots, kilometres, unlabelled tails and conflicting roads out.
    The complete source remains unchanged; this returns comparison keys only.
    """
    if re.search(r"\b(?:s\s*[/.-]\s*n|sin\s+n[uú]mero)\b", source, re.I):
        return set()
    fragments = [p.strip() for p in re.split(r"[,;]", _postal_spaces(source)) if p.strip()]
    candidates = fragments + [a+" "+b for a,b in zip(fragments,fragments[1:])]
    descriptors = (r"(?:p\.?\s*i\.?\b|pol\.?\b|pol[ií]gono\b|pol[ií]gon\b|"+
                   UNIT+r"\b|bj\b|[0-9]+[ºª°]\s*(?:piso|planta)\b)")
    found = set()
    for part in candidates:
        match = re.fullmatch(r"(.+?)\s+(?:n[º°o]\s*|n[uú]m(?:ero)?\.?\s*:?\s*)("+
                             HOUSE+r")(\s+"+descriptors+r".*)?", part, re.I)
        if not match:
            continue
        road, house, tail = match.groups()
        if re.search(r"(?:n[º°o]|n[uú]m(?:ero)?\.?)\s*:?\s*[0-9]|[0-9]+[ºª°]\s*(?:piso|planta)\b", road, re.I):
            continue  # A later unit/floor number must not become the house.
        key = road_key(road)
        if key.partition(" ")[0] in EXPLICIT_PREFIXES and key.partition(" ")[0] not in ROAD_TYPES:
            continue
        if re.match(r"^p\.?\s*i\b", road, re.I):
            continue
        if tail and re.search(r"\b(?:calle|carrer|cl|avenida|avinguda|avda|av|carretera|ctra|camino|cami|paseo|passeig|plaza|placa)\b|c/", tail, re.I):
            continue
        if key and house_key(house):
            found.add((key, house_key(house)))
    return found


def road_keys_match(source_key: str, returned_key: str) -> bool:
    if source_key == returned_key:
        return bool(source_key)
    prefix, _, name = returned_key.partition(" ")
    return (prefix in ROAD_TYPES and bool(name) and source_key == name
            and source_key.partition(" ")[0] not in EXPLICIT_PREFIXES)


def street_matches(source: str, road: object, house: object) -> bool:
    wanted_road, wanted_house = road_key(road), house_key(house)
    return bool(wanted_road and wanted_house and any(
        number == wanted_house and road_keys_match(source_road, wanted_road)
        for source_road, number in address_parts(source)))


def provider_address(source: str) -> str:
    """Strip unit/estate clutter only when one typed numbered road is explicit.

    Keep the original structured query in storage. This changes only the text
    sent to the provider; two different roads never produce an arbitrary choice.
    """
    components = structured_components(source)
    if components is None:
        return source
    street, house = components
    return f"{street} {house}"


def input_kind(source: object) -> str:
    """Classify request structure for diagnostics, never publication eligibility."""
    if not isinstance(source, str) or not source.strip():
        return "empty"
    folded = text(source)
    if re.search(r"\b(?:s\s*[/.-]\s*n|sin\s+n[uú]mero)\b", source, re.I):
        return "explicit_no_number"
    if re.search(r"\b(?:km|kilometro|kilometros)\b", folded):
        return "road_distance"
    if re.search(r"\b(?:poligono|poligon|industrial|parcela|pgno)\b", folded):
        return "estate_or_plot"
    if re.search(rf"\b{UNIT}\b", folded):
        return "building_unit"
    pairs = address_parts(source)
    if len(pairs) > 1:
        return "multiple_numbered_fragments"
    if len(pairs) == 1:
        road, house = next(iter(pairs))
        explicit_type = re.match(r"^(?:calle|carrer|avenida|avinguda|carretera|camino|cami|paseo|passeig|plaza|placa|c|cl|avda|av|ctra) ", folded)
        if (explicit_type and road.partition(" ")[0] in {"street", "avenue", "road", "path", "promenade", "square"}
                and re.fullmatch(r"[0-9]+[a-z]?", house) and int(re.match(r"[0-9]+", house)[0]) > 0):
            return "simple_numbered_road"
        return "other_numbered_address"
    return "unparsed_or_unnumbered"


def structured_components(source: object) -> tuple[str, str] | None:
    """Use one explicit typed road; do not turn plots or kilometres into houses."""
    if input_kind(source) in {"empty", "explicit_no_number", "road_distance"}:
        return None
    types = {"street": "calle", "avenue": "avenida", "road": "carretera",
             "path": "camino", "promenade": "paseo", "square": "plaza"}
    pairs = {(road, house) for road, house in address_parts(source)
             if road.partition(" ")[0] in types}
    if len(pairs) != 1:
        return None
    road, house = next(iter(pairs))
    prefix, _, name = road.partition(" ")
    if int(re.match(r"[0-9]+", house)[0]) == 0:
        return None
    # PG can mean either poligono or passeig; require the full road type here.
    if prefix == "promenade" and re.search(r"(?:^|[,;])\s*pg\.?\s", source, re.I):
        return None
    return f"{types[prefix]} {name}", house


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
    return {"alacant": "alacantalicante", "castello": "castellocastellon",
            "comunidaddemadrid": "madrid", "principadodeasturias": "asturias",
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
