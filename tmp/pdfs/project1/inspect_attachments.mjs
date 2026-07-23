import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root = "/Users/step/Desktop/projects/Energo_PVO";
const files = [
  "project1/9. АОСР КЛ.xlsx",
  "project1/9. АОСР КЛ 6кВ.xlsx",
  "project1/10. АОСР ВРЩ.xlsx",
];

function scalar(sheet, address) {
  const values = sheet.getRange(address).values;
  return values?.[0]?.[0] ?? null;
}

const output = [];
for (const relativeFile of files) {
  const workbook = await SpreadsheetFile.importXlsx(
    await FileBlob.load(path.join(root, relativeFile)),
  );
  const sheetInspection = await workbook.inspect({
    kind: "sheet",
    include: "id,name",
    maxChars: 20000,
  });
  const sheets = String(sheetInspection.ndjson || "")
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line))
    .map((item) => item.name || item.sheetName || item.title)
    .filter((name) => typeof name === "string" && name.startsWith("АОСР"));
  const acts = sheets.map((sheetName) => {
    const sheet = workbook.worksheets.getItem(sheetName);
    return {
      sheet: sheetName,
      number: scalar(sheet, "C32"),
      work: scalar(sheet, "A62"),
      attachment_g72: scalar(sheet, "G72"),
      attachment_g74: scalar(sheet, "G74"),
      start_p77: scalar(sheet, "P77"),
      end_p78: scalar(sheet, "P78"),
      start_p79: scalar(sheet, "P79"),
      end_p80: scalar(sheet, "P80"),
    };
  });
  output.push({ file: relativeFile, acts });
}
console.log(JSON.stringify(output, null, 2));
