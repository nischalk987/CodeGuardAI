import { describe, expect, it } from "vitest";
import { demoReview } from "./demo";
import { filterFindings, isReview } from "./review";

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
});

describe("isReview", () => {
  it("accepts the typed demo review", () => {
    expect(isReview(demoReview)).toBe(true);
  });

  it("rejects malformed findings and summary counts", () => {
    expect(isReview({ ...demoReview, findings: [{ ...demoReview.findings[0], line: 0 }] })).toBe(false);
    expect(isReview({ ...demoReview, summary: { ...demoReview.summary, high: 99 } })).toBe(false);
  });
});
