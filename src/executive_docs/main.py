from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import settings
from .domain import AnswersRequest, CorrectionReviewRequest, JobStatus, ProjectState, ReviewRequest
from .packaging import build_result_zip, write_report
from .pipeline import JobQueue, Pipeline
from .repository import Repository
from .storage import Storage


settings.ensure_directories()
repository = Repository(settings.db_path)
storage = Storage(settings)
pipeline = Pipeline(settings, repository, storage)
queue = JobQueue(pipeline)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    repository.initialize()
    await queue.start()
    for job_id in repository.recoverable_jobs():
        await queue.enqueue(job_id)
    yield
    await queue.stop()


app = FastAPI(title="ИИ-агент исполнительной документации", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


def get_job_or_404(job_id: str) -> ProjectState:
    state = repository.get(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Задание не найдено")
    return state


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    default_policy = settings.policy(settings.processing_profile)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "jobs": repository.list(),
            "agent_mode": settings.agent_mode,
            "model": default_policy.analysis_model,
            "processing_profile": default_policy.name,
        },
    )


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_page(request: Request, job_id: str):
    return templates.TemplateResponse(request=request, name="job.html", context={"job": get_job_or_404(job_id)})


@app.post("/api/jobs")
async def create_job(
    request: Request,
    branch_id: str = Form(...),
    first_aosr_number: int = Form(...),
    operator_name: str = Form(...),
    processing_profile: str = Form(settings.processing_profile),
    files: list[UploadFile] = File(...),
):
    if branch_id not in {"khimki", "solnechnogorsk"}:
        raise HTTPException(status_code=422, detail="Неизвестный филиал")
    if first_aosr_number < 1:
        raise HTTPException(status_code=422, detail="Первый номер должен быть положительным")
    if not operator_name.strip():
        raise HTTPException(status_code=422, detail="Укажите специалиста")
    if processing_profile not in {"economy", "balanced", "quality"}:
        raise HTTPException(status_code=422, detail="Неизвестный профиль расхода")
    if not files:
        raise HTTPException(status_code=422, detail="Добавьте исходные файлы")
    job_id = str(uuid.uuid4())
    storage.initialize_job(job_id)
    artifacts = []
    try:
        for upload in files:
            artifacts.append(storage.save_upload(job_id, upload.filename or "file", upload.file, upload.content_type or ""))
        if sum(item.size for item in artifacts) > settings.max_job_bytes:
            raise ValueError("Общий объём задания превышает лимит")
        state = ProjectState(
            job_id=job_id,
            branch_id=branch_id,
            first_aosr_number=first_aosr_number,
            operator_name=operator_name.strip(),
            processing_profile=processing_profile,
            status=JobStatus.FILES_UPLOADED,
            artifacts=artifacts,
        )
        repository.create(state)
        await queue.enqueue(job_id)
    except Exception as exc:
        storage.remove_job(job_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(state.model_dump(mode="json"), status_code=202)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.get("/api/jobs")
async def list_jobs():
    return [item.model_dump(mode="json") for item in repository.list()]


@app.get("/api/corrections")
async def list_corrections(job_id: str | None = None):
    if job_id:
        get_job_or_404(job_id)
    return repository.list_corrections(job_id)


@app.post("/api/corrections/{correction_id}/review")
async def review_correction(correction_id: int, payload: CorrectionReviewRequest):
    if not payload.reviewed_by.strip() or not payload.comment.strip():
        raise HTTPException(status_code=422, detail="Укажите проверяющего и комментарий")
    try:
        result = repository.review_correction(
            correction_id,
            status="APPROVED" if payload.action == "approve" else "REJECTED",
            reviewed_by=payload.reviewed_by.strip(),
            comment=payload.comment.strip(),
            regression_passed=payload.regression_passed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Предложение не найдено")
    return result


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    return get_job_or_404(job_id).model_dump(mode="json")


@app.post("/api/jobs/{job_id}/answers")
async def answer_questions(job_id: str, payload: AnswersRequest):
    state = get_job_or_404(job_id)
    if state.status != JobStatus.NEEDS_INPUT:
        raise HTTPException(status_code=409, detail="Задание не ожидает ответов")
    by_id = {item.id: item for item in state.questions}
    for answer in payload.answers:
        if answer.question_id not in by_id:
            raise HTTPException(status_code=422, detail=f"Неизвестный вопрос {answer.question_id}")
        question = by_id[answer.question_id]
        question.answer = answer.value.strip()
        question.comment = answer.comment.strip()
        question.confirmed_by = answer.confirmed_by.strip()
        if not question.confirmed_by:
            raise HTTPException(status_code=422, detail=f"Укажите, кто подтвердил ответ {answer.question_id}")
        from .domain import utc_now

        question.answered_at = utc_now()
    unanswered = [item for item in state.questions if item.required and not item.answer]
    if unanswered:
        raise HTTPException(status_code=422, detail="Ответьте на все обязательные вопросы")
    state.status = JobStatus.FILES_UPLOADED
    repository.save(state)
    await queue.enqueue(job_id)
    return state.model_dump(mode="json")


@app.get("/api/jobs/{job_id}/preview")
async def preview(job_id: str):
    root = storage.job_dir(job_id)
    state = get_job_or_404(job_id)
    files = [
        path.relative_to(root).as_posix()
        for path in sorted((root / "preview" / f"r{state.revision}").glob("*.pdf"))
    ]
    return {"files": files}


@app.get("/api/jobs/{job_id}/files/{relative_path:path}")
async def job_file(job_id: str, relative_path: str):
    get_job_or_404(job_id)
    root = storage.job_dir(job_id).resolve()
    path = (root / relative_path).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(path)


@app.post("/api/jobs/{job_id}/review")
async def review(job_id: str, payload: ReviewRequest):
    state = get_job_or_404(job_id)
    if payload.action == "approve":
        if state.status != JobStatus.READY_FOR_REVIEW or any(i.severity == "error" for i in state.validation_issues):
            raise HTTPException(status_code=409, detail="Комплект не готов к утверждению")
        state.status = JobStatus.APPROVED_FINAL
        state.summary = "Комплект подтверждён специалистом и готов к подписанию"
        repository.save(state)
        write_report(state, storage.job_dir(job_id))
        state.result_zip = str(build_result_zip(state, storage.job_dir(job_id)).relative_to(storage.job_dir(job_id)))
        repository.save(state)
    elif payload.action == "request_revision":
        if not payload.corrections:
            raise HTTPException(status_code=422, detail="Опишите хотя бы одно исправление")
        if any(not item.expected_value.strip() or not item.reason.strip() for item in payload.corrections):
            raise HTTPException(status_code=422, detail="Укажите правильное значение и причину исправления")
        state.corrections.extend(payload.corrections)
        repository.add_corrections(job_id, state.revision, payload.corrections)
        state.revision += 1
        state.status = JobStatus.FILES_UPLOADED
        state.validation_issues = []
        state.result_zip = None
        repository.save(state)
        await queue.enqueue(job_id)
    else:
        state.status = JobStatus.CANCELLED
        repository.save(state)
    return state.model_dump(mode="json")


@app.get("/api/jobs/{job_id}/download")
async def download(job_id: str):
    state = get_job_or_404(job_id)
    if state.status != JobStatus.APPROVED_FINAL or not state.result_zip:
        raise HTTPException(status_code=409, detail="Финальный комплект ещё не утверждён")
    path = storage.job_dir(job_id) / state.result_zip
    if not path.exists():
        raise HTTPException(status_code=404, detail="Архив не найден")
    return FileResponse(path, media_type="application/zip", filename=path.name)


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    get_job_or_404(job_id)
    repository.delete(job_id)
    storage.remove_job(job_id)
    return JSONResponse({"deleted": job_id})


def run() -> None:
    uvicorn.run("executive_docs.main:app", host=settings.host, port=settings.port, workers=1)


if __name__ == "__main__":
    run()
