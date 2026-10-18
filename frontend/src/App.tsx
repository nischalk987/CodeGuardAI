import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Activity, ArrowUpRight, Bell, BookOpenCheck, Bot, Bug, Check, ChevronDown,
  CircleAlert, Clock3, Code2, FileCode2, Filter, GitPullRequest, LayoutDashboard,
  Search, ShieldCheck, Sparkles, Terminal, Zap
} from "lucide-react";
import { demoReview } from "./demo";
import type { Finding, Review, Severity } from "./types";

type FindingFilter = "all" | "security" | "performance" | "quality";
const severityOrder: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3 };

export default function App() {
  const [review, setReview] = useState<Review>(demoReview);
  const [apiConnected, setApiConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FindingFilter>("all");
  const [selected, setSelected] = useState(demoReview.findings[0].id);
  const [showToast, setShowToast] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/reviews/demo", { signal: controller.signal })
      .then((response) => { if (!response.ok) throw new Error("API unavailable"); return response.json() as Promise<Review>; })
      .then((data) => { setReview(data); setSelected(data.findings[0]?.id ?? ""); setApiConnected(true); })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") return;
        setReview(demoReview); setApiConnected(false);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const visibleFindings = useMemo(() => review.findings
    .filter((finding) => {
      const matchesQuery = [finding.title, finding.file_path, finding.category, finding.message].join(" ").toLowerCase().includes(query.toLowerCase());
      const category = finding.category.toLowerCase();
      const matchesFilter = filter === "all" ||
        (filter === "security" && category === "security") ||
        (filter === "performance" && category === "performance") ||
        (filter === "quality" && ["maintainability", "reliability"].includes(category));
      return matchesQuery && matchesFilter;
    }).sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]),
    [review.findings, query, filter]);

  const selectedFinding = visibleFindings.find((item) => item.id === selected) ?? visibleFindings[0];

  function showDemoMessage() {
    setShowToast(true);
    window.setTimeout(() => setShowToast(false), 3200);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#" aria-label="CodeGuard AI home">
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
        <header className="topbar"><div className="breadcrumb">Workspace <span>/</span> <strong>Overview</strong></div><div className="topbar-actions">
          <span className={"connection-pill " + (apiConnected ? "connected" : "demo")}><span className="status-dot" />{loading ? "Connecting…" : apiConnected ? "API connected" : "Demo mode"}</span>
          <button className="icon-button" aria-label="Notifications" title="Notifications"><Bell size={17} /><i /></button><div className="topbar-avatar">N</div>
        </div></header>

        <div className="content-wrap">
          <section className="welcome-row"><div>
            <div className="eyebrow"><span className="eyebrow-line" /> CODE INTELLIGENCE, REIMAGINED</div>
            <h1>Review code.<br /><span>Ship with confidence.</span></h1>
            <p className="welcome-description">Your command center for bugs, security risks, and better code.</p>
            <div className="welcome-meta"><span className="demo-label"><span /> {apiConnected ? "API SAMPLE REVIEW" : "INTERACTIVE DEMO DATA"}</span><span className="meta-separator">·</span><span><Clock3 size={13} /> Updated moments ago</span></div>
          </div>
          <div className="hero-art" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="hero-shield"><ShieldCheck size={55} /></div><span className="float-icon float-one"><Bug size={18} /></span><span className="float-icon float-two"><Code2 size={18} /></span><span className="float-icon float-three"><Sparkles size={17} /></span><div className="hero-glow" /></div>
          </section>

          <section className="metrics-grid" aria-label="Finding summary">
            <MetricCard label="Total findings" value={review.summary.total_findings} hint="Across this sample review" icon={<Bug size={17} />} kind="neutral" />
            <MetricCard label="Critical" value={review.summary.critical} hint="Needs immediate attention" icon={<CircleAlert size={17} />} kind="critical" trend="Prioritize first" />
            <MetricCard label="High severity" value={review.summary.high} hint="Potential impact detected" icon={<ShieldCheck size={17} />} kind="high" trend="Review soon" />
            <MetricCard label="Risk index" value={review.risk_score + "/100"} hint="Illustrative demo score" icon={<Activity size={17} />} kind="risk" trend="Elevated" />
          </section>

          <section className="review-section" id="findings">
            <div className="section-heading"><div><div className="section-kicker">LATEST ANALYSIS</div><h2>Review workspace <span className="count-badge">{visibleFindings.length}</span></h2></div><button className="primary-button" onClick={showDemoMessage}><Sparkles size={16} /> Run demo scan <ArrowUpRight size={15} /></button></div>
            <div className="review-context"><div className="repo-icon"><Code2 size={19} /></div><div className="repo-detail"><strong>{review.repository}</strong><span><GitPullRequest size={13} /> {review.branch} <span className="branch-status"><Check size={11} /> Review complete</span></span></div><div className="context-spacer" /><span className="demo-chip">DEMO</span><button className="secondary-button" onClick={() => { setQuery(""); setFilter("all"); }}> <Filter size={14} /> Reset filters</button></div>
            <div className="filter-bar"><div className="filter-tabs" role="tablist" aria-label="Filter findings">
              <FilterTab active={filter === "all"} onClick={() => setFilter("all")}>All findings <span>{review.findings.length}</span></FilterTab>
              <FilterTab active={filter === "security"} onClick={() => setFilter("security")}>Security</FilterTab>
              <FilterTab active={filter === "performance"} onClick={() => setFilter("performance")}>Performance</FilterTab>
              <FilterTab active={filter === "quality"} onClick={() => setFilter("quality")}>Quality</FilterTab>
            </div><label className="search-box"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search findings…" aria-label="Search findings" /></label></div>
            <div className="findings-layout">
              <div className="findings-list"><div className="list-heading"><span>FINDINGS</span><span>SEVERITY <ChevronDown size={12} /></span></div>
                {visibleFindings.map((finding) => <FindingRow key={finding.id} finding={finding} active={selectedFinding?.id === finding.id} onClick={() => setSelected(finding.id)} />)}
                {visibleFindings.length === 0 && <div className="empty-state"><Search size={22} /><strong>No findings match</strong><span>Try another search or filter.</span></div>}
                <div className="list-footer"><span><span className="tiny-green-dot" /> Analysis completed</span><span>{visibleFindings.length} shown</span></div>
              </div>
              <div className="detail-panel" id="analysis">{selectedFinding ? <FindingDetail finding={selectedFinding} /> : <div className="empty-detail">Select a finding to inspect its details.</div>}</div>
            </div>
          </section>

          <section className="bottom-grid" id="architecture">
            <div className="bottom-card"><div className="bottom-icon ai-icon"><Bot size={19} /></div><div className="bottom-copy"><span className="section-kicker">AI REVIEWER</span><h3>Context-aware insights</h3><p>Groq integration is planned for structured explanations, separated from deterministic checks.</p><a href="https://github.com/nischalk987/CodeGuardAI/issues/4" target="_blank" rel="noreferrer">Explore implementation issue <ArrowUpRight size={13} /></a></div><div className="bottom-spark"><Sparkles size={40} /></div></div>
            <div className="bottom-card"><div className="bottom-icon cli-icon"><Terminal size={19} /></div><div className="bottom-copy"><span className="section-kicker">DEVELOPER TOOLING</span><h3>Scan from your terminal</h3><p>Planned local CLI for repeatable scans, JSON output, and severity-based exit codes in CI.</p><a href="https://github.com/nischalk987/CodeGuardAI/issues/5" target="_blank" rel="noreferrer">Explore CLI issue <ArrowUpRight size={13} /></a></div><div className="terminal-mini"><span>$ codeguard scan .</span><span className="terminal-ok">✓ ready to build</span><span className="terminal-cursor">_</span></div></div>
          </section>

          <footer className="page-footer"><span>© 2026 CodeGuard AI <span className="footer-dot">·</span> Built for developers, by developers.</span><span><span className="footer-live-dot" /> Starter environment <span className="footer-dot">·</span> <a href="https://github.com/nischalk987/CodeGuardAI" target="_blank" rel="noreferrer">GitHub repository <ArrowUpRight size={11} /></a></span></footer>
        </div>
      </main>
      {showToast && <div className="toast"><Check size={17} /><div><strong>Demo scan preview</strong><span>This starter uses labelled sample findings. Live scanning is on the roadmap.</span></div><button onClick={() => setShowToast(false)} aria-label="Dismiss">×</button></div>}
      <a className="floating-terminal" href="https://github.com/nischalk987/CodeGuardAI/issues/5" target="_blank" rel="noreferrer"><Terminal size={15} /> CLI roadmap</a>
    </div>
  );
}

function MetricCard({ label, value, hint, icon, kind, trend }: { label: string; value: string | number; hint: string; icon: ReactNode; kind: string; trend?: string }) {
  return <article className={"metric-card metric-" + kind}><div className="metric-top"><span>{label}</span><span className="metric-icon">{icon}</span></div><div className="metric-value">{value}</div><div className="metric-bottom"><span>{hint}</span>{trend && <span className="metric-trend">{trend}</span>}</div></article>;
}
function FilterTab({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return <button className={"filter-tab " + (active ? "selected" : "")} role="tab" aria-selected={active} onClick={onClick}>{children}</button>;
}
function FindingRow({ finding, active, onClick }: { finding: Finding; active: boolean; onClick: () => void }) {
  return <button className={"finding-row " + (active ? "finding-active" : "")} onClick={onClick}><span className={"severity-mark severity-" + finding.severity} /><span className="finding-main"><span className="finding-title">{finding.title}</span><span className="finding-location"><FileCode2 size={12} /> {finding.file_path} <span>:{finding.line}</span></span></span><span className={"severity-tag tag-" + finding.severity}>{finding.severity}</span></button>;
}
function FindingDetail({ finding }: { finding: Finding }) {
  return <article className="detail-content">
    <div className="detail-topline"><span className="section-kicker">FINDING DETAILS</span><span className={"severity-tag tag-" + finding.severity}>{finding.severity}</span></div>
    <div className="detail-title-row"><div className={"detail-symbol symbol-" + finding.severity}><ShieldCheck size={20} /></div><div><h3>{finding.title}</h3><span className="detail-id">{finding.id} <span>·</span> {finding.category}</span></div></div>
    <p className="detail-message">{finding.message}</p>
    <div className="code-location"><div><FileCode2 size={14} /><span>{finding.file_path}</span></div><span className="line-number">L{finding.line}</span></div>
    <div className="code-preview"><div className="code-gutter">{finding.line - 1}<br />{finding.line}<br />{finding.line + 1}</div><pre><span className="code-comment">// flagged by CodeGuard</span>{"\n"}<span className="code-warning">{finding.title}</span>{"\n"}<span className="code-muted">// inspect this path before shipping</span></pre></div>
    <div className="explanation-block"><div className="explanation-title"><span className="explanation-icon"><Sparkles size={14} /></span> WHY IT MATTERS</div><p>{finding.explanation}</p></div>
    <div className="fix-block"><div className="fix-heading"><span><Check size={14} /> SUGGESTED DIRECTION</span><span className="suggested-badge">PROPOSAL</span></div><p>{finding.suggested_fix}</p></div>
    <div className="detail-metadata"><span>Source <strong>{finding.source === "static" ? "Static rule" : "AI suggestion"}</strong></span><span>Confidence <strong>{finding.confidence}% <span className="confidence-track"><i style={{ width: String(finding.confidence) + "%" }} /></span></strong></span></div>
    <p className="disclaimer"><CircleAlert size={13} /> Demo findings are illustrative, not the result of scanning a real repository.</p>
  </article>;
}