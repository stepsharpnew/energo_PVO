#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [rootArg, outputArg] = process.argv.slice(2);
if (!rootArg || !outputArg) {
  throw new Error("Usage: verify_approved_templates.mjs <project-root> <output-dir>");
}

const root = path.resolve(rootArg);
const outputDir = path.resolve(outputArg);
await fs.mkdir(outputDir, { recursive: true });

const specs = [
  {
    id: "aosr_kl",
    path: path.join(root, "templates", "approved", "9. АОСР КЛ.xlsx"),
    sheets: [
      "АОСР-1",
      "АОСР-2",
      "АОСР-3",
      "АОСР-4",
      "АОСР-5",
      "АОСР-6",
      "АОСР-7",
      "АОСР-пожар",
    ],
  },
  {
    id: "aosr_vrs",
    path: path.join(root, "templates", "approved", "10. АОСР ВРЩ.xlsx"),
    sheets: ["АОСР-1", "АОСР-2", "АОСР-3", "АОСР-4", "АОСР-5", "АОСР-6"],
  },
];

const report = {
  generatedAt: new Date().toISOString(),
  templates: [],
};

for (const spec of specs) {
  const input = await FileBlob.load(spec.path);
  const workbook = await SpreadsheetFile.importXlsx(input);
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 300 },
    maxChars: 20000,
  });
  const rendered = [];
  for (const sheetName of spec.sheets) {
    const preview = await workbook.render({
      sheetName,
      autoCrop: "all",
      scale: 0.8,
      format: "png",
    });
    const safeName = sheetName.replace(/[^0-9A-Za-zА-Яа-яЁё_-]+/g, "_");
    const output = path.join(outputDir, `${spec.id}-${safeName}.png`);
    await fs.writeFile(output, new Uint8Array(await preview.arrayBuffer()));
    rendered.push(path.relative(outputDir, output));
  }
  report.templates.push({
    id: spec.id,
    path: spec.path,
    formulaErrorScan: errors.ndjson ?? String(errors),
    rendered,
  });
}

const reportPath = path.join(outputDir, "artifact-verification.json");
await fs.writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
console.log(`report=${reportPath}`);
console.log(
  `render_count=${report.templates.reduce((sum, item) => sum + item.rendered.length, 0)}`,
);
