from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from lxml import html as html_parser

from executive_docs.domain import JobStatus, ProjectState


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "src" / "executive_docs" / "templates"


def environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(("html",)),
    )


def test_index_wizard_renders_required_inputs_and_steps() -> None:
    html = environment().get_template("index.html").render(
        jobs=[],
        agent_mode="heuristic",
        model="test-model",
        processing_profile="balanced",
        today_iso="2026-07-27",
    )
    assert 'data-step-panel="object"' in html
    assert 'data-step-panel="files"' in html
    assert 'data-step-panel="check"' in html
    assert html.count('name="files"') == 3
    assert 'id="project-file"' in html and 'id="facts-file"' in html
    assert 'name="processing_profile"' in html
    document = html_parser.fromstring(html)
    assert "required" in document.get_element_by_id("project-file").attrib
    assert document.get_element_by_id("facts-file").get("required") is None
    assert "Необязательно" in document.get_element_by_id("facts-file").getprevious().text_content()


def test_job_page_renders_manager_review_surfaces() -> None:
    state = ProjectState(
        job_id="44444444-4444-4444-4444-444444444444",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
        status=JobStatus.NEEDS_INPUT,
    )
    html = environment().get_template("job.html").render(job=state)
    assert 'id="questions"' in html
    assert 'id="previews"' in html
    assert 'id="review"' in html
    assert 'id="download"' in html
    assert 'id="retry-analysis"' in html
    assert 'id="missing-warning"' in html
    assert "Комплект 44444444" not in html
    assert "Решение специалиста" in html


def test_recent_job_link_uses_public_reference_instead_of_uuid() -> None:
    state = ProjectState(
        job_id="44444444-4444-4444-4444-444444444444",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
        status=JobStatus.NEEDS_INPUT,
        created_at="2026-07-27T08:18:23.110361+00:00",
    )
    html = environment().get_template("index.html").render(
        jobs=[state],
        agent_mode="heuristic",
        model="test-model",
        processing_profile="balanced",
        today_iso="2026-07-27",
    )
    assert f'href="/kits/{state.public_ref}"' in html
    assert f'href="/jobs/{state.job_id}"' not in html


def test_needs_input_controls_are_optional_text_or_yes_no() -> None:
    script = (ROOT / "src" / "executive_docs" / "static" / "job.js").read_text(encoding="utf-8")
    assert 'option value="YES"' in script
    assert 'option value="NO"' in script
    assert "Необязательно. Введите подтверждённые сведения" in script
    assert 'data-comment="' not in script
