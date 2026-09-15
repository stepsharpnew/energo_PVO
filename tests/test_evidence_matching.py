from __future__ import annotations

import pytest

from executive_docs.evidence_matching import (
    entity_value_is_present,
    iter_evidence_spans,
    material_quantity_is_present,
    material_name_with_type,
    material_row_fragment_is_present,
    normalize_evidence_text,
    text_value_is_present,
    title_value_is_present,
    validate_numeric_identifiers,
)


def test_long_project_title_may_restore_only_a_closing_prose_parenthesis():
    title = "Строительство ВЛИ-0,38 кВ (сооруж. по дог. №С8-25-303-235077(542604) от 05.11.2025, пос. Березки, д.101)"
    fragment = 'по титулу: «' + title[:-1] + '»'
    assert title_value_is_present(title, fragment)
    assert not text_value_is_present(title, fragment)
    assert not title_value_is_present(title.replace("235077", "235078"), fragment)
    assert not title_value_is_present(title.replace("0,38", "0,4"), fragment)
    assert not title_value_is_present("С8-25-303-235077(542604)", "С8-25-303-235077(542604")
    assert not title_value_is_present("(12,5)", "(125")


@pytest.mark.parametrize(
    ("value", "fragment"),
    [
        ("Солнечногорский район", "МО, Солнечногорский р-он, д. Бережки"),
        ("Солнечногорский р-н", "МО, Солнечногорский район, д. Бережки"),
        ("Солнечногорский район", "Солнечногорский р ‑ н"),
        ('ООО "Энергосистемы"', "Проектная организация: ООО «ЭНЕРГОСИСТЕМЫ»"),
        ("ПАО «МОЭСК» — филиал «Северные электрические сети»", "Заказчик: ПАО «МОЭСК» — филиал Северные электрические сети"),
        ("ОГРН 1135044003709; ИНН 5044089069; КПП 504401001", "ООО «Энергосистемы»; ОГРН 1135044003709, ИНН 5044089069, КПП 504401001."),
        ("Бережной", "Заявитель: БЕРЕЖНОЙ"),
        ("пос. Берёзки", "Адрес: пос. Березки"),
        ("ООО «Строй 123»", 'Организация ООО "Строй 123"'),
        ("12,5 м", "Протяженность 12,5 м."),
        ("5593-355745-110-04/26-ЭС", "Шифр: 5593-355745-110-04/26-ЭС."),
        ("СВ95-3АТ", "Применяется опора СВ95-3АТ."),
    ],
)
def test_permitted_formatting_equivalence(value: str, fragment: str) -> None:
    assert text_value_is_present(value, fragment)


@pytest.mark.parametrize(
    ("value", "fragment"),
    [
        ("", "любое значение"),
        ("ООО «Энергосистемы»", "ООО «Энергосистема»"),
        ("ПАО «МОЭСК»", "ООО «МОЭСК»"),
        ("район", "межрайонный"),
        ("выполнено", "невыполнено"),
        ("125 м", "Длина 12,5 м"),
        ("12.5 м", "Длина 12,5 м"),
        ("12,5 м", "Длина 12;5 м"),
        ("12,5 м", "Длина 12,5 мм"),
        ("5 м", "Длина 12,5 м"),
        ("5 м", "Отклонение -5 м"),
        ("5 м", "Отклонение −5 м"),
        ("12", "Длина 12,5 м"),
        ("5044089069", "ИНН 50440890690"),
        ("ИНН 5044089069", "ИНН 5044089068"),
        ("23.06.2026", "Дата 23.07.2026"),
        ("23062026", "Дата 23.06.2026"),
        ("06.2026", "Дата 23.06.2026"),
        ("55933557451100426ЭС", "Шифр 5593-355745-110-04/26-ЭС"),
        ("5593-355745-110", "Шифр 5593-355745-110-04/26-ЭС"),
        ("СВ95", "Опора СВ95-3АТ"),
        ("3×70+1×95", "Провод 3×95+1×70"),
        ("70", "Провод 3×70+1×95"),
        ("50×50×5 мм", "Уголок 50×50×4 мм"),
        ("3", 'Размер 3"'),
        ("3", "Размер 3′"),
        ("3", "Уклон 3%"),
    ],
)
def test_facts_units_and_boundaries_are_not_relaxed(value: str, fragment: str) -> None:
    assert not text_value_is_present(value, fragment)


def test_numeric_punctuation_and_literal_quote_units_are_not_erased() -> None:
    for value in ('12,5', '12.5', '3"', '3′'):
        assert normalize_evidence_text(value) == value


@pytest.mark.parametrize(
    "text",
    [
        "ОГРН 1135044003709; ИНН 5044089069; КПП 504401001; БИК 044525411",
        "ИНН 123456789012; ОГРНИП 123456789012345",
        "ИНН/КПП 5044089069/504401001",
        "ИНН / КПП: 5044089069 / 504401001",
        "ИНН5044089069",
        "р/с 40702 81060 000 1168660; к/с 30101810145250000411",
        "Расчётный счёт № 40702810600001168660",
        "Корреспондентский счет: 30101810145250000411",
        "Шифр 5593-355745-110-04/26-ЭС; номер 4070281060000116866",
        "Заказчик ООО «Компания», ИНН отсутствует",
    ],
)
def test_valid_explicit_identifiers_and_unlabelled_numbers(text: str) -> None:
    assert validate_numeric_identifiers(text) is None


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("р/с 4070281060000116866", "р/с"),
        ("к/с 3010181014525000041", "к/с"),
        ("БИК 04452541", "БИК"),
        ("ОГРН 113504400370", "ОГРН"),
        ("ОГРНИП 12345678901234", "ОГРНИП"),
        ("ИНН 504408906", "ИНН"),
        ("КПП 50440100", "КПП"),
        ("ИНН/КПП 504408906/504401001", "ИНН"),
        ("ИНН/КПП 5044089069/50440100", "КПП"),
        ("ИНН/КПП 5044089069/504401001А", "КПП"),
        ("ИНН/КПП 5044089069/504401001.1", "КПП"),
        ("ИНН 5044089069.1", "ИНН"),
        ("ИНН 5044089069А", "ИНН"),
    ],
)
def test_identifier_transcription_errors_are_not_repaired(text: str, label: str) -> None:
    error = validate_numeric_identifiers(text)
    assert error is not None
    assert error.startswith(label + ":")
    assert "PDF" in error


def test_saved_submission_formatting_is_allowed_but_lost_account_digit_is_not() -> None:
    value = (
        "ОГРН 1135044003709; ИНН 5044089069; КПП 504401001; "
        "к/с 30101810145250000411; р/с 4070281060000116866; "
        "БИК 044525411; филиал «Центральный» Банка ВТБ (ПАО)"
    )
    fragment = (
        "ООО «ЭНЕРГОСИСТЕМЫ»; ОГРН 1135044003709, ИНН 5044089069, "
        "КПП 504401001, к/с 30101810145250000411, р/с 4070281060000116866, "
        "БИК 044525411, филиал «Центральный» Банка ВТБ (ПАО)."
    )
    # Presence matching tolerates the harmless separators even when the model
    # repeated the same mistaken account transcription in its quote and value.
    # The independent length check must still reject that record.
    assert text_value_is_present(value, fragment)
    error = validate_numeric_identifiers(value)
    assert error is not None and "19" in error and "20" in error


@pytest.mark.parametrize(
    ("value", "fragment"),
    [
        ('ООО «А»', 'Проектная организация: ООО "А"'),
        ('ООО «А Строй»', 'Проектная организация: ООО „А Строй“'),
        ('ООО «А»', 'ООО А; ИНН 5044089069'),
        ('ООО А', 'Проектная организация: ООО «А»'),
        ('ООО «А»', 'ООО А, юридический адрес: Москва'),
        ('ООО «А»', 'ООО А ИНН 5044089069'),
        ('ПАО «МОЭСК» — филиал «Северные электрические сети»', 'Заказчик: ПАО «МОЭСК» — филиал Северные электрические сети'),
        ('Иванов И.И.', 'Представитель заказчика Иванов И.И.'),
        ('ООО «А»', 'ООО «А Строй»; проектная организация: ООО «А»'),
    ],
)
def test_entity_match_retains_typographic_variants_and_exact_later_match(value: str, fragment: str) -> None:
    assert entity_value_is_present(value, fragment)


@pytest.mark.parametrize(
    ("value", "fragment"),
    [
        ('ООО «А»', 'Проектная организация: ООО «АБ»'),
        ('ООО «А»', 'Проектная организация: ООО «А Строй»'),
        ('ООО «А»', 'Проектная организация: ООО "А Строй"'),
        ('ООО А', 'Проектная организация: ООО «А Строй»'),
        ('ООО «А»', 'Проектная организация: ООО А Строй; ИНН 5044089069'),
        ('ООО «А»', 'Проектная организация: ООО А Строй ИНН 5044089069'),
        ('ООО «А»', 'Проектная организация: ООО А Строй'),
        ('ООО «А»', 'Проектная организация: ПАО «А»'),
    ],
)
def test_entity_name_must_not_be_a_prefix_of_a_different_company(value: str, fragment: str) -> None:
    assert not entity_value_is_present(value, fragment)


def test_entity_span_offsets_refer_to_normalized_fragment_and_skip_prefix() -> None:
    fragment = 'ООО «А Строй»; проектная организация: ООО «А»'
    normalized = normalize_evidence_text(fragment)
    spans = list(iter_evidence_spans('ООО «А»', fragment, require_entity_boundaries=True))
    assert len(spans) == 1
    start, end = spans[0]
    assert normalized[start:end] == 'ооо а'
    assert start > normalized.index('проектная организация')


@pytest.mark.parametrize(
    ("value", "fragment"),
    [
        ("уч. 3/18", "уч.3/18"),
        ("д. Бережки", "д.Бережки"),
        ("г. Солнечногорск", "г.Солнечногорск"),
        ("ул. Промышленная, стр. 5", "ул.Промышленная, стр.5"),
        ("городской округ Солнечногорск, д. Бережки Московская область", "городской округ Солнечногорск,д.Бережки Московская область"),
    ],
)
def test_address_caption_spacing_does_not_change_the_fact(value: str, fragment: str) -> None:
    assert text_value_is_present(value, fragment)


@pytest.mark.parametrize(
    ("value", "fragment"),
    [
        ("уч. 3/18", "уч.31/8"),
        ("д. 12,5", "д.125"),
        ("д. Бережки", "д.Березки"),
        ("ул. 23.06.2026", "ул.23.07.2026"),
        ("ИНН 5044089069", "ИНН5044089069"),
    ],
)
def test_address_spacing_is_not_global_token_or_number_repair(value: str, fragment: str) -> None:
    assert not text_value_is_present(value, fragment)


@pytest.mark.parametrize(
    ("value", "fragment"),
    [
        ("143 м", "Провод СИП-2г 3х70+1х70 м 143"),
        ("12 шт.", "Стойка СВ95-3АТ шт. 12"),
        ("5 шт.", "Заземляющий проводник ЗП6 1 м шт. 5"),
        ("25 шт.", "Скрепа NC20 шт. 25"),
        ("14 м", "Сталь полосовая 40х4 мм ГОСТ 103-2006 м 14"),
        ("2,4 кг", "Краска белая кг 2,4"),
        ("143 м", "Провод СИП, количество 143 м."),
        ("12 шт", "Стойка СВ95-3АТ шт. 12"),
        ("143 м", "Провод СИП м 143; масса 1,24 кг"),
        ("79 м", "Провод СИП-2г 3х95+1х95 м 79 1,24"),
        ("79 м", "Провод СИП-2г 3х95+1х95 79 м 1,24"),
    ],
)
def test_material_quantity_preserves_number_and_unit_in_either_column_order(value: str, fragment: str) -> None:
    assert material_quantity_is_present(value, fragment)


@pytest.mark.parametrize(
    ("value", "fragment"),
    [
        ("143 м", "Провод СИП м 1430"),
        ("5 м", "Провод СИП м 12,5"),
        ("125 м", "Провод СИП м 12,5"),
        ("12.5 м", "Провод СИП м 12,5"),
        ("12 м", "Провод СИП м 12,0"),
        ("12 м", "Провод СИП мм 12"),
        ("12 м", "Провод СИП м² 12"),
        ("12 шт.", "Стойка СВ95-3АТ шт. -"),
        ("5 м", "Отклонение -5 м"),
        ("5 м", "Отклонение − 5 м"),
        ("5 м", "Отклонение - 5 м"),
        ("5 м", "Отклонение + 5 м"),
        ("5 м", "Сталь, линейная масса кг/м 5"),
        ("5 м", "Сталь, линейная масса кг / м 5"),
        ("5 м", "Болт с моментом затяжки Н·м 5"),
        ("5 м", "Болт с моментом затяжки Н · м 5"),
        ("5 м", "Болт с моментом затяжки Н⋅м 5"),
        ("5 м", "Болт с моментом затяжки Н ⋅ м 5"),
        ("5 м", "Болт с моментом затяжки Н∙м 5"),
        ("5 м", "Болт с моментом затяжки Н ∙ м 5"),
        ("5 м", "Болт с моментом затяжки Н×м 5"),
        ("5 м", "Болт с моментом затяжки Н*м 5"),
        ("5 м", "Единица кг∕м 5"),
        ("5 м", "Единица кг⁄м 5"),
        ("5 м", "Сталь 12, 5 м"),
        ("5 м", "Сталь 12 , 5 м"),
        ("5 м", "Сталь 12. 5 м"),
        ("70 м", "Провод 3х70+1х70 м 143"),
        ("5 мм", "Уголок 50х50х5 мм шт. 5"),
        ("8 мм", "Сталь круглая d8 мм, ГОСТ 2590-2006 м 40"),
        ("79 м", "Провод СИП-2г 3х95+1х95 м791,24"),
        ("1,24 кг", "Провод СИП м 143; масса 1,24 кг"),
        ("1 м", "Заземляющий проводник ЗП6 1 м шт. 5"),
        ("143 м кабеля", "Провод СИП м 143"),
        ("ИНН 5044089069", "ИНН 5044089069"),
    ],
)
def test_material_quantity_does_not_reorder_generic_text_or_change_number_unit(value: str, fragment: str) -> None:
    assert not material_quantity_is_present(value, fragment)


@pytest.mark.parametrize("separator", ["—", "–", "|"])
@pytest.mark.parametrize("suffix,value", [
    ("шт — 1", "1 шт"), ("шт. — 2", "2 шт"), ("м — 62", "62 м"),
    ("кг — 0,25", "0,25 кг"), ("12 — м", "12 м"),
    ("м — 62 — 1,24 кг", "62 м"),
])
def test_explicit_material_table_cells_preserve_quantities(separator, suffix, value):
    quote = ("Провод — СИП-3г 1х70 — " + suffix).replace("—", separator)
    assert material_quantity_is_present(value, quote)


@pytest.mark.parametrize("value,quote", [
    ("5 м", "Сталь — кг/м — 5"), ("5 м", "Сталь — Н · м — 5"),
    ("5 м", "Сталь — м — − 5"), ("5 м", "Сталь — м — -5"),
    ("5 м", "Сталь — м — +5"), ("5 м", "Сталь — м — 12,5"),
    ("5 м", "Сталь — м — 12, 5"), ("12.5 м", "Сталь — м — 12,5"),
    ("5 м", "Сталь — мм — 5"), ("5 м", "Сталь — м² — 5"),
    ("5 кг", "Сталь — масса — кг — 5"), ("5 м", "Сталь — м — 5 — Другой материал"),
    ("5 м", "Сталь — м\n5"), ("5 м", "м — 5"),
    ("5 м", "Сталь — м — 5,0"), ("5 м", "Сталь — м — -"),
])
def test_table_separators_do_not_relax_numbers_units_signs_or_mass(value, quote):
    assert not material_quantity_is_present(value, quote)


def test_joined_material_mark_preserves_literal_separator_and_exact_code():
    quote = "Траверса — ТМ73 — шт — 4"
    assert material_name_with_type("Траверса", "ТМ73", quote) == "Траверса — ТМ73"
    assert not text_value_is_present(material_name_with_type("Траверса", "ТМ74", quote), quote)
    assert not text_value_is_present(material_name_with_type("Траверса", "ТМ7", quote), quote)


def test_material_quote_separator_normalization_never_changes_source():
    source = "Провод    СИП-2    м    12,5"
    assert material_row_fragment_is_present("Провод — СИП-2 — м — 12,5", source)
    assert not material_row_fragment_is_present("Провод — СИП-3 — м — 12,5", source)
    assert not material_row_fragment_is_present("Провод — СИП-2 — м — 12.5", source)
    assert not material_row_fragment_is_present("Провод — СИП-2 — м — 12,5", source.replace("12,5", "− 12,5"))
    assert not material_row_fragment_is_present("Провод — СИП-2 — м — 12,5", source.replace("м", "кг/м"))
    assert not material_row_fragment_is_present("Провод — СИП-2 — м — 12,5", "Провод СИП-2\nДругой материал м 12,5")
