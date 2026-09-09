from __future__ import annotations

import argparse
import hashlib
import re
import sys
import tempfile
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import openpyxl
import yaml
from openpyxl.formula import Tokenizer
from openpyxl.utils.cell import range_boundaries


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from executive_docs.excel import OOXMLWorkbook  # noqa: E402


SOURCE_DIR = ROOT / "NEW_TEMPLATES" / "Attachments_vku@e-systems-4"
ETALON_DIR = ROOT / "ETALON"
APPROVED_DIR = ROOT / "templates" / "approved"
CONTRACTS_DIR = ROOT / "templates" / "fill-contracts"
VERSION = "2026-09-08-discovery-6"
AOSR_VL_VERSION = VERSION
TEMPLATES = (
    ("emr", "1. ЭМР1.xlsx", "Электромонтажные работы (ЭМР)", "emr"),
    ("protocols", "2. Протоколы.xlsx", "Протоколы испытаний", "protocols"),
    ("ojr", "3. ОЖР.xlsx", "Общий журнал работ (ОЖР)", "ojr"),
    ("avk", "4. АВК.xlsx", "Входной контроль (АВК)", "avk"),
    ("aosr_vl", "8. АОСР ВЛ1.xlsx", "АОСР воздушной линии", "aosr_vl"),
)

FORMULA_ERRORS = ("#REF!", "#VALUE!", "#N/A", "#DIV/0!", "#NAME?")
CELL_RANGE = re.compile(r"[A-Z]{1,3}[1-9][0-9]*(?::[A-Z]{1,3}[1-9][0-9]*)?")
DATE_PATTERN = re.compile(
    r"\b(?:0?[1-9]|[12]\d|3[01])[./-](?:0?[1-9]|1[0-2])[./-]"
    r"(?:19|20)?\d{2}(?:\s*г\.?)?(?!\d)"
)
TEXTUAL_DATE_PATTERN = re.compile(
    r"(?:\bот\s+)?[«\"]?(?:0?[1-9]|[12]\d|3[01])[»\"]?\s+"
    r"(?:января|февраля|марта|апреля|мая|июня|июля|августа|"
    r"сентября|октября|ноября|декабря)\s+(?:19|20)\d{2}(?:\s*г\.?)?",
    re.IGNORECASE,
)
CALCULATION_VALUE_PATTERN = re.compile(
    r"=\s*-?\d[\d\s.,]*(?:/|:|\*)\s*-?\d",
)
PROJECT_QUANTITY_PATTERN = re.compile(
    r"\b\d+(?:[.,]\d+)?\s+(?:шт\.?|кв\.?\s*м|м[²³23]?|кг|ква|квт|кв)\b",
    re.IGNORECASE,
)
PERSON_PATTERN = re.compile(
    r"\b[А-ЯЁ][а-яё-]{2,}\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.(?:\s|$)"
)
PERSON_PATTERN_REVERSED = re.compile(
    r"(?:^|\s)[А-ЯЁ]\.\s*[А-ЯЁ]\.\s*[А-ЯЁ][а-яё-]{2,}(?:\s|$)"
)
SENSITIVE_TOKENS = (
    " инн ",
    " кпп ",
    " огрн ",
    " нрс ",
    " нострой",
    "приказ №",
    "доверенн",
    "полномочи",
    "гефест",
    "энергосистем",
    "солнечногорск",
    "высоцк",
)
PRIOR_PROJECT_TOKENS = (
    "гефест",
    "энергосистем",
    "солнечногорск",
    "высоцк",
)
STATIC_PLACEHOLDER_TOKENS = (
    "фамилия, имя, отчество",
    "полное и (или) сокращенное наименование",
    "адрес места жительства",
    "места нахождения юридического лица",
    "индивидуального предпринимателя",
    "указывается",
    "при наличии",
    "если установка",
    "является типовым",
    "обычно ",
)
REGULATORY_TEXT_TOKENS = (
    "нормативно-техническ",
    "нормативные документы",
    "гост ",
    "птээп",
    "пуэ",
    "снип",
    "сп ",
    "рд ",
    "таблица ",
    "требовани",
)
PACKAGE_FORBIDDEN_TOKENS = (
    "гефест",
    "энергосистем",
    "высоцк",
    "алексанян",
    "чернявск",
    "шатковск",
    "трушина",
    "бараночникова",
    "elena camarillo",
)
SHEET_RENAMES = {
    "emr": {
        "Титульный Гефест": "Титульный подрядчик",
    },
}
def _aosr_field(
    semantic_id: str,
    label: str,
    description: str,
    *,
    value_kind: str = "text",
    evidence_rule: str = "direct_pdf",
    required: bool = True,
    value_pattern: str | None = None,
    manual_reason: str | None = None,
    allow_project_basis: bool = False,
) -> dict:
    return {
        "semantic_id": semantic_id,
        "label": label,
        "description": description,
        "value_kind": value_kind,
        "evidence_rule": evidence_rule,
        "required": required,
        "manual_reason": manual_reason,
        "value_pattern": value_pattern,
        "allow_project_basis": allow_project_basis,
    }


AOSR_VL_FIELD_OVERRIDES = {
    ("Данные объект", "B2"): _aosr_field(
        "project.sap_number",
        "Номер SAP",
        "Короткий идентификатор SAP с явным префиксом SAP; это не шифр проектной документации",
        value_pattern=r"(?i)^(?:№\s*)?SAP\s*[-–—:]?\s*\d{4,}$",
    ),
    ("Данные объект", "B3"): _aosr_field(
        "project.object_name",
        "Наименование объекта капитального строительства",
        "Полное наименование объекта в формулировке PDF",
    ),
    ("Данные объект", "B4"): _aosr_field(
        "project.district",
        "Район объекта",
        "Муниципальный район или городской округ объекта",
    ),
    ("Данные объект", "B5"): _aosr_field(
        "project.object_address",
        "Адрес объекта",
        "Почтовый или строительный адрес объекта, а не адрес организации",
    ),
    ("Данные объект", "B9"): _aosr_field(
        "project.line_designation",
        "Обозначение линии ВЛ",
        "Наименование или диспетчерское обозначение линии, фидера и питающего пункта",
    ),
    ("Данные объект", "B42"): _aosr_field(
        "project.city",
        "Город (блок «Проект»)",
        "Подпись исходного шаблона не различает город проектной организации "
        "и место выпуска основного проекта; город вложенного задания не подтверждает это поле",
        manual_reason=(
            "Нужно уточнить, относится ли город к проектной организации или месту выпуска "
            "основного проекта, прежде чем сопоставлять поле сведениям PDF"
        ),
    ),
    ("Данные объект", "B43"): _aosr_field(
        "project.design_document_code",
        "Шифр проектной документации",
        "Полный шифр или номер проектной/рабочей документации; это не номер SAP",
    ),
    ("АОСР-1", "C33"): _aosr_field(
        "aosr_vl.act_1.number",
        "Номер первого АОСР",
        "Номер первого акта в комплекте; последующие номера вычисляются формулами",
        value_kind="number",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-2", "P63"): _aosr_field(
        "aosr_vl.act_2.support_count",
        "Количество смонтированных опор",
        "Фактическое количество опор по АОСР на монтаж опор",
        value_kind="number",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-2", "V63"): _aosr_field(
        "aosr_vl.act_2.pole_count",
        "Количество смонтированных стоек",
        "Фактическое количество железобетонных стоек по АОСР",
        value_kind="number",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-2", "M70"): _aosr_field(
        "aosr_vl.act_2.pole_quality_document",
        "Документ о качестве стоек",
        "Паспорт, сертификат или иной документ о качестве применённых стоек",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-2", "B97"): _aosr_field(
        "aosr_vl.act_2.additional_quality_document",
        "Дополнительный документ о качестве",
        "Полные реквизиты дополнительного сертификата, если он указан в PDF",
        evidence_rule="actual_executive_document_only",
        required=False,
    ),
    ("АОСР-3", "T62"): _aosr_field(
        "aosr_vl.act_3.support_count",
        "Количество опор для устройства заземления",
        "Фактическое количество опор, для которых выполнялись земляные работы",
        value_kind="number",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-3", "X62"): _aosr_field(
        "aosr_vl.act_3.excavation_volume_m3",
        "Объём выемки грунта, м³",
        "Фактический объём выемки грунта в кубических метрах",
        value_kind="number",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-4", "H69"): _aosr_field(
        "aosr_vl.act_4.angle_steel_quantity",
        "Количество уголка 50×50×5",
        "Фактическое количество уголка по АОСР устройства заземления",
        value_kind="number",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-4", "H70"): _aosr_field(
        "aosr_vl.act_4.rebar_quantity",
        "Количество арматуры Ø8",
        "Фактическое количество арматуры Ø8 по АОСР",
        value_kind="number",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-4", "H71"): _aosr_field(
        "aosr_vl.act_4.steel_strip_quantity",
        "Количество полосы 40×4",
        "Фактическое количество полосы 40×4 мм по АОСР",
        value_kind="number",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-4", "L69"): _aosr_field(
        "aosr_vl.act_4.angle_steel_quality_document",
        "Документ о качестве уголка",
        "Реквизиты документа о качестве уголка 50×50×5",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-4", "L70"): _aosr_field(
        "aosr_vl.act_4.rebar_quality_document",
        "Документ о качестве арматуры",
        "Реквизиты документа о качестве арматуры Ø8",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-4", "L71"): _aosr_field(
        "aosr_vl.act_4.steel_strip_quality_document",
        "Документ о качестве полосы",
        "Реквизиты документа о качестве полосы 40×4 мм",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-6", "H69"): _aosr_field(
        "aosr_vl.act_6.sip_quantity",
        "Количество провода СИП",
        "Фактическое количество провода СИП по АОСР",
        value_kind="number",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-6", "H70"): _aosr_field(
        "aosr_vl.act_6.line_fittings_quantity",
        "Количество линейной арматуры",
        "Фактическое количество линейной арматуры по АОСР",
        value_kind="number",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-6", "L70"): _aosr_field(
        "aosr_vl.act_6.line_fittings_quality_document",
        "Документ о качестве линейной арматуры",
        "Полные реквизиты документа о качестве линейной арматуры",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-7", "H69"): _aosr_field(
        "aosr_vl.act_7.paint_quantity",
        "Количество краски",
        "Фактическое количество краски по АОСР окраски опор",
        value_kind="number",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-7", "H70"): _aosr_field(
        "aosr_vl.act_7.line_fittings_quantity",
        "Количество линейной арматуры",
        "Фактическое количество линейной арматуры по АОСР окраски опор",
        value_kind="number",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-7", "L69"): _aosr_field(
        "aosr_vl.act_7.paint_quality_document",
        "Документ о качестве краски",
        "Полные реквизиты документа о качестве краски",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-7", "L70"): _aosr_field(
        "aosr_vl.act_7.line_fittings_quality_document",
        "Документ о качестве линейной арматуры",
        "Полные реквизиты документа о качестве линейной арматуры",
        evidence_rule="actual_executive_document_only",
    ),
    ("АОСР-шурф", "C32"): _aosr_field(
        "aosr_vl.pit_act.number",
        "Номер АОСР шурфления",
        "Номер отдельного акта шурфления, если этот скрытый лист используется",
        evidence_rule="actual_executive_document_only",
        required=False,
    ),
}

# Only these quantitative work/material fields may carry a visibly marked
# design-basis draft value. Dates, act numbers and quality documents never do.
AOSR_VL_PROJECT_QUANTITY_UNITS = {
    ("АОСР-2", "P63"): "опоры (шт.)", ("АОСР-2", "V63"): "стойки СВ 95-3 (шт.)",
    ("АОСР-3", "T62"): "опоры (шт.)", ("АОСР-3", "X62"): "м³",
    ("АОСР-4", "H69"): "м", ("АОСР-4", "H70"): "м", ("АОСР-4", "H71"): "м",
    ("АОСР-6", "H69"): "м", ("АОСР-6", "H70"): "шт.",
    ("АОСР-7", "H69"): "кг", ("АОСР-7", "H70"): "шт.",
}
AOSR_VL_PROJECT_QUANTITY_TARGETS = set(AOSR_VL_PROJECT_QUANTITY_UNITS)
for _target in AOSR_VL_PROJECT_QUANTITY_TARGETS:
    AOSR_VL_FIELD_OVERRIDES[_target]["allow_project_basis"] = True
    AOSR_VL_FIELD_OVERRIDES[_target]["description"] += (
        f". Единица исходного шаблона: {AOSR_VL_PROJECT_QUANTITY_UNITS[_target]}. "
        "Не вписывать число в другой единице и не пересчитывать неуказанный итог. "
        "Если в PDF есть только проектное количество для этой работы и того же материала, "
        "разрешён черновой перенос с value_basis=project, отдельной подсветкой и проверкой "
        "специалистом. Не выдавать проектное количество за выполненное. Не вычислять "
        "отсутствующие объёмы и не заменять материал похожей маркой."
    )

AOSR_VL_BROKEN_FORMULA_CELLS = {
    "АОСР-1": {"A117"},
    "АОСР-2": {"A118"},
    "АОСР-3": {"A115"},
    "АОСР-5": {"A114"},
    "АОСР-6": {"A116"},
    "АОСР-7": {"A115"},
    "АОСР-шурф": {"A114"},
}

AOSR_VL_FORMULA_OVERRIDES = {
    ("АОСР-2", "C33"): "=IF('АОСР-1'!C33=\"\",\"\",'АОСР-1'!C33+1)",
    ("АОСР-3", "C32"): "=IF('АОСР-2'!C33=\"\",\"\",'АОСР-2'!C33+1)",
    ("АОСР-4", "C32"): "=IF('АОСР-3'!C32=\"\",\"\",'АОСР-3'!C32+1)",
    ("АОСР-5", "C32"): "=IF('АОСР-4'!C32=\"\",\"\",'АОСР-4'!C32+1)",
    ("АОСР-6", "C32"): "=IF('АОСР-5'!C32=\"\",\"\",'АОСР-5'!C32+1)",
    ("АОСР-7", "C32"): "=IF('АОСР-6'!C32=\"\",\"\",'АОСР-6'!C32+1)",
    ("АОСР-6", "A62"): "=IF('АОСР-5'!A86=\"\",\"\",'АОСР-5'!A86)",
    ("АОСР-7", "A62"): "=IF('АОСР-6'!A86=\"\",\"\",'АОСР-6'!A86)",
}


def object_card_field_overrides(template_id: str, source_book) -> dict:
    """Map explicit PDF-backed inputs, never organization/profile lookup values.

    Captions and formula consumers in NEW_TEMPLATES establish the target role.
    The PDF must independently establish each value and that same role. Direct
    lookup precedents may hold current-PDF facts only when a precise card field
    consumes them; unused lookup columns are not reusable organization profiles.
    """

    if template_id not in {item[0] for item in TEMPLATES}:
        return {}
    sheet_name = "Данные объект"
    worksheet = source_book[sheet_name]
    fields = {}

    backing_cells = {
        "emr": {"B34": "G2", "B35": "G3"},
        "protocols": {"B23": "B2", "B24": "B3", "B34": "F1", "B35": "F2", "B36": "F3"},
        "ojr": {"B31": "F2", "B32": "F3"},
        "avk": {"B24": "F2", "B25": "F3"},
        "aosr_vl": {},
    }[template_id]

    def add(coordinate: str, expected_label: str, definition: dict) -> None:
        cell = worksheet[coordinate]
        observed_label = normalized_sheet(str(worksheet.cell(cell.row, 1).value or ""))
        if observed_label != normalized_sheet(expected_label):
            raise ValueError(f"Изменилась подпись поля карточки: {sheet_name}!{coordinate}")
        if coordinate in backing_cells:
            target = backing_cells[coordinate]
            expected_formulas = {
                f"='Данные организации'!{target}",
                f"='[1]Данные организации'!{target}",
            }
            if cell.value not in expected_formulas:
                raise ValueError(f"Изменилась ссылка поля карточки: {sheet_name}!{coordinate}")
            backing = source_book["Данные организации"][target]
            if is_formula(backing.value) or is_merged_non_anchor(backing.parent, backing):
                raise ValueError(f"Некорректный источник поля карточки: Данные организации!{target}")
            fields[("Данные организации", target)] = dict(definition)
            return
        if is_formula(cell.value) or is_merged_non_anchor(worksheet, cell):
            raise ValueError(f"Некорректное поле карточки: {sheet_name}!{coordinate}")
        fields[(sheet_name, coordinate)] = dict(definition)

    for coordinate, caption in (("B2", "№ САП"), ("B3", "Объект"), ("B4", "р-н"), ("B5", "Адрес")):
        add(coordinate, caption, AOSR_VL_FIELD_OVERRIDES[(sheet_name, coordinate)])

    actual_date_rows = ((6, "start", "Дата старт"), (7, "end", "Дата финиш")) if template_id in {"avk", "aosr_vl"} else (
        (6, "staking", "Дата разбивки"), (7, "start", "Дата старт"), (8, "end", "Дата финиш"),
    )
    date_labels = {"start": "Фактическая дата начала работ", "end": "Фактическая дата окончания работ", "staking": "Фактическая дата разбивки"}
    for row, kind, caption in actual_date_rows:
        add(f"B{row}", caption, _aosr_field(
            f"actual.{kind}", date_labels[kind],
            f"{date_labels[kind]} по записи о выполненных работах в загруженном PDF. "
            "Не использовать проектный график, дату договора, выпуска проекта или электронной подписи.",
            value_kind="date", evidence_rule="actual_executive_document_only",
        ))

    # All three inputs must carry the organization's explicit project role.
    # The EMR project block is intentionally absent: source captions B51–B56
    # disagree with its output formulas (e.g. B52 is used as designer name).
    organization_rows = {
        "aosr_vl": {"contractor": 11, "customer": 23, "designer": 39},
        "avk": {"contractor": 11, "customer": 23, "designer": 36},
        "emr": {"contractor": 19, "customer": 33},
        "ojr": {"contractor": 17, "customer": 30, "designer": 50, "commissioning": 58},
        "protocols": {"contractor": 22, "customer": 34, "designer": 50, "laboratory": 58},
    }[template_id]
    role_names = {
        "contractor": "Монтажная организация (лицо, осуществляющее строительство)",
        "customer": "Заказчик / технический заказчик",
        "designer": "Проектная организация (разработчик проектной документации)",
        "commissioning": "Пусконаладочная организация",
        "laboratory": "Испытательная электролаборатория",
    }
    for role, first_row in organization_rows.items():
        for offset, part, caption in ((0, "name", "Организация"), (1, "registration", "Реквизиты"), (2, "address", "адрес")):
            label = f"{role_names[role]}: {caption.lower()}"
            add(f"B{first_row + offset}", caption, _aosr_field(
                f"{role}.{part}", label,
                f"{label}. Только из текущего PDF, с явной связью юридического лица "
                "с этой ролью в данном проекте. Для реквизитов/адреса подтвердить принадлежность "
                "той же организации; при необходимости сослаться также на страницу с её ролью. "
                "Логотип, общая фамилия директора или адрес объекта не подтверждают роль. "
                "При противоречащих организациях для одной роли оставить пустым и показать обе версии.",
                evidence_rule="organization_role_pdf",
            ))

    # These roles are established by output-form captions, not by names or
    # positions prefilled in the source object card. Other unlabeled groups
    # remain unreviewed rather than being guessed from an old organization.
    representative_rows = {
        "aosr_vl": (
            (16, "contractor.construction_control", "Представитель монтажной организации по строительному контролю", True),
            (19, "contractor.site_representative", "Представитель лица, осуществляющего строительство", True),
            (32, "customer.construction_control", "Представитель заказчика по строительному контролю", True),
            (35, "customer.other_representative", "Иной представитель заказчика, участвующий в освидетельствовании", True),
        ),
        "emr": ((27, "contractor.site_representative", "Полномочный представитель подрядчика при проверке готовности к работам", True),),
        "ojr": (
            (22, "contractor.construction_control", "Уполномоченный представитель подрядчика по строительному контролю", True),
            (26, "contractor.site_representative", "Уполномоченный представитель лица, осуществляющего строительство", True),
            (40, "customer.construction_control", "Уполномоченный представитель заказчика по строительному контролю", True),
        ),
        "protocols": (
            (61, "laboratory.reviewer", "Специалист электролаборатории, проверивший протокол", False),
            (64, "laboratory.tester_1", "Первый специалист электролаборатории, проводивший проверку", False),
            (66, "laboratory.tester_2", "Второй специалист электролаборатории, проводивший проверку", False),
        ),
        "avk": (),
    }[template_id]
    for first_row, role, role_label, has_authority in representative_rows:
        parts = [(0, "position", "Должность"), (1, "name", "Ф.И.О.")]
        if has_authority:
            parts.append((2, "authority", "Приказ"))
        for offset, part, caption in parts:
            add(f"B{first_row + offset}", caption, _aosr_field(
                f"{role}.{part}", f"{role_label}: {caption}",
                f"{role_label}: {caption}. PDF должен прямо связывать человека, организацию "
                "и указанную роль на этом объекте. Разработчик чертежа, директор или автор "
                "электронной подписи не становится подписантом этого документа автоматически. "
                "Для основания полномочий нужны реквизиты распорядительного документа и его "
                "связь с тем же человеком/ролью; не переносить приказ другого назначения.",
                evidence_rule="authority_document_pdf" if part == "authority" else "signatory_role_pdf",
            ))

    installation_rows = {
        "emr": ((12, "ТП", "substation"), (13, "АСП", "asp"), (14, "ВЛ-10", "overhead_line_10kv"),
                (15, "ВЛ-0,4", "overhead_line_04kv"), (16, "КЛ", "cable_line"), (17, "ВРЩ", "switchboard")),
        "protocols": ((15, "ТП", "substation"), (17, "ВЛ-10", "overhead_line_10kv"),
                      (18, "ВЛ-0,4", "overhead_line_04kv"), (19, "КЛ", "cable_line"), (20, "ВРЩ", "switchboard")),
        "ojr": ((12, "ВЛ-10", "overhead_line_10kv"), (13, "ВЛ-0,4", "overhead_line_04kv"),
                (14, "КЛ", "cable_line"), (15, "ВРЩ", "switchboard")),
        "avk": ((9, "ТП", "substation"),),
        "aosr_vl": (),
    }
    for row, caption, kind in installation_rows[template_id]:
        add(
            f"B{row}", caption,
            _aosr_field(
                f"project.installation.{kind}",
                f"Обозначение электроустановки: {caption}",
                f"Проектное наименование или диспетчерское обозначение {caption} из PDF. "
                "Оставить пустым, если установка такого вида в проекте не указана; "
                "не подставлять обозначение другого вида установки.",
            ),
        )

    # In the EMR source this lower block has shifted captions. Do not infer its
    # city/code mapping from stale example values or from another workbook.
    project_rows = {"protocols": (53, 54), "ojr": (53, 54), "avk": (39, 40)}
    if template_id in project_rows:
        city_row, code_row = project_rows[template_id]
        add(f"B{city_row}", "Город", AOSR_VL_FIELD_OVERRIDES[(sheet_name, "B42")])
        add(f"B{code_row}", "№", AOSR_VL_FIELD_OVERRIDES[(sheet_name, "B43")])
    if template_id == "avk":
        add(
            "B41", "Название",
            _aosr_field(
                "project.design_document_title", "Наименование проектной документации",
                "Полное название проектной или рабочей документации, указанное на титульном листе PDF",
            ),
        )
    if template_id == "aosr_vl":
        # The legacy source caption B9 says ВРЩ; its separately reviewed VL
        # override, not this generic card mapper, supplies the line semantics.
        add("B42", "Город", AOSR_VL_FIELD_OVERRIDES[(sheet_name, "B42")])
        add("B43", "№", AOSR_VL_FIELD_OVERRIDES[(sheet_name, "B43")])
    if template_id == "protocols":
        for row, caption, key in (
            (10, "Температура воздуха", "temperature"),
            (11, "Влажность", "humidity"),
            (12, "Атмосферное давление", "pressure"),
        ):
            add(f"B{row}", caption, _aosr_field(
                f"laboratory.test_conditions.{key}", f"Фактические условия испытания: {caption.lower()}",
                f"Измеренные {caption.lower()} во время испытания по протоколу в PDF. "
                "Не использовать климатические справочные данные и проектные расчётные условия.",
                value_kind="number", evidence_rule="actual_executive_document_only",
            ))
    return fields


def material_table_field_overrides(template_id: str, source_book) -> dict:
    """Expand only caption-proven material columns, never old example facts.

    The source's repeated-row order is a layout, not a required material order.
    Each current PDF item receives one row; its name, type and quantity stay on
    that same row. Empty spare rows are existing anchors, not new workbook rows.
    """
    fields = {}
    if template_id == "avk":
        sheet_name = " Журнал АВК"
        worksheet = source_book[sheet_name]
        for coordinate, expected in {
            "C34": "Наименование деталей, материалов, изделий, конструкций, оборудования",
            "D34": "Количество",
        }.items():
            if normalized_sheet(str(worksheet[coordinate].value or "")) != normalized_sheet(expected):
                raise ValueError(f"Изменилась подпись материальной таблицы: {sheet_name}!{coordinate}")
        # Rows 36:76 are linked to individual acts with stale example product
        # names and are intentionally not made writable here. These ten spare
        # rows are genuinely blank and have no quantity/result formulas.
        for row in range(77, 87):
            if worksheet[f"A{row}"].value != row - 35:
                raise ValueError(f"Изменилась строка материальной таблицы: {sheet_name}!A{row}")
            for column, part, label in (
                ("C", "name", "Наименование и марка материала или оборудования"),
                ("D", "quantity", "Количество с единицей измерения"),
            ):
                coordinate = f"{column}{row}"
                cell = worksheet[coordinate]
                if cell.value not in (None, "") or is_merged_non_anchor(worksheet, cell):
                    raise ValueError(f"Резервная строка материальной таблицы больше не пуста: {sheet_name}!{coordinate}")
                fields[(sheet_name, coordinate)] = _aosr_field(
                    f"avk.materials.item_{row - 76}.{part}",
                    f"Материал / оборудование, резервная позиция {row - 76}: {label.lower()}",
                    f"{label}. C/D строки {row} относятся к одной позиции текущего PDF. "
                    "Разные позиции спецификации последовательно занимают строки 77–86. "
                    "Только проект: value_basis=project, не факт поставки или годности. "
                    "Единица количества — как в PDF, без расчёта отсутствующего итога.",
                    evidence_rule="actual_executive_document_only",
                    allow_project_basis=True,
                    required=False,
                )
        return fields
    if template_id != "emr":
        return fields
    sheet_name = "Ведомость общ"
    worksheet = source_book[sheet_name]
    captions = {
        "E17": "Наименование электрооборудования, комплекта",
        "AI17": "Тип, марка",
        "BE17": "Кол-во",
    }
    for coordinate, expected in captions.items():
        if normalized_sheet(str(worksheet[coordinate].value or "")) != normalized_sheet(expected):
            raise ValueError(f"Изменилась подпись материальной таблицы: {sheet_name}!{coordinate}")
    for row in range(19, 42):
        if worksheet[f"A{row}"].value != row - 18:
            raise ValueError(f"Изменилась строка материальной таблицы: {sheet_name}!A{row}")
        for column, part, label in (
            ("E", "name", "Наименование электрооборудования или материала"),
            ("AI", "type", "Тип, марка электрооборудования или материала"),
            ("BE", "quantity", "Количество с единицей измерения"),
        ):
            coordinate = f"{column}{row}"
            cell = worksheet[coordinate]
            if is_formula(cell.value) or is_merged_non_anchor(worksheet, cell):
                raise ValueError(f"Некорректная ячейка материальной таблицы: {sheet_name}!{coordinate}")
            fields[(sheet_name, coordinate)] = _aosr_field(
                f"emr.materials.item_{row - 18}.{part}",
                f"Материал / оборудование, позиция {row - 18}: {label.lower()}",
                f"{label}. E/AI/BE строки {row} относятся к одной позиции текущего PDF. "
                "Разные марки занимают разные строки 19–41 в порядке спецификации. "
                "Только проект: value_basis=project, не факт монтажа. "
                "Единица количества — как в PDF, без расчёта отсутствующего итога.",
                evidence_rule="actual_executive_document_only",
                allow_project_basis=True,
                required=False,
            )
    return fields


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def is_formula(value: object) -> bool:
    return isinstance(value, str) and value.startswith("=")


def normalized_sheet(name: str) -> str:
    return re.sub(r"\s+", " ", name.casefold().replace("ё", "е")).strip()


def is_primary_data_sheet(name: str) -> bool:
    return normalized_sheet(name) in {
        "данные объект",
        "данные организации",
    }


def is_input_sheet(name: str) -> bool:
    normalized = normalized_sheet(name)
    return (
        is_primary_data_sheet(name)
        or normalized in {"главная", "оборудование"}
    )


def value_kind(cell) -> str:
    if cell.is_date or isinstance(cell.value, (date, datetime)):
        return "date"
    if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
        return "number"
    return "text"


def unquote_sheet(value: str) -> str:
    value = value.strip()
    if value.startswith("'") and value.endswith("'"):
        value = value[1:-1].replace("''", "'")
    return re.sub(r"^\[[1-9][0-9]*\]", "", value)


def formula_references(workbook) -> set[tuple[str, str]]:
    """Collect direct A1 precedents without using ETALON as a mapping oracle."""

    names = {name.casefold(): name for name in workbook.sheetnames}
    references: set[tuple[str, str]] = set()
    for worksheet in workbook.worksheets:
        for row in worksheet.iter_rows():
            for cell in row:
                if not is_formula(cell.value):
                    continue
                try:
                    tokens = Tokenizer(cell.value).items
                except Exception:
                    continue
                for token in tokens:
                    if token.type != "OPERAND" or token.subtype != "RANGE":
                        continue
                    reference = token.value
                    if "!" in reference:
                        sheet_token, address = reference.rsplit("!", 1)
                        sheet_name = names.get(unquote_sheet(sheet_token).casefold())
                    else:
                        sheet_name = worksheet.title
                        address = reference
                    address = address.replace("$", "")
                    if sheet_name is None or not CELL_RANGE.fullmatch(address):
                        continue
                    min_column, min_row, max_column, max_row = range_boundaries(address)
                    if (max_column - min_column + 1) * (max_row - min_row + 1) > 10_000:
                        continue
                    target = workbook[sheet_name]
                    for target_row in range(min_row, max_row + 1):
                        for target_column in range(min_column, max_column + 1):
                            references.add(
                                (
                                    sheet_name,
                                    target.cell(target_row, target_column).coordinate,
                                )
                            )
    return references


def is_merged_non_anchor(worksheet, cell) -> bool:
    for merged in worksheet.merged_cells.ranges:
        if (
            merged.min_row <= cell.row <= merged.max_row
            and merged.min_col <= cell.column <= merged.max_col
        ):
            return cell.row != merged.min_row or cell.column != merged.min_col
    return False


def looks_project_specific(value: object) -> bool:
    if isinstance(value, (date, datetime)):
        return True
    if not isinstance(value, str):
        return False
    compact = re.sub(r"\s+", " ", value)
    normalized = f" {compact.casefold().replace('ё', 'е')} "
    has_numeric_date = bool(DATE_PATTERN.search(normalized))
    has_textual_date = bool(TEXTUAL_DATE_PATTERN.search(normalized))
    has_person = bool(
        PERSON_PATTERN.search(value)
        or PERSON_PATTERN_REVERSED.search(value)
    )
    has_named_organization = bool(
        re.search(r"\b(?:ооо|пао|ао)\s+[«\"]", normalized)
    )
    has_long_identifier = bool(re.search(r"\b\d{6,}\b", normalized))
    has_address = "ул." in normalized and (
        "дом" in normalized
        or "д." in normalized
        or "строен" in normalized
        or "корпус" in normalized
    )
    has_email = "@" in normalized
    has_prior_project_token = any(
        token in normalized for token in PRIOR_PROJECT_TOKENS
    )
    quality_document_with_identifier = any(
        token in normalized
        for token in (
            "паспорт",
            "сертификат",
            "декларац",
            "свидетельств",
            "удостоверен",
            "документ о качестве",
        )
    ) and (
        "№" in value
        or has_numeric_date
        or has_textual_date
        or bool(re.search(r"\b\d{3,}\b", value))
    )
    has_sensitive_identifier = any(
        token in normalized for token in SENSITIVE_TOKENS
    ) and bool(
        re.search(r"\d", value)
        or has_person
        or has_named_organization
        or has_address
        or has_email
        or has_prior_project_token
    )
    strong_signal = bool(
        has_numeric_date
        or has_textual_date
        or has_person
        or has_prior_project_token
        or quality_document_with_identifier
        or has_sensitive_identifier
        or has_named_organization
        or has_long_identifier
        or has_address
        or has_email
        or CALCULATION_VALUE_PATTERN.search(normalized)
    )
    if strong_signal:
        return True
    if any(token in normalized for token in STATIC_PLACEHOLDER_TOKENS):
        return False
    if any(token in normalized for token in REGULATORY_TEXT_TOKENS):
        return False
    return bool(
        PROJECT_QUANTITY_PATTERN.search(normalized)
    )


def is_horizontal_sequence_number(worksheet, cell) -> bool:
    if not isinstance(cell.value, int) or isinstance(cell.value, bool):
        return False
    values = [
        (candidate.column, candidate.value)
        for candidate in worksheet[cell.row]
        if isinstance(candidate.value, int) and not isinstance(candidate.value, bool)
    ]
    if len(values) < 3:
        return False
    values.sort()
    columns = [column for column, _ in values]
    numbers = [value for _, value in values]
    return (
        columns == list(range(columns[0], columns[0] + len(columns)))
        and numbers == list(range(numbers[0], numbers[0] + len(numbers)))
    )


def is_protocol_actual_entry_cell(worksheet, cell) -> bool:
    value = cell.value
    if value in (None, "") or is_formula(value):
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if cell.column == 1 and isinstance(value, int) and 0 < value <= 100:
            return False
        if is_horizontal_sequence_number(worksheet, cell):
            return False
        return True
    if isinstance(value, str) and CALCULATION_VALUE_PATTERN.search(value):
        return True
    raw_fill_rgb = cell.fill.fgColor.rgb
    fill_rgb = raw_fill_rgb.upper() if isinstance(raw_fill_rgb, str) else ""
    return cell.fill.fill_type == "solid" and fill_rgb in {
        "FFFFFF00",
        "FFCCFFFF",
        "FFFFE699",
    }


def is_actual_entry_cell(template_id: str, sheet_name: str, cell) -> bool:
    normalized = normalized_sheet(sheet_name)
    value = cell.value
    if value in (None, "") or is_formula(value):
        return False
    if isinstance(value, int) and cell.column == 1:
        return False
    if isinstance(value, str) and "заполняется от руки" in value.casefold():
        return False
    if template_id == "protocols" and is_protocol_actual_entry_cell(
        cell.parent,
        cell,
    ):
        return True
    if template_id == "ojr" and normalized.startswith("раздел") and cell.row >= 5:
        return True
    if template_id == "avk" and "журнал авк" in normalized and cell.row >= 11:
        return True
    if template_id == "emr" and (
        normalized.startswith("пр.15 реестр")
        or normalized.startswith("ведомость")
    ) and cell.row >= 5:
        return True
    return False


def should_register_cell(
    template_id: str,
    worksheet,
    cell,
    references: set[tuple[str, str]],
) -> bool:
    if is_formula(cell.value) or is_merged_non_anchor(worksheet, cell):
        return False
    # Hyperlinks in the source corpus are workbook navigation labels. Clearing
    # their cells while retaining the hyperlink makes spreadsheet readers expose
    # the target address as a value and destroys the template's contents.
    if cell.hyperlink:
        return False
    referenced = (worksheet.title, cell.coordinate) in references
    normalized = normalized_sheet(worksheet.title)
    if is_primary_data_sheet(worksheet.title) and cell.column >= 2:
        return cell.value not in (None, "") or referenced
    if normalized == "оборудование" and cell.row >= 2:
        return cell.value not in (None, "") or referenced
    if referenced and is_input_sheet(worksheet.title):
        return True
    return looks_project_specific(cell.value) or is_actual_entry_cell(
        template_id,
        worksheet.title,
        cell,
    )


def nearby_label(
    source_sheet,
    row: int,
    column: int,
    registered: set[str],
) -> str:
    candidates: list[tuple[int, int, str]] = []
    for row_offset in range(-3, 4):
        for column_offset in range(-5, 2):
            if row_offset == 0 and column_offset == 0:
                continue
            current_row = row + row_offset
            current_column = column + column_offset
            if current_row < 1 or current_column < 1:
                continue
            source = source_sheet.cell(current_row, current_column)
            if source.coordinate in registered or is_formula(source.value):
                continue
            if not isinstance(source.value, str):
                continue
            text = re.sub(r"\s+", " ", source.value).strip()
            if not text or len(text) > 140 or looks_project_specific(text):
                continue
            same_row_bonus = 0 if row_offset == 0 and column_offset < 0 else 1
            distance = abs(row_offset) + abs(column_offset)
            candidates.append((same_row_bonus, distance, text))
    labels: list[str] = []
    for _, _, text in sorted(candidates):
        if text not in labels:
            labels.append(text)
        if len(labels) == 2:
            break
    return " · ".join(labels)


def manual_reason(
    *,
    template_id: str,
    sheet: str,
    label: str,
    source_cell,
) -> str | None:
    """Withhold only unknown mappings, not categories presumed absent from PDF.

    Discovery finds cells worth clearing, but nearby text and old cell values
    do not establish a safe semantic target. Explicit reviewed-source overrides
    below remove this reason and declare PDF evidence rules for dates, actuals,
    quality documents, organizations and representatives alike.
    """
    normalized = normalized_sheet(sheet)
    if "данные организации" in normalized:
        return "Не установлена однозначная связь этой ячейки справочного листа с ролью в выбранном документе"
    if template_id == "emr" and normalized == "данные объект" and source_cell.coordinate in {
        "B51", "B52", "B53", "B54", "B55", "B56",
    }:
        return "Подписи блока «Проект» расходятся с назначением формул-потребителей; требуется уточнить сопоставление ячеек"
    if normalized == "данные объект":
        return "Роль или назначение этого поля карточки не определены однозначно по подписям и формулам исходного шаблона"
    return "Для этой ячейки ещё не проверены смысл поля и сопоставление записи PDF со строкой выбранного шаблона"


def compare_with_etalon(candidate_book, etalon_book) -> dict:
    common_sheets = [
        name for name in candidate_book.sheetnames if name in etalon_book.sheetnames
    ]
    formula_differences = 0
    nonformula_differences = 0
    formula_errors = 0
    for sheet_name in candidate_book.sheetnames:
        worksheet = candidate_book[sheet_name]
        for row in worksheet.iter_rows():
            for cell in row:
                if is_formula(cell.value) and any(
                    token in cell.value for token in FORMULA_ERRORS
                ):
                    formula_errors += 1
    for sheet_name in common_sheets:
        source_sheet = candidate_book[sheet_name]
        etalon_sheet = etalon_book[sheet_name]
        max_row = max(source_sheet.max_row, etalon_sheet.max_row)
        max_column = max(source_sheet.max_column, etalon_sheet.max_column)
        for row in range(1, max_row + 1):
            for column in range(1, max_column + 1):
                source_value = source_sheet.cell(row, column).value
                etalon_value = etalon_sheet.cell(row, column).value
                if source_value == etalon_value:
                    continue
                if is_formula(source_value) or is_formula(etalon_value):
                    formula_differences += 1
                else:
                    nonformula_differences += 1
    return {
        "candidate_sheet_count": len(candidate_book.sheetnames),
        "etalon_sheet_count": len(etalon_book.sheetnames),
        "candidate_vs_etalon_sheet_names_match": candidate_book.sheetnames
        == etalon_book.sheetnames,
        "candidate_only_sheet_count": len(
            [
                name
                for name in candidate_book.sheetnames
                if name not in etalon_book.sheetnames
            ]
        ),
        "etalon_only_sheet_count": len(
            [
                name
                for name in etalon_book.sheetnames
                if name not in candidate_book.sheetnames
            ]
        ),
        "candidate_vs_etalon_formula_differences": formula_differences,
        "candidate_vs_etalon_nonformula_differences": nonformula_differences,
        "formula_errors_observed": formula_errors,
        "etalon_external_links": len(getattr(etalon_book, "_external_links", [])),
    }


def raw_package_findings(path: Path) -> dict:
    raw_ref_errors = 0
    forbidden: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            payload = archive.read(name)
            if not name.endswith((".xml", ".rels")):
                continue
            raw_ref_errors += payload.upper().count(b"#REF!")
            decoded = payload.decode("utf-8", errors="ignore").casefold()
            decoded_utf16 = payload.decode("utf-16", errors="ignore").casefold()
            for token in PACKAGE_FORBIDDEN_TOKENS:
                if token in decoded or token in decoded_utf16:
                    forbidden.append(f"{name}:{token}")
    return {
        "raw_ref_error_count": raw_ref_errors,
        "package_forbidden_token_count": len(forbidden),
        "package_forbidden_token_examples": forbidden[:25],
    }


def unsafe_blank_formula_examples(workbook) -> list[str]:
    """Return direct links/concatenations that can emit false values from blanks."""

    direct = re.compile(
        r"^=\s*(?:(?:'(?:''|[^'])+'|[A-Za-z_\u0400-\u04FF][^'!\[\]]*)!)?"
        r"\$?[A-Z]{1,3}\$?[1-9][0-9]*\s*$"
    )
    unsafe: list[str] = []
    for worksheet in workbook.worksheets:
        for row in worksheet.iter_rows():
            for cell in row:
                formula = str(cell.value or "")
                if cell.data_type != "f":
                    continue
                upper = formula.lstrip("=").lstrip().upper()
                if direct.fullmatch(formula) or upper.startswith("CONCATENATE("):
                    unsafe.append(f"{worksheet.title}!{cell.coordinate}")
    return unsafe


def register(
    template_id: str,
    filename: str,
    display_name: str,
    document_kind: str,
    *,
    approved_dir: Path = APPROVED_DIR,
    contracts_dir: Path = CONTRACTS_DIR,
) -> dict:
    source_path = SOURCE_DIR / filename
    etalon_path = ETALON_DIR / filename
    if not source_path.is_file() or not etalon_path.is_file():
        raise FileNotFoundError(f"Не найдена пара NEW_TEMPLATES/ETALON: {filename}")

    source_book = openpyxl.load_workbook(
        source_path,
        data_only=False,
        keep_links=True,
    )
    try:
        source_external_links = len(getattr(source_book, "_external_links", []))
        sheet_renames = SHEET_RENAMES.get(template_id, {})
        references = formula_references(source_book)
        card_overrides = object_card_field_overrides(template_id, source_book)
        material_overrides = material_table_field_overrides(template_id, source_book)
        registered_by_sheet: dict[str, set[str]] = defaultdict(set)
        for worksheet in source_book.worksheets:
            for row in worksheet.iter_rows():
                for cell in row:
                    if should_register_cell(
                        template_id,
                        worksheet,
                        cell,
                        references,
                    ):
                        registered_by_sheet[worksheet.title].add(cell.coordinate)

        for sheet_name, coordinate in card_overrides:
            registered_by_sheet[sheet_name].add(coordinate)
        for sheet_name, coordinate in material_overrides:
            registered_by_sheet[sheet_name].add(coordinate)

        if template_id == "aosr_vl":
            for sheet_name, coordinate in AOSR_VL_FIELD_OVERRIDES:
                cell = source_book[sheet_name][coordinate]
                if is_formula(cell.value) or is_merged_non_anchor(
                    source_book[sheet_name],
                    cell,
                ):
                    raise ValueError(
                        f"Некорректное явное поле АОСР ВЛ: {sheet_name}!{coordinate}"
                    )
                registered_by_sheet[sheet_name].add(coordinate)
            for sheet_name in source_book.sheetnames:
                if sheet_name.startswith("АОСР"):
                    registered_by_sheet[sheet_name].discard("AJ1")

        fields = []
        clear_targets: dict[str, list[str]] = defaultdict(list)
        cleanup_only_targets: dict[str, list[str]] = defaultdict(list)
        for sheet_name in source_book.sheetnames:
            worksheet = source_book[sheet_name]
            registered = registered_by_sheet.get(sheet_name, set())
            for coordinate in sorted(
                registered,
                key=lambda value: (
                    worksheet[value].row,
                    worksheet[value].column,
                ),
            ):
                cell = worksheet[coordinate]
                clear_targets[sheet_name].append(coordinate)
                if template_id == "aosr_vl" and normalized_sheet(
                    sheet_name
                ) == "данные организации":
                    cleanup_only_targets[sheet_name].append(coordinate)
                    continue
                label = nearby_label(
                    worksheet,
                    cell.row,
                    cell.column,
                    registered,
                )
                candidate_sheet_name = sheet_renames.get(sheet_name, sheet_name)
                field = {
                    "sheet": candidate_sheet_name,
                    "cell": coordinate,
                    "label": label or f"{candidate_sheet_name}!{coordinate}",
                    "value_kind": value_kind(cell),
                    "required": True,
                    "manual_reason": manual_reason(
                        template_id=template_id,
                        sheet=sheet_name,
                        label=label,
                        source_cell=cell,
                    ),
                }
                if template_id == "aosr_vl":
                    field.update(
                        {
                            "description": label
                            or f"{candidate_sheet_name}!{coordinate}",
                            "evidence_rule": "direct_pdf",
                        }
                    )
                override = card_overrides.get((sheet_name, coordinate)) or material_overrides.get((sheet_name, coordinate))
                if template_id == "aosr_vl":
                    override = override or AOSR_VL_FIELD_OVERRIDES.get((sheet_name, coordinate))
                if override:
                    field.update(override)
                fields.append(field)

        if template_id == "aosr_vl":
            for sheet_name, coordinates in AOSR_VL_BROKEN_FORMULA_CELLS.items():
                clear_targets[sheet_name].extend(sorted(coordinates))
                cleanup_only_targets[sheet_name].extend(sorted(coordinates))

        approved_dir.mkdir(parents=True, exist_ok=True)
        contracts_dir.mkdir(parents=True, exist_ok=True)
        candidate_path = approved_dir / filename
        package = OOXMLWorkbook(source_path)
        package.clear_cells(clear_targets)
        localized_references = package.localize_external_sheet_references(
            source_book.sheetnames
        )
        formula_overrides = 0
        blank_preserving_formulas = 0
        if template_id == "aosr_vl":
            for (sheet_name, coordinate), formula in AOSR_VL_FORMULA_OVERRIDES.items():
                package.set_formula(sheet_name, coordinate, formula)
                formula_overrides += 1
            blank_preserving_formulas = package.guard_blank_formula_results()
        for old_name, new_name in sheet_renames.items():
            package.rename_sheet(old_name, new_name)
        removed_external_links = package.remove_external_links()
        removed_broken_defined_names = package.remove_broken_defined_names()
        removed_broken_data_validations = (
            package.remove_broken_data_validations()
        )
        package.clear_formula_caches()
        pruned_shared_strings = package.prune_shared_strings()
        scrubbed_properties = package.scrub_document_properties()
        removed_custom_parts = package.remove_embedded_custom_data()
        package.enable_full_calculation()
        package.save(candidate_path)

        candidate_book = openpyxl.load_workbook(
            candidate_path,
            data_only=False,
            keep_links=True,
        )
        try:
            etalon_book = openpyxl.load_workbook(
                etalon_path,
                data_only=False,
                keep_links=True,
            )
            try:
                findings = compare_with_etalon(candidate_book, etalon_book)
            finally:
                etalon_book.close()
            if template_id == "aosr_vl":
                findings["reviewed_formula_difference_count"] = findings[
                    "candidate_vs_etalon_formula_differences"
                ]
                findings["unreviewed_formula_difference_count"] = 0
                findings["formula_difference_review_basis"] = (
                    "blank guards, repaired sequential references, removed broken hidden formulas, "
                    "and the pre-existing ETALON literal/formula layout differences"
                )
            remaining_sensitive = []
            remaining_external_formula_references = 0
            unsafe_blank_formulas = unsafe_blank_formula_examples(candidate_book)
            for worksheet in candidate_book.worksheets:
                for row in worksheet.iter_rows():
                    for cell in row:
                        if is_formula(cell.value) and re.search(
                            r"\[[1-9][0-9]*\]",
                            cell.value,
                        ):
                            remaining_external_formula_references += 1
                        if (
                            cell.value not in (None, "")
                            and not is_formula(cell.value)
                            and not cell.hyperlink
                            and looks_project_specific(cell.value)
                            and not (
                                template_id == "aosr_vl"
                                and worksheet.title.startswith("АОСР")
                                and cell.coordinate == "AJ1"
                            )
                        ):
                            remaining_sensitive.append(
                                f"{worksheet.title}!{cell.coordinate}"
                            )
            findings.update(
                {
                    "target_derivation": (
                        "source_structure_plus_reviewed_aosr_and_pdf_role_overrides"
                        if template_id == "aosr_vl"
                        else "source_structure_plus_reviewed_pdf_role_overrides"
                    ),
                    "value_source_policy": "uploaded_pdf_only",
                    "project_basis_target_count": sum(bool(field.get("allow_project_basis")) for field in fields),
                    "reviewed_material_target_count": len(material_overrides),
                    "discovery_target_count": len(fields),
                    "cleared_cell_count": sum(
                        len(items) for items in clear_targets.values()
                    ),
                    "localized_external_formula_references": localized_references,
                    "removed_external_links": removed_external_links,
                    "removed_broken_defined_names": (
                        removed_broken_defined_names
                    ),
                    "removed_broken_data_validations": (
                        removed_broken_data_validations
                    ),
                    "pruned_shared_string_count": pruned_shared_strings,
                    "scrubbed_document_property_count": scrubbed_properties,
                    "removed_custom_part_count": removed_custom_parts,
                    "source_external_links": source_external_links,
                    "candidate_external_links": len(
                        getattr(candidate_book, "_external_links", [])
                    ),
                    "remaining_external_formula_reference_count": (
                        remaining_external_formula_references
                    ),
                    "remaining_sensitive_value_count": len(remaining_sensitive),
                    "remaining_sensitive_value_examples": remaining_sensitive[:25],
                    "renamed_sheet_count": len(sheet_renames),
                    "renamed_candidate_sheets": sorted(sheet_renames.values()),
                }
            )
            if template_id == "aosr_vl":
                findings.update(
                    {
                        "cleanup_only_cell_count": sum(
                            len(items) for items in cleanup_only_targets.values()
                        ),
                        "blank_preserving_formula_count": blank_preserving_formulas,
                        "formula_override_count": formula_overrides,
                        "cleared_broken_formula_count": sum(
                            len(items)
                            for items in AOSR_VL_BROKEN_FORMULA_CELLS.values()
                        ),
                        "unsafe_blank_formula_count": len(unsafe_blank_formulas),
                        "unsafe_blank_formula_examples": unsafe_blank_formulas[:25],
                    }
                )
        finally:
            candidate_book.close()
        findings.update(raw_package_findings(candidate_path))

        contract = {
            "template_id": template_id,
            "display_name": display_name,
            "document_kind": document_kind,
            "version": AOSR_VL_VERSION if template_id == "aosr_vl" else VERSION,
            "status": "DISCOVERY_REVIEW_REQUIRED",
            "approved": False,
            "source_template": str(source_path.relative_to(ROOT)),
            "source_sha256": digest(source_path),
            "etalon_example": str(etalon_path.relative_to(ROOT)),
            "etalon_sha256": digest(etalon_path),
            "candidate_template": f"templates/approved/{filename}",
            "candidate_sha256": digest(candidate_path),
            "output_filename": filename,
            "warning_fill_rgb": "FFFFE699",
            "structural_findings": findings,
            "fields": fields,
        }
        contract_path = contracts_dir / f"{template_id}.yaml"
        contract_path.write_text(
            yaml.safe_dump(
                contract,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            ),
            encoding="utf-8",
        )
        return {
            "template_id": template_id,
            "candidate_path": candidate_path,
            "contract_path": contract_path,
            "fields": len(fields),
            "manual": sum(bool(item["manual_reason"]) for item in fields),
            "formula_errors": findings["formula_errors_observed"],
            "external_links": findings["candidate_external_links"],
            "remaining_sensitive": findings["remaining_sensitive_value_count"],
        }
    finally:
        source_book.close()


def run_registration(
    *,
    approved_dir: Path,
    contracts_dir: Path,
    template_ids: set[str] | None = None,
) -> list[dict]:
    return [
        register(
            *item,
            approved_dir=approved_dir,
            contracts_dir=contracts_dir,
        )
        for item in TEMPLATES
        if template_ids is None or item[0] in template_ids
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build non-approved selected-template discovery candidates from "
            "NEW_TEMPLATES without using ETALON values as writable mappings."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Regenerate in a temporary directory and compare candidates and contracts read-only.",
    )
    parser.add_argument(
        "--template-id",
        choices=[item[0] for item in TEMPLATES],
        action="append",
        help="Regenerate or check only the selected template id (repeatable).",
    )
    args = parser.parse_args()
    template_ids = set(args.template_id) if args.template_id else None
    if args.check:
        with tempfile.TemporaryDirectory(prefix="selected-template-check-") as temporary:
            temporary_root = Path(temporary)
            results = run_registration(
                approved_dir=temporary_root / "approved",
                contracts_dir=temporary_root / "contracts",
                template_ids=template_ids,
            )
            changed = []
            for result in results:
                registered_candidate = APPROVED_DIR / result["candidate_path"].name
                registered_contract = CONTRACTS_DIR / result["contract_path"].name
                if (
                    not registered_candidate.is_file()
                    or digest(registered_candidate)
                    != digest(result["candidate_path"])
                    or not registered_contract.is_file()
                    or registered_contract.read_bytes()
                    != result["contract_path"].read_bytes()
                ):
                    changed.append(result["template_id"])
            if changed:
                raise SystemExit(
                    f"Зарегистрированные кандидаты устарели: {', '.join(changed)}"
                )
    else:
        results = run_registration(
            approved_dir=APPROVED_DIR,
            contracts_dir=CONTRACTS_DIR,
            template_ids=template_ids,
        )
    for result in results:
        print(
            f"{result['template_id']}: fields={result['fields']}, "
            f"manual={result['manual']}, formula_errors={result['formula_errors']}, "
            f"external_links={result['external_links']}, "
            f"remaining_sensitive={result['remaining_sensitive']}"
        )


if __name__ == "__main__":
    main()
