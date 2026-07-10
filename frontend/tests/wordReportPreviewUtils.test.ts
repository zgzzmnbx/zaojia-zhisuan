import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  DOCX_MIME,
  WordReportPreviewError,
  filenameFromContentDisposition,
  normalizeDocxFilename,
  responseToDocxFile,
} from "../src/components/report/wordReportPreviewUtils.ts";

const DOCX_BYTES = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x14, 0x00]);

test("normalizes report filenames to a safe .docx name", () => {
  assert.equal(normalizeDocxFilename("造价智算报告"), "造价智算报告.docx");
  assert.equal(normalizeDocxFilename("C:\\temp\\当前报告.DOCX"), "当前报告.DOCX");
  assert.equal(normalizeDocxFilename(""), "造价智算-控制价报告.docx");
});

test("parses an RFC 5987 Chinese filename", () => {
  const header = "attachment; filename*=UTF-8''%E9%80%A0%E4%BB%B7%E6%99%BA%E7%AE%97%E6%8A%A5%E5%91%8A.docx";
  assert.equal(filenameFromContentDisposition(header), "造价智算报告.docx");
});

test("creates a named DOCX File from the report response", async () => {
  const response = new Response(DOCX_BYTES, {
    status: 200,
    headers: { "Content-Disposition": "attachment; filename=report.docx" },
  });
  const file = await responseToDocxFile(response, "fallback");
  assert.equal(file.name, "report.docx");
  assert.equal(file.type, DOCX_MIME);
  assert.equal(file.size, DOCX_BYTES.length);
});

test("rejects empty and non-DOCX responses", async () => {
  await assert.rejects(
    responseToDocxFile(new Response(new Uint8Array(), { status: 200 }), "empty.docx"),
    (error: unknown) => error instanceof WordReportPreviewError && error.code === "empty",
  );
  await assert.rejects(
    responseToDocxFile(new Response("<!doctype html>", { status: 200 }), "index.docx"),
    (error: unknown) => error instanceof WordReportPreviewError && error.code === "invalid-docx",
  );
});

test("maps a missing report to a recoverable 404 error", async () => {
  await assert.rejects(
    responseToDocxFile(new Response("missing", { status: 404 }), "missing.docx"),
    (error: unknown) => error instanceof WordReportPreviewError && error.status === 404,
  );
});

test("ships the same-origin DOCX worker and JSZip assets as real JavaScript", async () => {
  const assetRoot = fileURLToPath(new URL("../public/file-viewer/vendor/docx/", import.meta.url));
  const workerPath = new URL("../public/file-viewer/vendor/docx/docx.worker.js", import.meta.url);
  const jszipPath = new URL("../public/file-viewer/vendor/docx/jszip.min.js", import.meta.url);
  const [worker, jszip, workerStat, jszipStat] = await Promise.all([
    readFile(workerPath, "utf8"),
    readFile(jszipPath, "utf8"),
    stat(workerPath),
    stat(jszipPath),
  ]);

  assert.match(assetRoot, /public[\\/]file-viewer[\\/]vendor[\\/]docx[\\/]?$/);
  assert.ok(workerStat.size > 200_000);
  assert.ok(jszipStat.size > 90_000);
  assert.match(worker, /@file-viewer\/docx/);
  assert.match(jszip, /JSZip v3\.10\.1/);
  assert.equal(worker.trimStart().startsWith("<"), false);
  assert.equal(jszip.trimStart().startsWith("<"), false);
});
