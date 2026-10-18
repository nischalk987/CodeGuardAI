import type { Review } from "./types";

export const demoReview: Review = {
  review_id: "demo-8f31a",
  repository: "acme/payments-api",
  branch: "feature/payment-retry",
  status: "completed",
  risk_score: 72,
  summary: { critical: 1, high: 2, medium: 1, low: 1, total_findings: 5 },
  findings: [
    { id: "CG-001", severity: "critical", category: "Security", file_path: "src/auth/session.py", line: 84, title: "Session token may be exposed in logs", message: "A token-like value is included in a debug log statement.", explanation: "If this path runs in production, log aggregation could retain session credentials and make them accessible to people who should not have access.", suggested_fix: "Log a request or session identifier instead. Never write the raw token to logs.", source: "static", confidence: 98 },
    { id: "CG-002", severity: "high", category: "Reliability", file_path: "src/payments/retry.ts", line: 42, title: "Retry loop has no upper bound", message: "A failed payment request can be retried without a maximum attempt count.", explanation: "Persistent upstream failures may cause repeated requests, unnecessary cost, and a backlog of work.", suggested_fix: "Set a maximum attempt count and use exponential backoff with jitter.", source: "ai", confidence: 89 },
    { id: "CG-003", severity: "high", category: "Security", file_path: "src/api/webhook.py", line: 117, title: "Webhook signature verification is missing", message: "The handler appears to process a webhook payload before validating its signature.", explanation: "An unauthenticated sender may be able to submit forged events. Confirm the full request path before treating this as a verified vulnerability.", suggested_fix: "Verify the provider signature against the raw request body before processing the event.", source: "ai", confidence: 83 },
    { id: "CG-004", severity: "medium", category: "Performance", file_path: "src/reports/query.py", line: 29, title: "Potential repeated database query", message: "The loop appears to fetch related records separately for each report row.", explanation: "This may create an N+1 query pattern as the report grows.", suggested_fix: "Consider eager loading or a batched query, then compare query counts with a test fixture.", source: "ai", confidence: 76 },
    { id: "CG-005", severity: "low", category: "Maintainability", file_path: "src/config.py", line: 16, title: "Use a named constant for the timeout", message: "The timeout value is embedded directly in the request call.", explanation: "A named configuration value is easier to tune consistently across environments.", suggested_fix: "Move the timeout into validated application configuration.", source: "static", confidence: 94 }
  ]
};