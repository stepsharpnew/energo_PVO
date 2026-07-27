const terminal = new Set([
  "READY_FOR_REVIEW",
  "APPROVED_FINAL",
  "FAILED_ANALYSIS",
  "FAILED_GENERATION",
  "FAILED_VALIDATION",
  "CANCELLED",
  "REVISION_REQUIRED",
]);
const statusLabels = {
  CREATED: ["Создаём комплект", "Задание зарегистрировано"],
  FILES_UPLOADED: ["Комплект в очереди", "Файлы приняты и ожидают обработки"],
  ANALYZING: ["Агент изучает проект", "Классифицируем файлы и извлекаем подтверждённые факты"],
  NEEDS_INPUT: ["Есть предупреждения", "Уточните доступные сведения перед финальным выпуском"],
  GENERATING: ["Формируем АОСР", "Заполняем утверждённые Excel-шаблоны"],
  VALIDATING: ["Проверяем комплект", "Техническая, смысловая и визуальная проверка"],
  READY_FOR_REVIEW: ["Проверьте комплект", "Документы готовы к решению специалиста"],
  APPROVED_FINAL: ["Комплект готов", "Подтверждён специалистом и собран для подписания"],
  REVISION_REQUIRED: ["Нужна новая ревизия", "Исправление сохранено"],
  FAILED_ANALYSIS: ["Анализ остановлен", "Проверьте сообщение об ошибке"],
  FAILED_GENERATION: ["Формирование остановлено", "Проверьте сообщение об ошибке"],
  FAILED_VALIDATION: ["Есть замечания", "Комплект не прошёл одну или несколько проверок"],
  CANCELLED: ["Задание отменено", "Обработка остановлена"],
};
const profileLabels = {
  economy: "Экономно",
  balanced: "Баланс",
  quality: "Тщательно",
};

const show = (id, on = true) => document.getElementById(id).classList.toggle("hidden", !on);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>'"]/g,
    (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]
  );
const safePath = (value) => String(value).split("/").map(encodeURIComponent).join("/");
const publicText = (value) =>
  String(value ?? "")
    .replace(/\s*\(\s*SHA-?256\s*[:=]?\s*[0-9a-f]{64}\s*\)/gi, "")
    .replace(/\b(?:SHA-?256\s*[:=]?\s*)?[0-9a-f]{64}\b/gi, "")
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, "")
    .replace(/\b(?:файл|file)\s+[0-9a-f]{8}\b/gi, "загруженный файл")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
const yesNoQuestion = (question) => question.field_key.toLowerCase().includes("change_state");
let currentJob = null;
let refreshTimer = null;

async function api(url, options = {}) {
  const headers = options.body ? { "Content-Type": "application/json" } : {};
  const response = await fetch(url, { ...options, headers: { ...headers, ...(options.headers || {}) } });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail || detail;
    } catch {
      // Keep HTTP status text when a non-JSON error is returned.
    }
    throw new Error(detail);
  }
  return response.json();
}

function updateStatus(job) {
  const draftWithWarnings = job.status === "NEEDS_INPUT" && job.draft_report_ready;
  const [title, fallbackSummary] = draftWithWarnings
    ? ["Черновой отчёт", "Отчёт сформирован с предупреждениями"]
    : statusLabels[job.status] || [job.status, "Состояние обновлено"];
  document.getElementById("status").textContent = title;
  document.getElementById("summary").textContent = publicText(job.summary || job.error || fallbackSummary);
  document.getElementById("status-pill").textContent = title;
  const pill = document.getElementById("status-pill");
  pill.className = "status-pill";
  if (["NEEDS_INPUT", "FAILED_VALIDATION"].includes(job.status)) pill.classList.add("is-warning");
  if (["FAILED_ANALYSIS", "FAILED_GENERATION", "CANCELLED"].includes(job.status)) {
    pill.classList.add("is-error");
  }
  if (job.status === "APPROVED_FINAL") pill.classList.add("is-success");

  const check = document.getElementById("step-check");
  const release = document.getElementById("step-release");
  check.classList.toggle("is-complete", job.status === "APPROVED_FINAL" || draftWithWarnings);
  check.classList.toggle("is-active", job.status !== "APPROVED_FINAL" && !draftWithWarnings);
  release.classList.toggle(
    "is-active",
    ["READY_FOR_REVIEW", "APPROVED_FINAL"].includes(job.status) || draftWithWarnings
  );
  release.classList.toggle("is-complete", job.status === "APPROVED_FINAL");
  document.getElementById("step-check-copy").textContent =
    draftWithWarnings
      ? "Завершена с замечаниями"
      : job.status === "NEEDS_INPUT"
      ? "Есть предупреждения"
      : job.status === "APPROVED_FINAL"
        ? "Пройдена"
        : "В процессе";
  document.getElementById("step-release-copy").textContent =
    draftWithWarnings
      ? "Черновой отчёт"
      : job.status === "APPROVED_FINAL"
      ? "Комплект готов"
      : job.status === "READY_FOR_REVIEW"
        ? "Решение специалиста"
        : "Ожидает проверки";
}

function updateUsage(job) {
  document.getElementById("profile").textContent =
    profileLabels[job.processing_profile] || job.processing_profile;
  const usage = job.model_usage || [];
  const input = usage.reduce((sum, item) => sum + (item.input_tokens || 0), 0);
  const cached = usage.reduce((sum, item) => sum + (item.cached_tokens || 0), 0);
  const output = usage.reduce((sum, item) => sum + (item.output_tokens || 0), 0);
  const unknownCost = usage.some((item) => item.estimated_cost_usd === null);
  const knownCost = usage.reduce((sum, item) => sum + (item.estimated_cost_usd || 0), 0);
  const costLabel = unknownCost ? "оценка стоимости недоступна" : `около $${knownCost.toFixed(3)}`;
  document.getElementById("usage-summary").textContent = usage.length
    ? `${usage.length} выз. · вход ${input.toLocaleString("ru-RU")} · кэш ${cached.toLocaleString(
        "ru-RU"
      )} · выход ${output.toLocaleString("ru-RU")} · ${costLabel}`
    : "Платных вызовов пока не было.";
}

async function refresh() {
  window.clearTimeout(refreshTimer);
  const job = await api(`/api/kits/${jobRef}`);
  currentJob = job;
  document.getElementById("revision").textContent = job.revision;
  updateStatus(job);
  updateUsage(job);
  const draftWithWarnings = job.status === "NEEDS_INPUT" && job.draft_report_ready;

  show(
    "progress",
    !terminal.has(job.status) && !["NEEDS_INPUT", "READY_FOR_REVIEW", "APPROVED_FINAL"].includes(job.status)
  );

  show("questions", job.status === "NEEDS_INPUT" && !draftWithWarnings);
  show("draft-report", draftWithWarnings);
  show("retry-analysis", job.status === "FAILED_ANALYSIS");
  if (job.status === "NEEDS_INPUT") {
    const unresolved = job.questions.filter((question) => !question.answer);
    document.getElementById("draft-warning-title").textContent =
      `Замечаний к отчёту: ${unresolved.length}`;
    document.getElementById("draft-warning-list").innerHTML = unresolved
      .map(
        (question) => `
          <article class="draft-warning-item">
            <strong>${esc(publicText(question.prompt))}</strong>
            <p>${esc(publicText(question.reason))}</p>
            <span>Не заполнено — требуется исправить перед финальным выпуском</span>
          </article>`
      )
      .join("");
    document.getElementById("missing-warning-title").textContent =
      unresolved.length > 0
        ? `Нужно проверить полей: ${unresolved.length}`
        : "Все доступные ответы заполнены";
    document.getElementById("missing-warning-copy").textContent =
      unresolved.length > 0
        ? "Их можно оставить пустыми и сохранить форму. Пока предупреждения не устранены, финальный выпуск останется недоступен."
        : "После сохранения агент продолжит обработку комплекта.";
    document.getElementById("question-list").innerHTML = job.questions
      .map(
        (question) => {
          const isYesNo = yesNoQuestion(question);
          const prompt = isYesNo
            ? "Были ли изменения относительно рабочего проекта?"
            : publicText(question.prompt);
          const control = isYesNo
            ? `<select name="${esc(question.id)}">
                <option value="">Не указано</option>
                <option value="YES" ${question.answer === "YES" ? "selected" : ""}>Да</option>
                <option value="NO" ${question.answer === "NO" ? "selected" : ""}>Нет</option>
              </select>`
            : `<textarea name="${esc(question.id)}" placeholder="Необязательно. Введите подтверждённые сведения при наличии">${esc(
                question.answer
              )}</textarea>`;
          return `
            <label class="question-item ${question.answer ? "is-complete" : "is-missing"}">
              <span>${esc(prompt)}</span>
              <small>${esc(publicText(question.reason))}</small>
              ${control}
              <em>${question.answer ? "Сведения сохранены" : "Не заполнено — будет показано как предупреждение"}</em>
            </label>`;
        }
      )
      .join("");
  }

  show("issues", job.validation_issues.length > 0);
  document.getElementById("issue-list").innerHTML = job.validation_issues
    .map(
      (issue) =>
        `<div class="issues ${esc(issue.severity)}"><b>${esc(issue.code)}</b><br>${esc(
          issue.message
        )}</div>`
    )
    .join("");

  const previews = await api(`/api/kits/${jobRef}/preview`);
  show("previews", previews.files.length > 0);
  document.getElementById("preview-list").innerHTML = previews.files
    .map(
      (file) =>
        `<a target="_blank" rel="noopener" href="/api/kits/${jobRef}/files/${safePath(file)}">${esc(
          file.split("/").pop()
        )}</a>`
    )
    .join("");

  show("review", ["READY_FOR_REVIEW", "FAILED_VALIDATION"].includes(job.status));
  document.getElementById("approve").disabled = job.status !== "READY_FOR_REVIEW";
  show("download", job.status === "APPROVED_FINAL");

  if (!terminal.has(job.status) && job.status !== "NEEDS_INPUT") {
    refreshTimer = window.setTimeout(() => refresh().catch(showFatalError), 2000);
  }
}

function showFatalError(error) {
  document.getElementById("summary").textContent = error.message;
  const pill = document.getElementById("status-pill");
  pill.textContent = "Ошибка интерфейса";
  pill.className = "status-pill is-error";
}

document.getElementById("answers-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const feedback = document.getElementById("answers-feedback");
  feedback.hidden = true;
  const answers = [];
  for (const [id, value] of form.entries()) {
    if (id.startsWith("q-")) {
      answers.push({
        question_id: id,
        value,
        comment: "",
        confirmed_by: currentJob.operator_name,
      });
    }
  }
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  button.textContent = "Сохраняем ответы…";
  try {
    await api(`/api/kits/${jobRef}/answers`, {
      method: "POST",
      body: JSON.stringify({ answers }),
    });
    await refresh();
    if (currentJob.status === "NEEDS_INPUT" && !currentJob.draft_report_ready) {
      feedback.textContent =
        "Заполненные сведения сохранены. Пропущенные поля отмечены предупреждениями и не отправлены на повторный анализ.";
      feedback.hidden = false;
    }
  } catch (error) {
    feedback.textContent = error.message;
    feedback.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Перейти к черновому отчёту";
  }
});

document.getElementById("edit-draft-answers").addEventListener("click", () => {
  show("draft-report", false);
  show("questions", true);
  document.getElementById("questions").scrollIntoView({ behavior: "smooth", block: "start" });
});

document.getElementById("retry-analysis-button").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = "Ставим в очередь…";
  try {
    await api(`/api/kits/${jobRef}/retry`, { method: "POST" });
    await refresh();
  } catch (error) {
    showFatalError(error);
    button.disabled = false;
    button.textContent = "Повторить анализ";
  }
});

document.getElementById("approve").addEventListener("click", async (event) => {
  event.currentTarget.disabled = true;
  try {
    await api(`/api/kits/${jobRef}/review`, {
      method: "POST",
      body: JSON.stringify({ action: "approve", corrections: [] }),
    });
    await refresh();
  } catch (error) {
    showFatalError(error);
    event.currentTarget.disabled = false;
  }
});

document.getElementById("revision-btn").addEventListener("click", () => {
  show("revision-form", true);
  document.querySelector("#revision-form input")?.focus();
});

document.getElementById("revision-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const correction = Object.fromEntries(new FormData(event.currentTarget));
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  try {
    await api(`/api/kits/${jobRef}/review`, {
      method: "POST",
      body: JSON.stringify({ action: "request_revision", corrections: [correction] }),
    });
    show("revision-form", false);
    event.currentTarget.reset();
    await refresh();
  } catch (error) {
    showFatalError(error);
  } finally {
    button.disabled = false;
  }
});

refresh().catch(showFatalError);
