export type Severity = "critical" | "high" | "medium" | "low";
export type FindingSource = "static" | "ai";
export type FindingDecision = "open" | "accepted" | "dismissed";

export interface ReviewDiffLine {
  kind: "context" | "addition" | "deletion";
  line: number;
  text: string;
}

export interface ReviewDiffFile {
  path: string;
  lines: ReviewDiffLine[];
}

export interface Finding {
  id: string;
  severity: Severity;
  category: string;
  file_path: string;
  line: number;
  title: string;
  message: string;
  explanation: string;
  suggested_fix: string;
  source: FindingSource;
  confidence: number;
  status?: "open" | "accepted" | "dismissed" | "fixed";
  evidence?: string | null;
  end_line?: number | null;
  certainty?: "confirmed" | "hypothesis" | null;
  rule_id?: string | null;
  analyzer_name?: string | null;
  analyzer_version?: string | null;
}
export interface ReviewSummary {
  critical: number; high: number; medium: number; low: number; total_findings: number;
}
export interface Review {
  review_id: string; repository: string; branch: string; status: string;
  risk_score: number; summary: ReviewSummary; findings: Finding[];
  correlation_id?: string | null;
  failure_reason?: string | null;
  diff_files?: ReviewDiffFile[];
}

export interface FindingDisposition {
  decision: FindingDecision;
  reason?: string;
}

export type FindingDispositionMap = Record<string, FindingDisposition>;
