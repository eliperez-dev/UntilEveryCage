"""Conservative offline matching for German street and house-number text."""

import re
import unicodedata


_HOUSE_FIRST = re.compile(r"^(\S+)\s+(.+)$")
_HOUSE_LAST = re.compile(r"^(.+?)\s+(\S+)$")
_TERMINAL_SUFFIX = re.compile(r"\s*(straße|strasse|str\.?)$", re.IGNORECASE)


def _text_key(value: str) -> str:
    # Compatibility normalization and case folding retain umlaut distinctions;
    # casefold intentionally makes ß and ss equivalent.
    return unicodedata.normalize("NFKC", value).casefold()


def _street_key(value: str) -> str | None:
    value = _text_key(value.strip())
    match = _TERMINAL_SUFFIX.search(value)
    if not match:
        return None
    stem = value[:match.start()].strip()
    if not stem:
        return None
    stem = stem.translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue"}))
    return re.sub(r"\s+", " ", stem) + "|strasse"


def _split_address(value: str) -> tuple[str, str] | None:
    value = unicodedata.normalize("NFKC", value).strip()
    if not value:
        return None
    first = _HOUSE_FIRST.fullmatch(value)
    if first and re.fullmatch(r"\d+[\w/-]*", first.group(1), re.UNICODE):
        return first.group(2), first.group(1)
    last = _HOUSE_LAST.fullmatch(value)
    if last and re.fullmatch(r"\d+[\w/-]*", last.group(2), re.UNICODE):
        return last.group(1), last.group(2)
    return None


def street_matches(source_street: str, road: str, house_number: str) -> bool:
    """Return whether a source address and provider road/number match exactly.

    This is candidate recovery for offline review, not geocoding acceptance.
    Only terminal German Straße/Strasse/Str/Str. spellings are canonicalized.
    """
    if not all(isinstance(value, str) and value.strip()
               for value in (source_street, road, house_number)):
        return False
    parsed = _split_address(source_street)
    if parsed is None:
        return False
    source_road, source_number = parsed
    return (_text_key(source_number) == _text_key(house_number.strip())
            and _street_key(source_road) is not None
            and _street_key(source_road) == _street_key(road))
