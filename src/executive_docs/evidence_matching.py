"""Conservative formatting equivalence for PDF-backed draft values.

These helpers establish text presence, not the meaning, role, or truth of a
claim. In particular, execution/organization context still needs its own guard.
No fuzzy spelling, number correction, entity aliasing, or unit conversion is
performed here.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator


_DISTRICT = re.compile(r"(?<!\w)(?:р\s*[-–‑]\s*(?:он|н)|район)(?!\w)")
_QUOTE_PAIRS = (
    re.compile(r"«([^«»]*)»"),
    re.compile(r"„([^„“]*)“"),
    re.compile(r"“([^“”]*)”"),
    re.compile(r"‘([^‘’]*)’"),
    # A quote immediately following a digit can denote inches/feet. Do not
    # reinterpret it as an opening typographic quote.
    re.compile(r'(?<!\d)"([^\"]*)"(?!\w)'),
    re.compile(r"(?<!\w)'([^']*)'(?!\w)"),
)
_WORD = re.compile(r"\w")
_CODE_JOINERS = "-/×*+"
_NUMBER_JOINERS = ".,:"
_ADDRESS_ABBREVIATION = re.compile(
    r"(?<!\w)(г|д|ул|уч|стр|корп|пом|кв|пос|пер|просп|пл)\.\s*(?=\d|[а-яa-z]{2})"
)


def normalize_evidence_text(text: str) -> str:
    """Normalize only explicit, non-factual Russian text formatting variants.

    Numeric punctuation is intentionally retained: ``12,5``, ``12.5`` and
    ``125`` remain distinct, as do dates, dimensions and project identifiers.
    """
    value = unicodedata.normalize("NFC", text).casefold().replace("ё", "е")
    for pair in _QUOTE_PAIRS:
        value = pair.sub(
            lambda match: (
                " " + match.group(1) + " "
                if any(char.isalpha() for char in match.group(1))
                else match.group(0)
            ),
            value,
        )
    value = _DISTRICT.sub("район", value)
    # Address captions may touch the next token in a PDF text layer. This only
    # inserts a separator after a known caption, never inside a number/code.
    value = _ADDRESS_ABBREVIATION.sub(r"\1. ", value)

    def prose_separator(match: re.Match[str]) -> str:
        left = value[: match.start()].rstrip()
        right = value[match.end() :].lstrip()
        # Preserve even spaced numeric punctuation rather than guessing
        # whether it represents a decimal, a list or an identifier.
        if left and right and left[-1].isdigit() and right[0].isdigit():
            return match.group(0)
        return " "

    value = re.sub(r"[,;]", prose_separator, value)
    return re.sub(r"\s+", " ", value).strip()


def iter_evidence_spans(
    value: str, fragment: str, *, require_entity_boundaries: bool = False,
) -> Iterator[tuple[int, int]]:
    """Yield matches in normalized text, optionally preserving entity names.

    Pass the original fragment, not already normalized text: closing quotation
    marks establish the full legal-entity name before formatting is normalized.
    """
    needle = normalize_evidence_text(value)
    haystack = normalize_evidence_text(fragment)
    if not needle:
        return
    protected_entities = (
        list(_legal_entity_spans(fragment, haystack))
        if require_entity_boundaries and _LEGAL_FORM.search(needle)
        else []
    )
    for match in re.finditer(re.escape(needle), haystack):
        start, end = match.span()
        before, after = haystack[:start], haystack[end:]
        if _WORD.match(needle[0]) and before:
            if needle[0].isdigit() and before[-1] in "+-−":
                continue
            if _WORD.match(before[-1]):
                continue
            if len(before) >= 2 and _WORD.match(before[-2]):
                if before[-1] in _CODE_JOINERS:
                    continue
                if needle[0].isdigit() and before[-2].isdigit() and before[-1] in _NUMBER_JOINERS:
                    continue
        if _WORD.match(needle[-1]) and after:
            if needle[-1].isdigit() and after[0] in "\"'′″%°":
                continue
            if _WORD.match(after[0]):
                continue
            if len(after) >= 2 and _WORD.match(after[1]):
                if after[0] in _CODE_JOINERS:
                    continue
                if needle[-1].isdigit() and after[1].isdigit() and after[0] in _NUMBER_JOINERS:
                    continue
        if any(
            start < entity_end and end > entity_start
            and not (start <= entity_start and end >= entity_end)
            for entity_start, entity_end in protected_entities
        ):
            continue
        yield start, end


def text_value_is_present(value: str, fragment: str) -> bool:
    """Find a formatting-equivalent value without partial word/code matches."""
    return next(iter_evidence_spans(value, fragment), None) is not None


def title_value_is_present(value: str, fragment: str) -> bool:
    """Permit one restored closing prose parenthesis in a long project title.

    PDF titles sometimes leave their descriptive aside unclosed. This does not
    normalize identifiers, numeric punctuation, words or interior parentheses.
    Only the object/title field validator may use this formatting exception.
    """
    if text_value_is_present(value, fragment):
        return True
    title = value.strip()
    if (len(title) < 80 or not title.endswith(")")
        or title.count("(") != title.count(")")
        or not re.search(r"\([а-яА-Яa-zA-Z]", title)):
        return False
    return text_value_is_present(title[:-1].rstrip(), fragment)


_MATERIAL_QUANTITY = re.compile(
    r"(?P<number>[+\-]?(?:0|[1-9][0-9]*)(?:[.,][0-9]+)?)\s*"
    r"(?P<unit>компл\.?|шт\.?|км|мм|см|м[23²³]?|кг|г|т|л)"
)


def material_quantity_is_present(value: str, fragment: str) -> bool:
    """Match one material-row quantity when unit/quantity columns are reversed.

    The exact quantity and unit must belong to a single cited item. A trailing
    mass column is allowed, without splitting digits glued by PDF extraction.
    This is not generic word reordering, arithmetic, unit conversion,
    or proof that independently quoted cells belong to the same material row.
    The caller must retain its name/page/shared-row checks.
    """
    raw_value = unicodedata.normalize("NFC", value).casefold().strip()
    quantity = _MATERIAL_QUANTITY.fullmatch(raw_value)
    if quantity is None:
        return False
    number = re.escape(quantity.group("number"))
    unit = re.escape(quantity.group("unit").rstrip("."))
    if quantity.group("unit").rstrip(".") in {"шт", "компл"}:
        unit += r"\.?"
    # Preserve digits, signs and decimal punctuation verbatim. The material
    # column must not accidentally supply a dimension or part of a type code.
    before_number = r"(?<![\w.,/×*+\-−])"
    # A real specification often has mass after quantity. Requiring quantity
    # to end the quote discarded otherwise fully evidenced rows. Only a
    # separated numeric mass column or explicitly labelled mass is permitted;
    # another material/dimension/unit sequence is not a row continuation.
    mass = r"(?:масса(?:\s+(?:единицы|ед\.?|изделия))?\s*[:=]?\s*)?\d+(?:[.,]\d+)?(?:\s*кг)?"
    tail = rf"(?:\s*[;|]\s*{mass}|\s+{mass})?\s*[.;]?\s*$"
    forward = before_number + number + r"\s*" + unit + tail
    reverse = r"(?<![\w/·⋅∙×*÷∕⁄^+\-−–—])" + unit + r"\s+" + number + tail
    source = unicodedata.normalize("NFC", fragment).casefold()
    for pattern in (forward, reverse):
        for match in re.finditer(pattern, source):
            preceding = source[:match.start()].rstrip()
            if re.search(r"масса[^;|\n]{0,45}$", preceding):
                continue
            # Whitespace must not hide a negative sign or a composite unit,
            # e.g. "− 5 м", "кг / м 5" or "Н · м 5".
            if preceding and preceding[-1] in "/·⋅∙×*÷∕⁄^+-−–—":
                continue
            if preceding and preceding[-1] in ".,":
                before_separator = preceding[:-1].rstrip()
                if before_separator and before_separator[-1].isdigit():
                    continue
            return True
    return False


_LEGAL_FORM = re.compile(r"(?<!\w)(?:ооо|пао|оао|зао|нао|ао)(?!\w)")
_CLOSING_ENTITY_QUOTES = {"«": "»", "„": "“", "“": "”", '"': '"', "'": "'", "‘": "’"}
_PLAIN_ENTITY_END = re.compile(
    r"[;,\n:]|\.(?:\s|$)|\s+[—–]\s+|"
    r"\s+(?:инн|огрнип|огрн|кпп|бик|адрес|юридический|телефон|"
    r"заказчик|подрядчик|проектировщик|проектная\s+организация)\b"
)


def _legal_entity_spans(fragment: str, normalized: str) -> Iterator[tuple[int, int]]:
    """Locate complete legal-form/name spans before quote stripping.

    Unquoted entity names have no definitive closing marker, so their name
    conservatively extends to a documentary field/separator or fragment end.
    This avoids treating the first word of a longer name as another company.
    """
    original = unicodedata.normalize("NFC", fragment).casefold().replace("ё", "е")
    for form in _LEGAL_FORM.finditer(original):
        name_start = form.end()
        while name_start < len(original) and original[name_start].isspace():
            name_start += 1
        if name_start == len(original):
            continue
        opening = original[name_start]
        if opening in _CLOSING_ENTITY_QUOTES:
            closing = original.find(_CLOSING_ENTITY_QUOTES[opening], name_start + 1)
            entity_end = closing + 1 if closing >= 0 else len(original)
        else:
            closing = _PLAIN_ENTITY_END.search(original, name_start)
            entity_end = closing.start() if closing else len(original)
        entity = normalize_evidence_text(original[form.start() : entity_end])
        prefix_length = len(normalize_evidence_text(original[: form.start()]))
        start = normalized.find(entity, prefix_length)
        if entity and start >= 0:
            yield start, start + len(entity)


def entity_value_is_present(value: str, fragment: str) -> bool:
    """Match a role-bound subject without borrowing a longer company's name."""
    return next(iter_evidence_spans(value, fragment, require_entity_boundaries=True), None) is not None


_HORIZONTAL_DIGITS = r"[0-9](?:[0-9 \t\u00a0]*[0-9])?"
_IDENTIFIER_LABELS = (
    ("ИНН", r"инн", (10, 12)),
    ("ОГРНИП", r"огрнип", (15,)),
    ("ОГРН", r"огрн", (13,)),
    ("КПП", r"кпп", (9,)),
    ("БИК", r"бик", (9,)),
    ("р/с", r"р\s*/\s*с|расчетн(?:ый|ого)\s+счет(?:а)?", (20,)),
    ("к/с", r"к\s*/\s*с|корреспондентск(?:ий|ого)\s+счет(?:а)?", (20,)),
)
_LABEL_SEPARATOR = r"(?![а-яa-z_])\s*(?:[№:#=]\s*)?"
_COMBINED_INN_KPP = re.compile(
    rf"(?<!\w)инн\s*/\s*кпп{_LABEL_SEPARATOR}"
    rf"(?P<inn>{_HORIZONTAL_DIGITS})\s*/\s*(?P<kpp>{_HORIZONTAL_DIGITS})"
)


def _identifier_error(label: str, number: str, lengths: tuple[int, ...]) -> str | None:
    digits = re.sub(r"[ \t\u00a0]", "", number)
    if len(digits) not in lengths:
        expected = " или ".join(str(length) for length in lengths)
        return f"{label}: найдено {len(digits)} цифр, требуется {expected}; сверьте с PDF."
    return None


def validate_numeric_identifiers(text: str) -> str | None:
    """Reject malformed lengths of explicitly labelled legal/bank identifiers.

    This is a transcription sanity check, not a registry lookup or a checksum
    assertion. Bare numbers and absent identifiers are not invented or inferred.
    A valid length does not establish that an identifier belongs to an entity.
    """
    value = unicodedata.normalize("NFC", text).casefold().replace("ё", "е")
    combined_spans = []
    for match in _COMBINED_INN_KPP.finditer(value):
        combined_spans.append(match.span())
        if re.match(r"[.,/+\-][0-9]+|[а-яa-z]\w*", value[match.end() :]):
            return "КПП: недопустимый формат числового реквизита; сверьте с PDF."
        for label, group, lengths in (("ИНН", "inn", (10, 12)), ("КПП", "kpp", (9,))):
            error = _identifier_error(label, match.group(group), lengths)
            if error:
                return error
    for label, pattern, lengths in _IDENTIFIER_LABELS:
        expression = re.compile(
            rf"(?<!\w)(?:{pattern}){_LABEL_SEPARATOR}"
            rf"(?P<number>{_HORIZONTAL_DIGITS})(?P<suffix>[.,/+\-][0-9]+|[а-яa-z]\w*)?"
        )
        for match in expression.finditer(value):
            if any(start <= match.start() < end for start, end in combined_spans):
                continue
            if match.group("suffix"):
                return f"{label}: недопустимый формат числового реквизита; сверьте с PDF."
            error = _identifier_error(label, match.group("number"), lengths)
            if error:
                return error
    return None
