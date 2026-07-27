const form = document.getElementById("job-form");
const panels = [...document.querySelectorAll("[data-step-panel]")];
const stepLinks = [...document.querySelectorAll("[data-step-target]")];
const fileInputs = [...document.querySelectorAll(".file-input")];
const drawerBackdrop = document.getElementById("drawer-backdrop");
const draftKey = "executive-docs-mvp-draft-v1";
const profileNames = {
  economy: "Экономно",
  balanced: "Баланс",
  quality: "Тщательно",
};
const statusNames = {
  CREATED: "Создан",
  FILES_UPLOADED: "Файлы загружены",
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

function objectIsValid(showMessage = false) {
  const operator = document.getElementById("operator-name");
  const number = document.getElementById("first-number");
  const valid = operator.value.trim().length > 1 && Number(number.value) >= 1;
  if (showMessage && !valid) {
    if (!operator.value.trim()) operator.setCustomValidity("Укажите специалиста");
    else operator.setCustomValidity("");
    if (Number(number.value) < 1) number.setCustomValidity("Номер должен быть больше нуля");
    else number.setCustomValidity("");
    (operator.checkValidity() ? number : operator).reportValidity();
  }
  return valid;
}

function filesAreValid(showMessage = false) {
  const project = document.getElementById("project-file");
  const valid = Boolean(project.files[0]);
  if (showMessage && !valid) {
    project.setCustomValidity("Добавьте рабочий проект PDF");
    project.reportValidity();
    window.setTimeout(() => project.setCustomValidity(""), 0);
  }
  return valid;
}

function showStep(step, { validate = true } = {}) {
  if (step === "files" && validate && !objectIsValid(true)) {
    step = "object";
  }
  if (step === "check" && validate) {
    if (!objectIsValid(true)) step = "object";
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
  if (kind === "attachments") return updateAttachments();
  const row = document.querySelector(`[data-upload-row="${kind}"]`);
  const file = input.files[0];
  row.classList.toggle("has-file", Boolean(file));
  if (!file) return;
  row.querySelector("[data-file-name]").textContent = file.name;
  row.querySelector("[data-file-meta]").textContent = `${formatBytes(file.size)} · готов к загрузке`;
  row.querySelector("[data-file-state]").textContent = "Файл выбран";
}

function updateAttachments() {
  const input = document.getElementById("attachment-files");
  const files = [...input.files];
  const count = document.getElementById("attachment-count");
  const list = document.getElementById("attachment-list");
  const noun = files.length === 1 ? "файл" : files.length > 1 && files.length < 5 ? "файла" : "файлов";
  count.textContent = `${files.length} ${noun}`;
  list.innerHTML = files
    .map(
      (file) =>
        `<div><span>${escapeHtml(file.name)}</span><small>${formatBytes(file.size)}</small></div>`
    )
    .join("");
}

function updateInsight() {
  const project = fileFor("project");
  const facts = fileFor("facts");
  const copy = document.getElementById("insight-copy");
  if (project && facts) {
    copy.textContent = "Рабочий проект и дополнительная таблица выбраны. Проверьте состав запуска.";
  } else if (project) {
    copy.textContent = "Рабочий проект выбран. Таблицу фактических данных можно не добавлять.";
  } else if (facts) {
    copy.textContent = "Добавьте обязательный рабочий проект PDF.";
  } else {
    copy.textContent = "После загрузки агент сопоставит объект, работы и доступные шаблоны.";
  }
}

function updateOperator() {
  const value = document.getElementById("operator-name").value.trim();
  document.getElementById("operator-label").textContent = value || "Специалист";
  const avatar = document.querySelector(".operator-avatar");
  if (avatar) avatar.textContent = (value || "С").slice(0, 1).toUpperCase();
}

function updateReview() {
  const branch = document.getElementById("branch-id");
  const attachments = document.getElementById("attachment-files").files.length;
  const profile = new FormData(form).get("processing_profile") || "balanced";
  document.getElementById("review-branch").textContent = branch.options[branch.selectedIndex].text;
  document.getElementById("review-number").textContent = `с АОСР №${document.getElementById("first-number").value}`;
  document.getElementById("review-operator").textContent =
    document.getElementById("operator-name").value.trim() || "Не указан";
  document.getElementById("review-project").textContent = fileFor("project")?.name || "Не выбран";
  document.getElementById("review-facts").textContent =
    fileFor("facts")?.name || "Не выбраны (необязательно)";
  document.getElementById("review-attachments").textContent = String(attachments);
  document.getElementById("review-profile").textContent = profileNames[profile] || profile;
}

function escapeHtml(value) {
  return String(value).replace(
    /[&<>'"]/g,
    (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]
  );
}

function saveDraft() {
  const profile = new FormData(form).get("processing_profile") || "balanced";
  const draft = {
    branch: document.getElementById("branch-id").value,
    firstNumber: document.getElementById("first-number").value,
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
    document.getElementById("branch-id").value = draft.branch || "khimki";
    document.getElementById("first-number").value = draft.firstNumber || "1";
    document.getElementById("operator-name").value = draft.operator || "";
    const profile = form.querySelector(`[name="processing_profile"][value="${CSS.escape(draft.profile || "")}"]`);
    if (profile) profile.checked = true;
    document.getElementById("draft-status").textContent =
      "Восстановлен локальный черновик. Файлы нужно выбрать заново.";
  } catch {
    localStorage.removeItem(draftKey);
  }
}

function applyDesignDemo() {
  if (new URLSearchParams(window.location.search).get("demo") !== "1") return false;
  document.getElementById("operator-name").value = "Иванова М. А.";
  const demoFiles = {
    project: {
      name: "4708-308092-125-11_24.ЭС_РП.pdf",
      meta: "12,4 МБ · выбран для загрузки",
    },
    facts: {
      name: "Фактические данные_4708-308092.xlsx",
      meta: "0,9 МБ · выбран для загрузки",
    },
  };
  Object.entries(demoFiles).forEach(([kind, file]) => {
    const row = document.querySelector(`[data-upload-row="${kind}"]`);
    row.classList.add("has-file");
    row.querySelector("[data-file-name]").textContent = file.name;
    row.querySelector("[data-file-meta]").textContent = file.meta;
    row.querySelector("[data-file-state]").textContent = "Файл выбран";
  });
  document.getElementById("attachment-count").textContent = "3 файла";
  document.getElementById("insight-copy").textContent =
    "Мы уже нашли: объект в Химках, шифр 4708-308092-125-11/24.ЭС, 15 отдельных работ.";
  updateOperator();
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
    updateUploadRow(input);
    updateInsight();
    updateReview();
  });
});

document.getElementById("attachments-toggle").addEventListener("click", (event) => {
  const body = document.getElementById("attachments-body");
  const expanded = event.currentTarget.getAttribute("aria-expanded") === "true";
  event.currentTarget.setAttribute("aria-expanded", String(!expanded));
  body.hidden = expanded;
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
  document.getElementById("operator-name").setCustomValidity("");
  document.getElementById("first-number").setCustomValidity("");
  updateOperator();
  scheduleDraft();
});
form.addEventListener("change", scheduleDraft);

form.addEventListener("submit", (event) => {
  const error = document.getElementById("form-error");
  if (!objectIsValid() || !filesAreValid()) {
    event.preventDefault();
    error.hidden = false;
    error.textContent =
      "Проверьте специалиста, первый номер АОСР и обязательный рабочий проект перед запуском.";
    showStep(objectIsValid() ? "files" : "object", { validate: false });
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
      ? "Черновой отчёт"
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
updateInsight();
if (!applyDesignDemo()) showStep(activeStep, { validate: false });
