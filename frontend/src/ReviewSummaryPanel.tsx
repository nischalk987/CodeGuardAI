import { ArrowDownRight, ArrowUpRight, ShieldCheck } from "lucide-react";
import type { Finding, FindingDispositionMap } from "./types";

interface ReviewSummaryPanelProps {
  riskScore: number;
  visibleFindings: Finding[];
  dispositions: FindingDispositionMap;
  onSelectFinding: (id: string) => void;
}

export function ReviewSummaryPanel({ riskScore, visibleFindings, dispositions, onSelectFinding }: ReviewSummaryPanelProps) {
  const keyFindings = visibleFindings.slice(0, 3);
  const openFindings = visibleFindings.filter((finding) =>
    (dispositions[finding.id]?.decision ?? "open") === "open");
  const nextAction = openFindings.some((finding) => finding.severity === "critical" || finding.severity === "high")
    ? "Review critical and high findings first. Confirm the cited evidence before changing code."
    : openFindings.length
      ? "Validate the remaining evidence, then accept or dismiss each finding."
      : visibleFindings.length
        ? "No open findings in this view. Revisit accepted or dismissed items before merging."
        : "No findings match the current filters. Clear or adjust filters to review the full result.";

  return <section className="review-overview" aria-label="Review summary">
    <div className="overview-risk">
      <span className="section-kicker">RISK OVERVIEW</span>
      <div className="overview-score"><ShieldCheck size={20} aria-hidden="true" /><strong>{riskScore}</strong><span>/ 100</span></div>
      <p>Severity-weighted review signal. It is not a probability of a breach.</p>
      <span className="overview-visible">{visibleFindings.length} visible finding{visibleFindings.length === 1 ? "" : "s"}</span>
    </div>
    <div className="overview-key-findings">
      <span className="section-kicker">KEY FINDINGS · RANKED</span>
      {keyFindings.length ? <ol>
        {keyFindings.map((finding, index) => <li key={finding.id}>
          <button onClick={() => onSelectFinding(finding.id)} aria-label={`View ranked finding ${index + 1}: ${finding.severity}, ${finding.title}, ${finding.file_path}, line ${finding.line}`}>
            <span className={`overview-severity severity-${finding.severity}`} aria-hidden="true" />
            <span><strong>{finding.title}</strong><small>{finding.file_path}:{finding.line}</small></span>
            {index === 0 ? <ArrowUpRight size={14} aria-hidden="true" /> : <ArrowDownRight size={14} aria-hidden="true" />}
          </button>
        </li>)}
      </ol> : <p className="overview-empty">No key findings in the current filtered view.</p>}
    </div>
    <div className="overview-next-step">
      <span className="section-kicker">SUGGESTED NEXT ACTION</span>
      <p>{nextAction}</p>
      <span className="ranking-note">Order: severity → confidence signal → changed-line match → location.</span>
    </div>
  </section>;
}
