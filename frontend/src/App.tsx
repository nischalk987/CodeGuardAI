import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity, ArrowUpRight, Bell, BookOpenCheck, Bot, Bug, Check, ChevronDown,
  CircleAlert, Clock3, Code2, FileCode2, Filter, GitPullRequest, LayoutDashboard,
  Search, ShieldCheck, Sparkles, Terminal, Zap,
} from "lucide-react";
import { demoDiffFiles, demoReview } from "./demo";
import { DismissReasonDialog } from "./DismissReasonDialog";
import { ReviewDiff } from "./ReviewDiff";
import { ReviewSummaryPanel } from "./ReviewSummaryPanel";
import { changedLineKeys, filterFindings, findingCounts, isReview } from "./review";
import type { Finding, FindingDecision, FindingDisposition, FindingDispositionMap, Review, Severity } from "./types";

type FindingFilter = "all" | "security" | "performance" | "quality";
const dispositionStorageKey = (reviewId: string) => `codeguard:review-dispositions:${reviewId}`;

export default function App() {
  const [review, setReview] = useState<Review>(demoReview);
  const [apiConnected, setApiConnected] = useState(false);
  const [apiError, setApiError] = useState("");
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FindingFilter>("all");
  const [severityFilter, setSeverityFilter] = useState<"all" | Severity>("all");
  const [selected, setSelected] = useState(demoReview.findings[0].id);
  const [dispositions, setDispositions] = useState<FindingDispositionMap>(() => readDispositions(demoReview));
  const [dispositionReviewId, setDispositionReviewId] = useState(demoReview.review_id);
  const [dismissTarget, setDismissTarget] = useState<Finding | null>(null);
  const [showToast, setShowToast] = useState(false);
  const [diffNavigationVersion, setDiffNavigationVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/reviews/demo", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Sample review API unavailable");
        return response.json() as Promise<unknown>;
      })
      .then((data) => {
        if (!isReview(data)) throw new Error("Sample review API returned an invalid response");
        setReview(data);
        setSelected(data.findings[0]?.id ?? "");
        setApiConnected(true);
        setApiError("");
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") return;
        setReview(demoReview);
        setSelected(demoReview.findings[0]?.id ?? "");
        setApiConnected(false);
        setApiError("Sample API unavailable. Showing the labelled local demo review instead.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (dispositionReviewId !== review.review_id) {
      setDispositions(readDispositions(review));
      setDispositionReviewId(review.review_id);
    }
  }, [dispositionReviewId, review]);

  useEffect(() => {
    if (dispositionReviewId !== review.review_id) return;
    try {
      window.localStorage.setItem(dispositionStorageKey(review.review_id), JSON.stringify(dispositions));
    } catch {
      // Triage remains usable for this page even when browser storage is disabled.
    }
  }, [dispositionReviewId, dispositions, review.review_id]);

  const isDemo = review.review_id === demoReview.review_id;
  const diffFiles = review.diff_files ?? (isDemo ? demoDiffFiles : []);
  const changedLines = useMemo(() => changedLineKeys(diffFiles), [diffFiles]);
  const visibleFindings = useMemo(
    () => filterFindings(review.findings, query, filter, severityFilter, changedLines),
    [review.findings, query, filter, severityFilter, changedLines],
  );
  const visibleCounts = useMemo(() => findingCounts(visibleFindings), [visibleFindings]);
  const selectedFinding = visibleFindings.find((item) => item.id === selected) ?? visibleFindings[0];

  function showDemoMessage() {
    setShowToast(true);
  }

  function viewFinding(id: string) {
    setSelected(id);
    setDiffNavigationVersion((version) => version + 1);
  }

  function setFindingDisposition(id: string, decision: FindingDecision, reason?: string) {
    setDispositions((current) => ({
      ...current,
      [id]: decision === "open" ? { decision: "open" } : { decision, ...(reason ? { reason } : {}) },
    }));
  }

  function toggleAccepted(id: string) {
    setFindingDisposition(id, dispositions[id]?.decision === "accepted" ? "open" : "accepted");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#overview" aria-label="CodeGuard AI home">
          <span className="brand-mark"><ShieldCheck size={22} /></span>
          <span className="brand-copy">codeguard<span>AI</span><small>CODE INTELLIGENCE</small></span>
        </a>
        <div className="workspace-picker"><div className="workspace-avatar">N</div><div className="workspace-meta"><strong>Personal workspace</strong><span>Developer plan</span></div><ChevronDown size={15} /></div>
        <p className="nav-label">WORKSPACE</p>
        <nav className="side-nav" aria-label="Main navigation">
          <a className="nav-item active" href="#overview"><LayoutDashboard size={17} /> Overview <span className="nav-pip" /></a>
          <a className="nav-item" href="#findings"><GitPullRequest size={17} /> Code reviews <span className="nav-count">3</span></a>
          <a className="nav-item" href="#findings"><Bug size={17} /> Findings</a>
          <a className="nav-item" href="#analysis"><Terminal size={17} /> CLI scanner <span className="soon-tag">BETA</span></a>
        </nav>
        <p className="nav-label nav-label-spaced">DEVELOP</p>
        <nav className="side-nav" aria-label="Developer links">
          <a className="nav-item" href="#architecture"><Code2 size={17} /> API & integrations</a>
          <a className="nav-item" href="https://github.com/nischalk987/CodeGuardAI/issues" target="_blank" rel="noreferrer"><BookOpenCheck size={17} /> Project roadmap <ArrowUpRight className="external-icon" size={14} /></a>
        </nav>
        <div className="sidebar-bottom">
          <div className="usage-card"><div className="usage-head"><span>MONTHLY ANALYSIS</span><Zap size={14} /></div><div className="usage-numbers"><strong>128</strong><span>/ 500 sample scans</span></div><div className="usage-track"><span /></div><p>Illustrative workspace metric</p></div>
          <a className="nav-item settings-link" href="#architecture"><Activity size={17} /> System status <span className="status-dot" /></a>
          <div className="profile-row"><div className="profile-avatar">CG</div><div className="profile-meta"><strong>CodeGuard Dev</strong><span>Builder workspace</span></div><ChevronDown size={15} /></div>
        </div>
      </aside>

      <main className="main-area" id="overview">
        <header className="topbar">
          <div className="breadcrumb">Workspace <span>/</span> <strong>Overview</strong></div>
          <div className="topbar-actions">
            <span className={`connection-pill ${apiConnected ? "connected" : "demo"}`} role="status" aria-live="polite">
              <span className="status-dot" />{loading ? "Loading sample…" : apiConnected ? "Sample API loaded" : "Demo mode"}
            </span>
            <button className="icon-button" aria-label="Notifications" title="Notifications"><Bell size={17} /><i /></button>
            <div className="topbar-avatar" aria-label="Personal workspace">N</div>
          </div>
        </header>

        <div className="content-wrap">
          <section className="welcome-row">
            <div>
              <div className="eyebrow"><span className="eyebrow-line" /> CODE INTELLIGENCE, REIMAGINED</div>
              <h1>Review code.<br /><span>Ship with confidence.</span></h1>
              <p className="welcome-description">Your command center for bugs, security risks, and better code.</p>
              <div className="welcome-meta"><span className="demo-label"><span /> DEMO DATA · SAMPLE REVIEW</span><span className="meta-separator">·</span><span><Clock3 size={13} /> {apiConnected ? "Loaded from sample API" : "Local sample fallback"}</span></div>
            </div>
            <div className="hero-art" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="hero-shield"><ShieldCheck size={55} /></div><span className="float-icon float-one"><Bug size={18} /></span><span className="float-icon float-two"><Code2 size={18} /></span><span className="float-icon float-three"><Sparkles size={17} /></span><div className="hero-glow" /></div>
          </section>

          {apiError && <div className="api-fallback-banner" role="status"><CircleAlert size={16} />{apiError}</div>}
          {loading && <div className="loading-banner" role="status">Loading review sample. The visible sample data is labelled as demo content.</div>}
          {review.status === "failed" && <div className="review-status-banner" role="alert">Review did not complete. {review.failure_reason ?? "Try again or inspect the review status."}</div>}
          {(review.status === "queued" || review.status === "running") && <div className="review-status-banner" role="status">Review is {review.status}. Findings may be incomplete until processing finishes.</div>}

          <section className="metrics-grid" aria-label="Visible finding counts">
            <MetricCard label="Critical" value={visibleCounts.critical} hint="Visible findings" icon={<CircleAlert size={17} />} kind="critical" />
            <MetricCard label="High" value={visibleCounts.high} hint="Visible findings" icon={<ShieldCheck size={17} />} kind="high" />
            <MetricCard label="Medium" value={visibleCounts.medium} hint="Visible findings" icon={<Activity size={17} />} kind="medium" />
            <MetricCard label="Low" value={visibleCounts.low} hint="Visible findings" icon={<Check size={17} />} kind="low" />
          </section>

          <ReviewSummaryPanel riskScore={review.risk_score} visibleFindings={visibleFindings}
            dispositions={dispositions} onSelectFinding={viewFinding} />

          <section className="review-section" id="findings">
            <div className="section-heading">
              <div><div className="section-kicker">{isDemo ? "SAMPLE REVIEW · NO REPOSITORY SCAN" : `REVIEW · ${review.status.toUpperCase()}`}</div>
                <h2>Review workspace <span className="count-badge" aria-label={`${visibleFindings.length} visible findings`}>{visibleFindings.length}</span></h2>
              </div>
              <button className="primary-button" onClick={showDemoMessage}><Sparkles size={16} /> Sample walkthrough <ArrowUpRight size={15} /></button>
            </div>
            <div className="review-context">
              <div className="repo-icon"><Code2 size={19} /></div>
              <div className="repo-detail"><strong>{review.repository}</strong><span><GitPullRequest size={13} /> {review.branch} <span className="branch-status"><Check size={11} /> {review.status}</span></span></div>
              <div className="context-spacer" />
              {isDemo && <span className="demo-chip">DEMO DATA</span>}
              <button className="secondary-button" onClick={() => { setQuery(""); setFilter("all"); setSeverityFilter("all"); }} aria-label="Reset all filters"><Filter size={14} /> Reset filters</button>
            </div>
            <div className="filter-bar">
              <div className="filter-tabs" role="group" aria-label="Filter by category">
                <FilterTab active={filter === "all"} onClick={() => setFilter("all")}>All findings <span>{review.findings.length}</span></FilterTab>
                <FilterTab active={filter === "security"} onClick={() => setFilter("security")}>Security</FilterTab>
                <FilterTab active={filter === "performance"} onClick={() => setFilter("performance")}>Performance</FilterTab>
                <FilterTab active={filter === "quality"} onClick={() => setFilter("quality")}>Quality</FilterTab>
              </div>
              <div className="filter-actions">
                <label className="severity-select-label">Severity<select aria-label="Filter by severity" value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value as "all" | Severity)}><option value="all">All severities</option><option value="critical">Critical</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
                <label className="search-box"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search findings…" aria-label="Search findings" /></label>
              </div>
            </div>
            <p className="ranking-explanation">Findings are ordered deterministically by severity, confidence signal, changed-line match, then file and line. Confidence is not a calibrated probability.</p>

            <div className="findings-layout">
              <div className="findings-list">
                <div className="list-heading"><span>FINDINGS · {visibleFindings.length} VISIBLE</span><span>RANKED PRIORITY</span></div>
                {visibleFindings.map((finding, index) => <FindingRow key={finding.id} finding={finding} rank={index + 1}
                  active={selectedFinding?.id === finding.id} disposition={dispositions[finding.id]?.decision ?? finding.status ?? "open"}
                  onClick={() => viewFinding(finding.id)} />)}
                {visibleFindings.length === 0 && <div className="empty-state"><Search size={22} /><strong>No findings match</strong><span>Try another search or filter.</span></div>}
                <div className="list-footer"><span><span className="tiny-green-dot" /> {visibleFindings.length} visible of {review.findings.length}</span><span>Counts reflect active filters</span></div>
              </div>
              <div className="detail-panel review-inspector" id="analysis">
                {selectedFinding ? <>
                  <ReviewDiff files={diffFiles} findings={visibleFindings} selectedFindingId={selectedFinding.id}
                    onSelectFinding={viewFinding} isDemo={isDemo} navigationVersion={diffNavigationVersion} />
                  <FindingDetail finding={selectedFinding}
                    disposition={dispositions[selectedFinding.id] ?? { decision: selectedFinding.status === "accepted" || selectedFinding.status === "dismissed" ? selectedFinding.status : "open" }}
                    onAccept={() => toggleAccepted(selectedFinding.id)} onDismiss={() => setDismissTarget(selectedFinding)}
                    onReopen={() => setFindingDisposition(selectedFinding.id, "open")}
                    onViewDiff={() => viewFinding(selectedFinding.id)} isDemo={isDemo} />
                </> : <div className="empty-detail"><Search size={22} /><strong>No finding selected</strong><span>Change the filters or choose a finding to inspect its evidence.</span></div>}
              </div>
            </div>
          </section>

          <section className="bottom-grid" id="architecture">
            <div className="bottom-card"><div className="bottom-icon ai-icon"><Bot size={19} /></div><div className="bottom-copy"><span className="section-kicker">ADVISORY AI</span><h3>Suggestions stay separate</h3><p>AI-generated findings are labelled as hypotheses. Confirm the cited code and evidence before acting.</p><a href="https://github.com/nischalk987/CodeGuardAI/issues/4" target="_blank" rel="noreferrer">Reviewer implementation <ArrowUpRight size={13} /></a></div><div className="bottom-spark"><Sparkles size={40} /></div></div>
            <div className="bottom-card"><div className="bottom-icon cli-icon"><Terminal size={19} /></div><div className="bottom-copy"><span className="section-kicker">DEVELOPER TOOLING</span><h3>Scan locally from your terminal</h3><p>The CodeGuard CLI runs deterministic checks locally and supports machine-readable output.</p><a href="https://github.com/nischalk987/CodeGuardAI/tree/main/backend" target="_blank" rel="noreferrer">Backend CLI documentation <ArrowUpRight size={13} /></a></div><div className="terminal-mini"><span>$ codeguard scan .</span><span className="terminal-ok">✓ local scan</span><span className="terminal-cursor">_</span></div></div>
          </section>

          <footer className="page-footer"><span>© 2026 CodeGuard AI <span className="footer-dot">·</span> Built for developers, by developers.</span><span><span className="footer-live-dot" /> Starter environment <span className="footer-dot">·</span> <a href="https://github.com/nischalk987/CodeGuardAI" target="_blank" rel="noreferrer">GitHub repository <ArrowUpRight size={11} /></a></span></footer>
        </div>
      </main>
      {showToast && <div className="toast" role="status"><Check size={17} /><div><strong>Demo review walkthrough</strong><span>This sample review uses labelled illustrative findings and excerpts, not analysis of your code.</span></div><button onClick={() => setShowToast(false)} aria-label="Dismiss walkthrough message">×</button></div>}
      <a className="floating-terminal" href="https://github.com/nischalk987/CodeGuardAI/tree/main/backend" target="_blank" rel="noreferrer"><Terminal size={15} /> CLI docs</a>
      <DismissReasonDialog open={Boolean(dismissTarget)} findingTitle={dismissTarget?.title ?? ""}
        onCancel={() => setDismissTarget(null)} onConfirm={(reason) => {
          if (dismissTarget) setFindingDisposition(dismissTarget.id, "dismissed", reason);
          setDismissTarget(null);
        }} />
    </div>
  );
}

function MetricCard({ label, value, hint, icon, kind }: { label: string; value: string | number; hint: string; icon: ReactNode; kind: string }) {
  return <article className={`metric-card metric-${kind}`}><div className="metric-top"><span>{label}</span><span className="metric-icon" aria-hidden="true">{icon}</span></div><div className="metric-value" aria-label={`${value} ${label.toLowerCase()} findings`}>{value}</div><div className="metric-bottom"><span>{hint}</span></div></article>;
}

function FilterTab({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return <button className={`filter-tab ${active ? "selected" : ""}`} aria-pressed={active} onClick={onClick}>{children}</button>;
}

function FindingRow({ finding, rank, active, disposition, onClick }: { finding: Finding; rank: number; active: boolean; disposition: FindingDecision; onClick: () => void }) {
  return <button className={`finding-row ${active ? "finding-active" : ""}`} onClick={onClick} aria-pressed={active}
    aria-label={`Rank ${rank}. ${finding.severity} ${finding.category}: ${finding.title}, ${finding.file_path} line ${finding.line}${disposition !== "open" ? `, ${disposition}` : ""}`}>
    <span className="finding-rank" aria-hidden="true">{String(rank).padStart(2, "0")}</span>
    <span className={`severity-mark severity-${finding.severity}`} aria-hidden="true" />
    <span className="finding-main"><span className="finding-title">{finding.title}</span>
      <span className="finding-location"><FileCode2 size={12} /> {finding.file_path} <span>:{finding.line}</span></span>
      <span className={`finding-source source-${finding.source}`}>{finding.source === "static" ? "DETERMINISTIC RULE" : "AI SUGGESTION · ADVISORY"}</span>
    </span>
    {disposition !== "open" && <span className="decision-tag">{disposition}</span>}
    <span className={`severity-tag tag-${finding.severity}`}>{finding.severity}</span>
  </button>;
}

function FindingDetail({ finding, disposition, onAccept, onDismiss, onReopen, onViewDiff, isDemo }: {
  finding: Finding;
  disposition: FindingDisposition;
  onAccept: () => void;
  onDismiss: () => void;
  onReopen: () => void;
  onViewDiff: () => void;
  isDemo: boolean;
}) {
  return <article className="detail-content" aria-labelledby="finding-detail-title">
    <div className="detail-topline"><span className="section-kicker">FINDING DETAILS</span><span className={`severity-tag tag-${finding.severity}`}>{finding.severity} severity</span></div>
    <div className="detail-title-row"><div className={`detail-symbol symbol-${finding.severity}`} aria-hidden="true"><ShieldCheck size={20} /></div><div><h3 id="finding-detail-title">{finding.title}</h3><span className="detail-id">{finding.id} <span>·</span> {finding.category}</span></div></div>
    <p className="detail-message">{finding.message}</p>
    <div className="code-location"><div><FileCode2 size={14} /><span>{finding.file_path}</span></div><button className="line-link" onClick={onViewDiff} aria-label={`Go to ${finding.file_path}, line ${finding.line}`}>L{finding.line} ↗</button></div>
    {finding.evidence ? <div className="evidence-block"><div className="explanation-title">CITED EVIDENCE <span>LINE {finding.line}</span></div><pre><code>{finding.evidence}</code></pre></div> : <p className="evidence-missing">The API did not include a code excerpt for this finding.</p>}
    <div className="explanation-block"><div className="explanation-title"><span className="explanation-icon"><Sparkles size={14} /></span> WHY IT MATTERS</div><p>{finding.explanation}</p></div>
    <div className="fix-block"><div className="fix-heading"><span><Check size={14} /> SUGGESTED DIRECTION</span><span className="suggested-badge">PROPOSAL · NOT APPLIED</span></div><p>{finding.suggested_fix}</p></div>
    <div className="detail-metadata"><span>Source <strong>{finding.source === "static" ? "Deterministic rule" : "AI suggestion · advisory"}</strong></span>
      <span title="This score is a reviewer confidence signal, not a calibrated probability.">Confidence signal <strong>{finding.confidence}/100</strong></span>
    </div>
    {finding.source === "ai" && <p className="ai-advisory-note">AI findings are hypotheses. Verify the code context before acting.</p>}
    <div className="decision-actions" aria-label="Finding disposition">
      <span role="status" aria-live="polite">{disposition.decision === "open" ? "Not triaged" : `Marked ${disposition.decision}`}</span>
      {disposition.decision === "open" ? <>
        <button className="decision-button" aria-pressed={false} onClick={onAccept}>Accept</button>
        <button className="decision-button dismiss-button" aria-pressed={false} onClick={onDismiss}>Dismiss…</button>
      </> : <button className="decision-button" onClick={onReopen}>Reopen decision</button>}
    </div>
    {disposition.decision === "dismissed" && disposition.reason && <div className="dismissal-reason"><strong>Dismissal reason</strong><p>{disposition.reason}</p><small>Saved in this browser for this review.</small></div>}
    <p className="disclaimer"><CircleAlert size={13} /> {isDemo ? "Demo finding and excerpt are illustrative; no real repository was scanned." : "Review findings are advisory. Confirm the evidence and suggested direction."}</p>
  </article>;
}

function readDispositions(review: Review): FindingDispositionMap {
  const fromApi: FindingDispositionMap = Object.fromEntries(review.findings.flatMap((finding) =>
    finding.status && finding.status !== "fixed" && finding.status !== "open"
      ? [[finding.id, { decision: finding.status }]] : []));
  try {
    const stored: unknown = JSON.parse(window.localStorage.getItem(dispositionStorageKey(review.review_id)) ?? "null");
    if (!stored || typeof stored !== "object" || Array.isArray(stored)) return fromApi;
    const result = { ...fromApi };
    for (const [id, value] of Object.entries(stored)) {
      if (!value || typeof value !== "object") continue;
      const item = value as Partial<FindingDisposition>;
      if (!["open", "accepted", "dismissed"].includes(item.decision ?? "")) continue;
      if (item.decision === "dismissed" && (typeof item.reason !== "string" || item.reason.trim().length < 5)) continue;
      result[id] = { decision: item.decision!, ...(item.reason ? { reason: item.reason } : {}) };
    }
    return result;
  } catch {
    return fromApi;
  }
}
