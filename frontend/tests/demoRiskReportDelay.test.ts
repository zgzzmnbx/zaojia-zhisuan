import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("keeps embedded demo risk reports in the processing state for five seconds", async () => {
  const appSource = await readFile(new URL("../src/App.tsx", import.meta.url), "utf8");

  assert.match(appSource, /DEMO_RISK_REPORT_PROCESSING_MS\s*=\s*5000/);
  assert.match(appSource, /const riskReportStartedAt = performance\.now\(\)/);
  assert.match(
    appSource,
    /payload\.risk_report_mode === "demo_preset"[\s\S]*DEMO_RISK_REPORT_PROCESSING_MS - \(performance\.now\(\) - riskReportStartedAt\)[\s\S]*window\.setTimeout\(resolve, remainingMs\)/,
  );
});
