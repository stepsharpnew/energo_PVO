from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

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
    assert "Решение специалиста" in html
