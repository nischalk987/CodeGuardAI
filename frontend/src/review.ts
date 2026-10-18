import type { Finding, Review, ReviewDiffFile, Severity } from "./types";

export type FindingCategory = "all" | "security" | "performance" | "quality";
export type SeverityFilter = "all" | Severity;
export type FindingLocationSet = ReadonlySet<string>;

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
  changedLines: FindingLocationSet = new Set(),
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
    .sort((a, b) => rankFindings(a, b, changedLines));
}

/** Ranking: severity first, then confidence signal, then whether the line changed, then stable location. */
export function rankFindings(a: Finding, b: Finding, changedLines: FindingLocationSet = new Set()): number {
  return severityOrder[a.severity] - severityOrder[b.severity] ||
    b.confidence - a.confidence ||
    Number(changedLines.has(findingLocationKey(b))) - Number(changedLines.has(findingLocationKey(a))) ||
    compareText(a.file_path, b.file_path) ||
    a.line - b.line ||
    compareText(a.id, b.id);
}

export function findingLocationKey(finding: Pick<Finding, "file_path" | "line">): string {
  return `${finding.file_path}:${finding.line}`;
}

export function changedLineKeys(files: ReviewDiffFile[]): Set<string> {
  return new Set(files.flatMap((file) => file.lines
    .filter((line) => line.kind === "addition")
    .map((line) => `${file.path}:${line.line}`)));
}

export function findingCounts(findings: Finding[]): Record<Severity, number> {
  return findings.reduce((counts, finding) => {
    counts[finding.severity] += 1;
    return counts;
  }, { critical: 0, high: 0, medium: 0, low: 0 });
}

export function isValidDismissalReason(reason: string): boolean {
  return reason.trim().length >= 5 && reason.trim().length <= 500;
}

function compareText(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
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
  const diffFilesValid = review.diff_files === undefined || (
    Array.isArray(review.diff_files) && review.diff_files.every(isDiffFile)
  );
  return diffFilesValid && summary.critical === counts.critical && summary.high === counts.high &&
    summary.medium === counts.medium && summary.low === counts.low &&
    summary.total_findings === review.findings.length;
}

function isDiffFile(value: unknown): value is ReviewDiffFile {
  if (!value || typeof value !== "object") return false;
  const file = value as Partial<ReviewDiffFile>;
  return typeof file.path === "string" && Array.isArray(file.lines) && file.lines.every((line) => {
    if (!line || typeof line !== "object") return false;
    const item = line as ReviewDiffFile["lines"][number];
    return ["context", "addition", "deletion"].includes(item.kind) &&
      Number.isInteger(item.line) && item.line > 0 && typeof item.text === "string";
  });
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
    Number.isInteger(finding.confidence) && (finding.confidence ?? -1) >= 0 && (finding.confidence ?? 101) <= 100 &&
    (finding.evidence === undefined || finding.evidence === null || typeof finding.evidence === "string") &&
    (finding.end_line === undefined || finding.end_line === null ||
      (Number.isInteger(finding.end_line) && finding.end_line >= finding.line!));
}
