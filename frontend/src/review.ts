import type { Finding, Review, Severity } from "./types";

export type FindingCategory = "all" | "security" | "performance" | "quality";
export type SeverityFilter = "all" | Severity;

const severityOrder: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3 };
const qualityCategories = new Set(["maintainability", "reliability"]);

export function matchesCategory(finding: Finding, category: FindingCategory): boolean {
  const normalized = finding.category.toLowerCase();
  if (category === "all") return true;
  if (category === "quality") return qualityCategories.has(normalized);
  return normalized === category;
}

export function filterFindings(
  findings: Finding[],
  query: string,
  category: FindingCategory,
  severity: SeverityFilter,
): Finding[] {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  return findings
    .filter((finding) => {
      const searchable = [finding.title, finding.file_path, finding.category, finding.message, String(finding.line)]
        .join(" ")
        .toLocaleLowerCase();
      return (!normalizedQuery || searchable.includes(normalizedQuery)) &&
        matchesCategory(finding, category) &&
        (severity === "all" || finding.severity === severity);
    })
    .sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]);
}

export function isReview(value: unknown): value is Review {
  if (!value || typeof value !== "object") return false;
  const review = value as Partial<Review>;
  if (typeof review.review_id !== "string" || typeof review.repository !== "string" ||
      typeof review.branch !== "string" || !["queued", "running", "completed", "failed"].includes(review.status ?? "") ||
      !Number.isInteger(review.risk_score) || (review.risk_score ?? -1) < 0 || (review.risk_score ?? 101) > 100 ||
      !Array.isArray(review.findings) || !review.summary) return false;

  const counts: Record<Severity, number> = { critical: 0, high: 0, medium: 0, low: 0 };
  for (const finding of review.findings) {
    if (!isFinding(finding)) return false;
    counts[finding.severity] += 1;
  }
  const summary = review.summary;
  return summary.critical === counts.critical && summary.high === counts.high &&
    summary.medium === counts.medium && summary.low === counts.low &&
    summary.total_findings === review.findings.length;
}

function isFinding(value: unknown): value is Finding {
  if (!value || typeof value !== "object") return false;
  const finding = value as Partial<Finding>;
  return typeof finding.id === "string" &&
    ["critical", "high", "medium", "low"].includes(finding.severity ?? "") &&
    typeof finding.category === "string" && typeof finding.file_path === "string" &&
    Number.isInteger(finding.line) && (finding.line ?? 0) > 0 &&
    typeof finding.title === "string" && typeof finding.message === "string" &&
    typeof finding.explanation === "string" && typeof finding.suggested_fix === "string" &&
    ["static", "ai"].includes(finding.source ?? "") &&
    Number.isInteger(finding.confidence) && (finding.confidence ?? -1) >= 0 && (finding.confidence ?? 101) <= 100;
}
