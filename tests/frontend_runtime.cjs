const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function browserFixture(scriptName, fetch, { storageBlocked = false } = {}) {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      id, value: "", textContent: "", innerHTML: "", hidden: false, disabled: false,
      dataset: {}, files: [], options: [], selectedIndex: 0, listeners: {},
      classList: { add() {}, remove() {}, toggle() {} },
      addEventListener(name, callback) { this.listeners[name] = callback; },
      setAttribute() {}, removeAttribute() {}, setCustomValidity() {},
      checkValidity() { return true; }, reportValidity() {}, scrollTo() {}, focus() {},
      querySelector() { return element(`${id}-child`); },
    });
    return elements.get(id);
  }
  const form = element("job-form");
  form.action = "http://localhost/api/jobs";
  element("template-id").value = "aosr_vl";
  element("template-id").options = [{ textContent: "АОСР ВЛ", dataset: { targetCount: "65" } }];
  element("operator-name").value = "Специалист";
  element("project-file").files = [{ name: "project.pdf", type: "application/octet-stream", size: 100 }];
  element("current-date").dateTime = "2026-09-07";
  const document = {
    getElementById: element,
    querySelector: (selector) => selector.includes("data-file-kind") ? element("project-file") : element(selector),
    querySelectorAll: () => [],
    addEventListener() {}, body: element("body"),
  };
  const timers = [];
  const locations = [];
  const window = {
    mvpConfig: { maxFileBytes: 1024 }, scrollTo() {},
    setTimeout(callback, delay) { timers.push({ callback, delay }); return timers.length; },
    clearTimeout() {}, location: { search: "", assign: (url) => locations.push(url) },
  };
  const localStorage = {
    getItem() { if (storageBlocked) throw new Error("Storage blocked"); return null; },
    setItem() { if (storageBlocked) throw new Error("Storage blocked"); },
    removeItem() { if (storageBlocked) throw new Error("Storage blocked"); },
  };
  class FormData {
    constructor(value) { this.form = value; }
    get(name) { return name === "processing_profile" ? "balanced" : null; }
  }
  const context = vm.createContext({
    document, window, localStorage, fetch, FormData, URLSearchParams,
    CSS: { escape: (value) => value }, TypeError, jobRef: "example-ref",
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../src/executive_docs/static", scriptName), "utf8"), context);
  return { element, timers, locations, context, form };
}

const response = (status, payload) => ({
  status, ok: status < 400, statusText: `HTTP ${status}`,
  async json() { if (payload === undefined) throw new SyntaxError("HTML response"); return payload; },
});
const settle = () => new Promise((resolve) => setImmediate(resolve));

(async () => {
  let requests = [];
  let fixture = browserFixture("index.js", async (url, options) => {
    requests.push({ url, options });
    return response(202, { job_id: "20260907-120000-123456" });
  }, { storageBlocked: true });
  await fixture.form.listeners.submit({ preventDefault() {} });
  assert.equal(requests.length, 1);
  assert.equal(requests[0].options.headers.Accept, "application/json");
  assert.equal(requests[0].options.body.form, fixture.form);
  assert.deepEqual(fixture.locations, ["/kits/20260907-120000-123456"]);
  await fixture.form.listeners.submit({ preventDefault() {} });
  assert.equal(requests.length, 1, "double submit must not create a second paid job");

  for (const [status, body] of [[413, undefined], [422, { detail: [{ msg: "Field required" }] }], [500, { detail: "Traceback secret" }]]) {
    fixture = browserFixture("index.js", async () => response(status, body));
    await fixture.form.listeners.submit({ preventDefault() {} });
    assert.equal(fixture.element("form-error").hidden, false);
    assert.equal(fixture.element("submit-job").disabled, false);
    assert.deepEqual(fixture.locations, []);
    assert.doesNotMatch(fixture.element("form-error").textContent, /Traceback|\[object Object\]|Field required/);
  }

  fixture = browserFixture("index.js", async () => { throw new TypeError("Failed to fetch"); });
  await fixture.form.listeners.submit({ preventDefault() {} });
  assert.match(fixture.element("form-error").textContent, /задание могло быть принято/);

  requests = [];
  fixture = browserFixture("index.js", async () => { requests.push(1); });
  fixture.element("project-file").files[0].size = 2048;
  await fixture.form.listeners.submit({ preventDefault() {} });
  assert.equal(requests.length, 0);
  assert.match(fixture.element("form-error").textContent, /Размер PDF превышает/);

  let unavailable = true;
  fixture = browserFixture("job.js", async (url) => {
    if (unavailable) throw new TypeError("Offline");
    if (url.endsWith("/preview")) throw new TypeError("Preview temporarily unavailable");
    return response(200, {
      status: "ANALYZING", flow_version: "selected-template-v2", revision: 1,
      summary: "Анализ PDF", processing_profile: "balanced", model_usage: [],
      draft_report_ready: false, draft_excel_files: [], validation_issues: [],
    });
  });
  await settle();
  assert.match(fixture.element("status-pill").textContent, /Восстанавливаем связь/);
  assert.equal(fixture.timers.at(-1).delay, 5000);
  unavailable = false;
  fixture.timers.at(-1).callback();
  await settle();
  assert.equal(fixture.element("status").textContent, "Агент изучает PDF");
  assert.equal(fixture.timers.at(-1).delay, 2000, "preview failure must not stop job polling");
  // The API already returns service prices: the browser only totals/formats.
  vm.runInContext('updateUsage({processing_profile:"balanced", model_usage:[{estimated_cost_usd:0.75},{estimated_cost_usd:0.125}]})', fixture.context);
  assert.match(fixture.element("usage-summary").textContent, /около \$0\.875$/);
  vm.runInContext('updateUsage({model_usage:[{estimated_cost_usd:0.75},{estimated_cost_usd:null}]})', fixture.context);
  assert.match(fixture.element("usage-summary").textContent, /оценка стоимости недоступна$/);
  vm.runInContext('updateUsage({model_usage:[{estimated_cost_usd:0}]})', fixture.context);
  assert.match(fixture.element("usage-summary").textContent, /около \$0\.000$/);
  vm.runInContext('updateUsage({model_usage:[]})', fixture.context);
  assert.equal(fixture.element("usage-summary").textContent, "Платных вызовов пока не было.");
  console.log("Frontend runtime checks passed");
})().catch((error) => { console.error(error); process.exitCode = 1; });
