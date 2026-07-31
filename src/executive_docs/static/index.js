const form = document.getElementById("job-form");
const panels = [...document.querySelectorAll("[data-step-panel]")];
const stepLinks = [...document.querySelectorAll("[data-step-target]")];
const fileInputs = [...document.querySelectorAll(".file-input")];
const drawerBackdrop = document.getElementById("drawer-backdrop");
const draftKey = "executive-docs-single-template-draft-v2";
const profileNames = {
  economy: "Экономно",
  balanced: "Баланс",
  quality: "Тщательно",
};
const templateStatusNames = {
  APPROVED: "Утверждён",
  READY: "Готов к заполнению",
  READY_FOR_USE: "Готов к заполнению",
  READY_FOR_VISUAL_APPROVAL: "Ожидает визуального утверждения",
  DISCOVERY_REVIEW_REQUIRED: "Требует проверки списка полей",
  NEEDS_INPUT: "Нужно уточнение",
};
const statusNames = {
  CREATED: "Создан",
  FILES_UPLOADED: "PDF загружен",
  ANALYZING: "Анализ",
  NEEDS_INPUT: "Нужны сведения",
  GENERATING: "Формирование",
  VALIDATING: "Проверка",
  READY_FOR_REVIEW: "Готов к проверке",
  APPROVED_FINAL: "Подтверждён",
  REVISION_REQUIRED: "Нужна ревизия",
  FAILED_ANALYSIS: "Ошибка анализа",
  FAILED_GENERATION: "Ошибка формирования",
  FAILED_VALIDATION: "Не прошёл проверку",
  CANCELLED: "Отменён",
};

let activeStep = "object";
let draftTimer = null;

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 Б";
  const units = ["Б", "КБ", "МБ", "ГБ"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value.toLocaleString("ru-RU", { maximumFractionDigits: exponent ? 1 : 0 })} ${units[exponent]}`;
}

function fileFor(kind) {
  const input = document.querySelector(`[data-file-kind="${kind}"]`);
  return input?.files?.[0] || null;
}

function selectedTemplateOption() {
  const select = document.getElementById("template-id");
  return select.value ? select.options[select.selectedIndex] : null;
}

function setupIsValid(showMessage = false) {
  const template = document.getElementById("template-id");
  const operator = document.getElementById("operator-name");
  const valid = Boolean(template.value) && operator.value.trim().length > 1;
  if (showMessage && !valid) {
    if (!template.value) template.setCustomValidity("Выберите шаблон Excel");
    else template.setCustomValidity("");
    if (!operator.value.trim()) operator.setCustomValidity("Укажите специалиста");
    else operator.setCustomValidity("");
    (template.checkValidity() ? operator : template).reportValidity();
  }
  return valid;
}

function filesAreValid(showMessage = false) {
  const project = document.getElementById("project-file");
  const file = project.files[0];
  const valid = Boolean(
    file &&
      /\.pdf$/i.test(file.name) &&
      (!file.type || file.type.toLowerCase() === "application/pdf")
  );
  if (showMessage && !valid) {
    project.setCustomValidity("Добавьте один рабочий проект в формате PDF");
    project.reportValidity();
    window.setTimeout(() => project.setCustomValidity(""), 0);
  }
  return valid;
}

function showStep(step, { validate = true } = {}) {
  if (step === "files" && validate && !setupIsValid(true)) {
    step = "object";
  }
  if (step === "check" && validate) {
    if (!setupIsValid(true)) step = "object";
    else if (!filesAreValid(true)) step = "files";
  }
  activeStep = step;
  panels.forEach((panel) => {
    const active = panel.dataset.stepPanel === step;
    panel.hidden = !active;
    panel.classList.toggle("is-active", active);
  });
  stepLinks.forEach((link) => {
    const active = link.dataset.stepTarget === step;
    link.classList.toggle("is-active", active);
    if (active) link.setAttribute("aria-current", "step");
    else link.removeAttribute("aria-current");
    const order = { object: 1, files: 2, check: 3 };
    link.classList.toggle("is-complete", order[link.dataset.stepTarget] < order[step]);
  });
  if (step === "check") updateReview();
  document.querySelector(".wizard-main").scrollTo?.({ top: 0, behavior: "smooth" });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function updateUploadRow(input) {
  const kind = input.dataset.fileKind;
  const row = document.querySelector(`[data-upload-row="${kind}"]`);
  const file = input.files[0];
  row.classList.toggle("has-file", Boolean(file));
  if (!file) {
    row.querySelector("[data-file-name]").textContent = "Выберите один PDF-файл";
    row.querySelector("[data-file-meta]").textContent = "Только PDF";
    row.querySelector("[data-file-state]").textContent = "Выбрать файл";
    return;
  }
  row.querySelector("[data-file-name]").textContent = file.name;
  row.querySelector("[data-file-meta]").textContent = `${formatBytes(file.size)} · готов к загрузке`;
  row.querySelector("[data-file-state]").textContent = "Файл выбран";
}

function updateTemplateMeta() {
  const option = selectedTemplateOption();
  const meta = document.getElementById("template-meta");
  if (!option) {
    meta.textContent = "За один запуск формируется только выбранная книга.";
    return;
  }
  const normalizedStatus = String(option.dataset.status || "").toUpperCase();
  const status = templateStatusNames[normalizedStatus] || option.dataset.status || "Доступен";
  const targetCount = Number(option.dataset.targetCount || 0);
  const targets = targetCount > 0 ? ` · полей для заполнения: ${targetCount}` : "";
  meta.textContent = `${status}${targets}`;
}

function updateInsight() {
  const project = fileFor("project");
  const copy = document.getElementById("insight-copy");
  if (project) {
    copy.textContent =
      "PDF выбран. Агент перенесёт подтверждённые сведения только в выбранную Excel-книгу.";
  } else {
    copy.textContent =
      "Недоступные в PDF сведения останутся пустыми и будут выделены в готовой книге.";
  }
}

function updateOperator() {
  const value = document.getElementById("operator-name").value.trim();
  document.getElementById("operator-label").textContent = value || "Специалист";
  const avatar = document.querySelector(".operator-avatar");
  if (avatar) avatar.textContent = (value || "С").slice(0, 1).toUpperCase();
}

function updateReview() {
  const template = selectedTemplateOption();
  const profile = new FormData(form).get("processing_profile") || "balanced";
  document.getElementById("review-template").textContent = template?.textContent.trim() || "Не выбран";
  document.getElementById("review-operator").textContent =
    document.getElementById("operator-name").value.trim() || "Не указан";
  document.getElementById("review-project").textContent = fileFor("project")?.name || "Не выбран";
  document.getElementById("review-profile").textContent = profileNames[profile] || profile;
}

function saveDraft() {
  const profile = new FormData(form).get("processing_profile") || "balanced";
  const draft = {
    template: document.getElementById("template-id").value,
    operator: document.getElementById("operator-name").value,
    profile,
  };
  localStorage.setItem(draftKey, JSON.stringify(draft));
  const status = document.getElementById("draft-status");
  status.textContent = `Черновик сохранён · ${new Date().toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

function scheduleDraft() {
  window.clearTimeout(draftTimer);
  draftTimer = window.setTimeout(saveDraft, 280);
}

function loadDraft() {
  try {
    const draft = JSON.parse(localStorage.getItem(draftKey) || "null");
    if (!draft) return;
    document.getElementById("template-id").value = draft.template || "";
    document.getElementById("operator-name").value = draft.operator || "";
    const profile = form.querySelector(`[name="processing_profile"][value="${CSS.escape(draft.profile || "")}"]`);
    if (profile) profile.checked = true;
    document.getElementById("draft-status").textContent =
      "Восстановлен локальный черновик. PDF нужно выбрать заново.";
  } catch {
    localStorage.removeItem(draftKey);
  }
}

function applyDesignDemo() {
  if (new URLSearchParams(window.location.search).get("demo") !== "1") return false;
  const template = document.getElementById("template-id");
  if (!template.value && template.options.length > 1) template.selectedIndex = 1;
  document.getElementById("operator-name").value = "Иванова М. А.";
  const row = document.querySelector('[data-upload-row="project"]');
  row.classList.add("has-file");
  row.querySelector("[data-file-name]").textContent = "4708-308092-125-11_24.ЭС_РП.pdf";
  row.querySelector("[data-file-meta]").textContent = "12,4 МБ · выбран для загрузки";
  row.querySelector("[data-file-state]").textContent = "Файл выбран";
  document.getElementById("insight-copy").textContent =
    "PDF выбран. За один запуск будет заполнен только указанный специалистом шаблон.";
  updateOperator();
  updateTemplateMeta();
  showStep("files", { validate: false });
  return true;
}

function openDrawer(drawer) {
  document.querySelectorAll(".side-drawer").forEach((item) => {
    const open = item === drawer;
    item.classList.toggle("is-open", open);
    item.setAttribute("aria-hidden", String(!open));
  });
  drawerBackdrop.hidden = false;
  document.body.classList.add("drawer-open");
  drawer.querySelector("button")?.focus();
}

function closeDrawers() {
  document.querySelectorAll(".side-drawer").forEach((item) => {
    item.classList.remove("is-open");
    item.setAttribute("aria-hidden", "true");
  });
  drawerBackdrop.hidden = true;
  document.body.classList.remove("drawer-open");
}

stepLinks.forEach((link) => {
  link.addEventListener("click", () => showStep(link.dataset.stepTarget));
});

document.querySelectorAll("[data-next-step]").forEach((button) => {
  button.addEventListener("click", () => showStep(button.dataset.nextStep));
});

fileInputs.forEach((input) => {
  input.addEventListener("change", () => {
    input.setCustomValidity("");
    updateUploadRow(input);
    updateInsight();
    updateReview();
  });
});

document.getElementById("help-toggle").addEventListener("click", () => {
  openDrawer(document.getElementById("help-drawer"));
});
document.getElementById("requirements-toggle").addEventListener("click", () => {
  openDrawer(document.getElementById("help-drawer"));
});
document.getElementById("recent-toggle").addEventListener("click", () => {
  openDrawer(document.getElementById("recent-drawer"));
});
document.querySelectorAll("[data-close-drawer]").forEach((button) => {
  button.addEventListener("click", closeDrawers);
});
drawerBackdrop.addEventListener("click", closeDrawers);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawers();
});

form.addEventListener("input", () => {
  document.getElementById("template-id").setCustomValidity("");
  document.getElementById("operator-name").setCustomValidity("");
  updateOperator();
  scheduleDraft();
});
form.addEventListener("change", (event) => {
  if (event.target.id === "template-id") {
    event.target.setCustomValidity("");
    updateTemplateMeta();
  }
  updateReview();
  scheduleDraft();
});

form.addEventListener("submit", (event) => {
  const error = document.getElementById("form-error");
  if (!setupIsValid() || !filesAreValid()) {
    event.preventDefault();
    error.hidden = false;
    error.textContent =
      "Выберите шаблон, укажите специалиста и добавьте один рабочий проект PDF.";
    showStep(setupIsValid() ? "files" : "object", { validate: false });
    return;
  }
  error.hidden = true;
  const submit = document.getElementById("submit-job");
  submit.disabled = true;
  submit.textContent = "Создаём задание…";
  localStorage.removeItem(draftKey);
});

document.querySelectorAll("[data-job-status]").forEach((item) => {
  item.textContent =
    item.dataset.jobStatus === "NEEDS_INPUT" && item.dataset.draftReady === "true"
      ? "Книга с предупреждениями"
      : statusNames[item.dataset.jobStatus] || item.dataset.jobStatus;
});

const today = document.getElementById("current-date");
if (today) {
  const parsed = new Date(`${today.dateTime}T12:00:00`);
  today.textContent = new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(parsed);
}

loadDraft();
updateOperator();
updateTemplateMeta();
updateInsight();
if (!applyDesignDemo()) showStep(activeStep, { validate: false });
