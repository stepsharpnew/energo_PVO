#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [runRootArg, artifactModulesArg] = process.argv.slice(2);
if (!runRootArg || !artifactModulesArg) {
  throw new Error(
    "Usage: verify_project1_golden_parity.mjs <run-root> <artifact-node-modules>",
  );
}

const runRoot = path.resolve(runRootArg);
const artifactEntry = path.join(
  path.resolve(artifactModulesArg),
  "@oai",
  "artifact-tool",
  "dist",
  "artifact_tool.mjs",
);
const { FileBlob, SpreadsheetFile } = await import(pathToFileURL(artifactEntry).href);
const reportPath = path.join(runRoot, "report", "comparison.json");
const comparison = JSON.parse(await fs.readFile(reportPath, "utf8"));
const renderRoot = path.join(runRoot, "artifact-render");
await fs.mkdir(renderRoot, { recursive: true });

const verification = {
  tool: "@oai/artifact-tool",
  generated_at: new Date().toISOString(),
  workbooks: [],
};

async function inspectAndRender(kind, templateId, workbookPath, sheets) {
  const input = await FileBlob.load(workbookPath);
  const workbook = await SpreadsheetFile.importXlsx(input);
  const sheetInspection = await workbook.inspect({
    kind: "sheet",
    include: "id,name",
    maxChars: 12000,
  });
  const errorInspection = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#VALUE!|#N/A|#DIV/0!",
    options: { useRegex: true, maxResults: 200 },
    maxChars: 12000,
  });
  const outputDir = path.join(renderRoot, kind, templateId);
  await fs.mkdir(outputDir, { recursive: true });
  const rendered = [];
  for (const sheetName of sheets) {
    const blob = await workbook.render({
      sheetName,
      autoCrop: "all",
      scale: 0.8,
      format: "png",
    });
    const safeName = sheetName.replace(/[^0-9A-Za-zА-Яа-яЁё_-]+/g, "_");
    const output = path.join(outputDir, `${safeName}.png`);
    await fs.writeFile(output, new Uint8Array(await blob.arrayBuffer()));
    rendered.push(path.relative(runRoot, output));
  }
  return {
    kind,
    workbook: path.relative(runRoot, workbookPath),
    sheets: sheetInspection.ndjson ?? String(sheetInspection),
    formulaErrorScan: errorInspection.ndjson ?? String(errorInspection),
    rendered,
  };
}

for (const item of comparison.workbooks) {
  const generatedPath = path.join(runRoot, item.generated);
  const goldenPath = path.resolve(path.dirname(runRoot), "..", "..", item.golden);
  const generated = await inspectAndRender(
    "generated",
    item.template_id,
    generatedPath,
    item.selected_sheets,
  );
  const golden = await inspectAndRender(
    "golden",
    item.template_id,
    goldenPath,
    item.selected_sheets,
  );
  verification.workbooks.push({
    template_id: item.template_id,
    generated,
    golden,
  });
}

const outputPath = path.join(runRoot, "report", "artifact-verification.json");
await fs.writeFile(outputPath, JSON.stringify(verification, null, 2), "utf8");
console.log(`artifact_verification=${outputPath}`);
console.log(
  `render_count=${verification.workbooks.reduce(
    (sum, item) => sum + item.generated.rendered.length + item.golden.rendered.length,
    0,
  )}`,
);
