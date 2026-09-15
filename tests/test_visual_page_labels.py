from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PageObject, PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, RectangleObject

from executive_docs.domain import Artifact
from executive_docs.ingestion import (
    EXTRACTOR_VERSION,
    VISUAL_PAGE_LABEL_HEIGHT,
    VISUAL_PAGE_LABEL_VERSION,
    _build_segments,
    _pdf_layout_text,
    _pdf_subset,
    _selected_template_text_score,
    build_compact_evidence,
    select_visual_sources,
    source_index,
    read_indexed_source,
)


def _page(number: int, *, rotation: int = 0, cropped: bool = False) -> PageObject:
    page = PageObject.create_blank_page(width=300, height=400)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/TestFont"): DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }),
        }),
    })
    content = DecodedStreamObject()
    content.set_data((
        "q 0.2 0.4 0.7 rg 25 35 190 250 re f Q "
        f"BT /TestFont 12 Tf 35 260 Td (Source page {number}) Tj ET "
        "BT /TestFont 12 Tf 35 55 Td (Bottom edge) Tj ET"
    ).encode("ascii"))
    page[NameObject("/Contents")] = content
    if cropped:
        page.cropbox = RectangleObject((20, 30, 220, 290))
    if rotation:
        page.rotate(rotation)
    return page


def _source(path: Path, count: int = 8, *, rotation: int = 0, cropped: bool = False) -> Artifact:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for number in range(1, count + 1):
        writer.add_page(_page(number, rotation=rotation, cropped=cropped))
    with path.open("wb") as stream:
        writer.write(stream)
    data = path.read_bytes()
    return Artifact(id="source", original_name=path.name, stored_name=path.name,
                    media_type="application/pdf", size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                    pages=count, category="project")


def test_subset_labels_use_original_not_subset_ordinals_and_preserve_source(tmp_path):
    source = tmp_path / "input.pdf"
    _source(source)
    before = source.read_bytes()
    output = _pdf_subset(source, tmp_path / "subset.pdf", [4, 7], label_original_pages=True)
    reader = PdfReader(output)
    assert len(reader.pages) == 2
    for page, original in zip(reader.pages, [4, 7], strict=True):
        assert f"Original PDF page: {original}" in page.extract_text()
        assert f"Source page {original}" in page.extract_text()
        assert "Bottom edge" in page.extract_text()
        assert float(page.mediabox.height) == 400 + VISUAL_PAGE_LABEL_HEIGHT
        assert float(page.mediabox.width) == 300
        assert page.rotation == 0
    assert source.read_bytes() == before
    assert reader.metadata["/ExecutiveDocsVisualVersion"] == VISUAL_PAGE_LABEL_VERSION
    assert json.loads(reader.metadata["/ExecutiveDocsVisualPages"]) == [4, 7]


def test_same_length_legacy_or_other_page_subset_cache_is_not_reused(tmp_path):
    source = tmp_path / "input.pdf"
    _source(source)
    output = _pdf_subset(source, tmp_path / "subset.pdf", [1, 2])
    assert "Original PDF page:" not in PdfReader(output).pages[0].extract_text()
    _pdf_subset(source, output, [4, 7], label_original_pages=True)
    assert "Original PDF page: 4" in PdfReader(output).pages[0].extract_text()
    before = output.stat().st_mtime_ns
    _pdf_subset(source, output, [4, 7], label_original_pages=True)
    assert output.stat().st_mtime_ns == before
    _pdf_subset(source, output, [3, 8], label_original_pages=True)
    assert "Original PDF page: 8" in PdfReader(output).pages[1].extract_text()


def test_selected_full_pdf_is_labeled_and_legacy_full_pdf_remains_original(tmp_path):
    artifact = _source(tmp_path / "input" / "project.pdf", count=2)
    original = (tmp_path / "input" / artifact.stored_name).read_bytes()
    selected = select_visual_sources(tmp_path, [artifact], max_pages=2, include_project=True, selected_template=True)
    assert selected[0]["path"] != tmp_path / "input" / artifact.stored_name
    assert selected[0]["pages"] == [1, 2]
    assert "Original PDF page: 2" in PdfReader(selected[0]["path"]).pages[1].extract_text()
    legacy = select_visual_sources(tmp_path, [artifact], max_pages=2, include_project=True)
    assert legacy[0]["path"] == tmp_path / "input" / artifact.stored_name
    assert (tmp_path / "input" / artifact.stored_name).read_bytes() == original


@pytest.mark.parametrize("page", [0, 9])
def test_labeled_subset_rejects_out_of_range_pages(tmp_path, page):
    source = tmp_path / "input.pdf"
    _source(source)
    with pytest.raises(ValueError, match="outside the source PDF"):
        _pdf_subset(source, tmp_path / "subset.pdf", [page], label_original_pages=True)


def _raster(path: Path) -> tuple[int, int, bytes]:
    pdfium = pytest.importorskip("pypdfium2", reason="Optional PDFium viewport raster QA")
    document = pdfium.PdfDocument(path)
    try:
        page = document[0]
        bitmap = page.render(scale=1)
        image = bitmap.to_pil().convert("RGB")
        return image.width, image.height, image.tobytes()
    finally:
        document.close()


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("cropped", [False, True])
def test_header_preserves_crop_and_rotation_geometry(tmp_path, rotation, cropped):
    source = tmp_path / "input.pdf"
    _source(source, count=1, rotation=rotation, cropped=cropped)
    output = _pdf_subset(source, tmp_path / "labeled.pdf", [1], label_original_pages=True)
    original = PdfReader(source).pages[0]
    labeled = PdfReader(output).pages[0]
    expected_width, expected_height = float(original.cropbox.width), float(original.cropbox.height)
    if rotation in (90, 270):
        expected_width, expected_height = expected_height, expected_width
    assert float(labeled.cropbox.width) == pytest.approx(expected_width)
    assert float(labeled.cropbox.height) == pytest.approx(expected_height + VISUAL_PAGE_LABEL_HEIGHT)
    assert labeled.rotation == 0
    assert "Source page 1" in labeled.extract_text()
    assert "Bottom edge" in labeled.extract_text()
    assert "Original PDF page: 1" in labeled.extract_text()
    # Optional bundled PDFium integration check. Normal CI needs no additional
    # rendering dependency and covers the page geometry/content above.
    if os.environ.get("EXECUTIVE_DOCS_VISUAL_RASTER_QA") != "1":
        return
    width, height, pixels = _raster(source)
    out_width, out_height, out_pixels = _raster(output)
    assert out_width == width
    assert out_height == height + VISUAL_PAGE_LABEL_HEIGHT
    assert out_pixels[width * VISUAL_PAGE_LABEL_HEIGHT * 3:] == pixels


def test_layout_is_supplemental_and_old_extraction_cache_is_invalidated(tmp_path):
    artifact = _source(tmp_path / "input" / "project.pdf", count=1)
    cache = tmp_path / "extracted"
    cache.mkdir()
    (cache / f"{artifact.sha256}-3.json").write_text(json.dumps({
        "extractor_version": "3", "sha256": artifact.sha256, "segments": [{"text": "old"}],
    }))
    result = source_index(tmp_path, artifact)
    assert EXTRACTOR_VERSION != "3"
    assert "Source page 1" in result["segments"][0]["text"]
    assert "Source page 1" in result["segments"][0]["layout_text"]
    assert (cache / f"{artifact.sha256}-{EXTRACTOR_VERSION}.json").is_file()


@pytest.mark.parametrize("failure", ["exception", "rotation_warning"])
def test_layout_failure_keeps_plain_extraction_and_visual_policy(tmp_path, monkeypatch, failure):
    def extract_text(**kwargs):
        if kwargs:
            if failure == "exception":
                raise ValueError("unsupported geometry")
            logging.getLogger("pypdf.layout").warning("Rotated text discovered. Layout is degraded.")
            return "unsafe layout"
        return "Original plain text remains available and unchanged. " * 3
    monkeypatch.setattr("executive_docs.ingestion.PdfReader", lambda _: SimpleNamespace(
        is_encrypted=False, pages=[SimpleNamespace(extract_text=extract_text)],
    ))
    segments, _ = _build_segments(tmp_path / "project.pdf")
    assert segments[0]["text"] == extract_text()
    assert segments[0]["layout_text"] is None
    assert segments[0]["layout_text_reliable"] is False
    assert segments[0]["text_reliable"] is True
    assert segments[0]["visual_required"] is False


def test_layout_is_size_bounded():
    page = SimpleNamespace(extract_text=lambda **_: "X" * 50_000)
    assert len(_pdf_layout_text(page)) == 25_000


def test_selected_source_read_keeps_available_layout_for_truncated_table_followup(tmp_path, monkeypatch):
    artifact = _source(tmp_path / "input" / "project.pdf", count=1)
    monkeypatch.setattr("executive_docs.ingestion.source_index", lambda *_: {"pages": 1, "segments": [{
        "page": 1, "locator": "page:1", "text": "Cable m791,24", "text_reliable": True,
        "layout_text": "Cable       m       79       1,24", "layout_text_reliable": True,
    }]})
    selected, _ = read_indexed_source(tmp_path, artifact, include_layout=True)
    assert "Cable       m       79       1,24" in selected
    assert "Cable m791,24" in selected
    legacy, _ = read_indexed_source(tmp_path, artifact)
    assert "LAYOUT EXTRACT" not in legacy


def test_upright_layout_survives_documented_skipped_rotated_stamp_warning(tmp_path, monkeypatch):
    def extract_text(**kwargs):
        if kwargs:
            assert kwargs["layout_mode_strip_rotated"] is True
            logging.getLogger("pypdf.layout").warning("Rotated text discovered. Output will be incomplete.")
            return "Upright material row m 79 1,24"
        return "Upright material row m791,24 plus rotated stamp"
    monkeypatch.setattr("executive_docs.ingestion.PdfReader", lambda _: SimpleNamespace(
        is_encrypted=False, pages=[SimpleNamespace(extract_text=extract_text)],
    ))
    segments, _ = _build_segments(tmp_path / "project.pdf")
    assert segments[0]["text"] == extract_text()
    assert segments[0]["layout_text"] == "Upright material row m 79 1,24"
    assert segments[0]["layout_text_reliable"] is True
    assert segments[0]["layout_text_partial"] is True
    assert segments[0]["layout_text_warnings"] == ["Rotated text discovered. Output will be incomplete."]


def _segment(page, text, *, reliable=True, layout=None):
    return {"page": page, "locator": f"page:{page}", "text": text,
            "text_reliable": reliable, "visual_required": not reliable, "score": 10,
            "layout_text": layout, "layout_text_reliable": bool(layout)}


def test_selected_text_routes_late_tables_before_36_scans_without_32_page_cap(tmp_path, monkeypatch):
    artifact = _source(tmp_path / "input" / "project.pdf", count=1)
    segments = [_segment(page, "Broken duplicate scan text " * 20, reliable=False) for page in range(1, 37)]
    segments += [_segment(page, "Readable project explanation. " * 20) for page in range(37, 67)]
    segments[61] = _segment(62, "Спецификация материалов и оборудования\nCable m791,24", layout="Спецификация материалов и оборудования\nCable       m  79  1,24")
    segments[62] = _segment(63, "Ведомость объемов работ\nУстройство опор шт. 12")
    index = {"segments": segments, "pages": 66, "scope": "unknown"}
    monkeypatch.setattr("executive_docs.ingestion.source_index", lambda *_: index)
    packet = build_compact_evidence(tmp_path, [artifact], 70_000, selected_template=True)
    assert len(packet) > 32
    assert {"page:62", "page:63"}.issubset({item["locator"] for item in packet[:3]})
    assert len(json.dumps(packet, ensure_ascii=False)) <= 70_000
    assert next(item for item in packet if item["locator"] == "page:62")["layout_text"].endswith("m  79  1,24")
    assert len(index["segments"]) == 66
    reversed_index = {**index, "segments": list(reversed(segments))}
    monkeypatch.setattr("executive_docs.ingestion.source_index", lambda *_: reversed_index)
    assert build_compact_evidence(tmp_path, [artifact], 70_000, selected_template=True) == packet


@pytest.mark.parametrize("budget", [0, 100, 550, 2000])
def test_selected_packet_counts_layout_and_escaped_text_within_budget(tmp_path, monkeypatch, budget):
    artifact = _source(tmp_path / "input" / "project.pdf", count=1)
    segment = _segment(1, "\x01\x02\n" * 2000, reliable=False, layout="Cable m 79 1,24 " * 2000)
    monkeypatch.setattr("executive_docs.ingestion.source_index", lambda *_: {"segments": [segment], "scope": "unknown"})
    packet = build_compact_evidence(tmp_path, [artifact], budget, selected_template=True)
    assert not packet or len(json.dumps(packet, ensure_ascii=False)) <= budget


def test_selected_visual_optional_table_beats_legacy_kl_boost_and_keeps_scan(tmp_path, monkeypatch):
    artifact = _source(tmp_path / "input" / "project.pdf", count=3)
    segments = [_segment(1, "Scan", reliable=False),
                _segment(2, "КЛ-6 кВ кабельная линия " * 50),
                _segment(3, "Спецификация материалов. Количество. ВЛ 0,4 кВ")]
    monkeypatch.setattr("executive_docs.ingestion.source_index", lambda *_: {"segments": segments, "pages": 3, "scope": "unknown"})
    selected = select_visual_sources(tmp_path, [artifact], max_pages=2, include_project=True, selected_template=True)
    assert selected[0]["pages"] == [1, 3]
    assert "Original PDF page: 3" in PdfReader(selected[0]["path"]).pages[1].extract_text()
    assert _selected_template_text_score(segments[2]) > _selected_template_text_score(segments[1])
    with pytest.raises(ValueError, match="1 страниц"):
        select_visual_sources(tmp_path, [artifact], max_pages=0, include_project=True, selected_template=True)
