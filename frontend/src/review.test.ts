import { describe, expect, it } from "vitest";
import { demoReview } from "./demo";
import {
  changedLineKeys,
  filterFindings,
  findingCounts,
  findingLocationKey,
  isReview,
  isValidDismissalReason,
} from "./review";
import { demoDiffFiles } from "./demo";

describe("filterFindings", () => {
  it("combines category, severity, and case-insensitive search including line numbers", () => {
    expect(filterFindings(demoReview.findings, "117", "security", "high").map(({ id }) => id))
      .toEqual(["CG-003"]);
  });

  it("groups maintainability and reliability under quality and sorts by severity", () => {
    expect(filterFindings(demoReview.findings, "", "quality", "all").map(({ id }) => id))
      .toEqual(["CG-002", "CG-005"]);
  });

  it("returns no findings for an unmatched query", () => {
    expect(filterFindings(demoReview.findings, "not-present", "all", "all")).toEqual([]);
  });

  it("ranks by severity, confidence signal, changed-line match, then stable location", () => {
    const lowConfidenceHigh = { ...demoReview.findings[1], id: "high-low", confidence: 60, file_path: "z.ts", line: 20 };
    const highConfidenceHighChanged = { ...demoReview.findings[1], id: "high-changed", confidence: 80, file_path: "z.ts", line: 10 };
    const highConfidenceHighContext = { ...demoReview.findings[1], id: "high-context", confidence: 80, file_path: "a.ts", line: 10 };
    const critical = { ...demoReview.findings[0], confidence: 1 };
    const changed = new Set([findingLocationKey(highConfidenceHighChanged)]);
    expect(filterFindings(
      [lowConfidenceHigh, highConfidenceHighChanged, critical, highConfidenceHighContext],
      "", "all", "all", changed,
    ).map(({ id }) => id)).toEqual(["CG-001", "high-changed", "high-context", "high-low"]);
  });

  it("counts exactly the visible filtered findings and marks added diff lines", () => {
    const visible = filterFindings(demoReview.findings, "", "security", "high");
    expect(findingCounts(visible)).toEqual({ critical: 0, high: 1, medium: 0, low: 0 });
    const changed = changedLineKeys(demoDiffFiles);
    expect(changed.has("src/api/webhook.py:117")).toBe(true);
    expect(changed.has("src/api/webhook.py:116")).toBe(false);
  });

  it("requires a concise reason for a dismissal", () => {
    expect(isValidDismissalReason("   ")).toBe(false);
    expect(isValidDismissalReason("Confirmed false positive")).toBe(true);
    expect(isValidDismissalReason("x".repeat(501))).toBe(false);
  });
});

describe("isReview", () => {
  it("accepts the typed demo review", () => {
    expect(isReview(demoReview)).toBe(true);
  });

  it("rejects malformed findings and summary counts", () => {
    expect(isReview({ ...demoReview, findings: [{ ...demoReview.findings[0], line: 0 }] })).toBe(false);
    expect(isReview({ ...demoReview, summary: { ...demoReview.summary, high: 99 } })).toBe(false);
  });

  it("rejects malformed diff line data when a diff is included", () => {
    expect(isReview({ ...demoReview, diff_files: [{ path: "src/a.ts", lines: [{ kind: "addition", line: 0, text: "bad" }] }] })).toBe(false);
  });
});
