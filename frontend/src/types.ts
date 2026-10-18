export type Severity = "critical" | "high" | "medium" | "low";
export type FindingSource = "static" | "ai";

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
}
export interface ReviewSummary {
  critical: number; high: number; medium: number; low: number; total_findings: number;
}
export interface Review {
  review_id: string; repository: string; branch: string; status: string;
  risk_score: number; summary: ReviewSummary; findings: Finding[];
}