import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Activity, ArrowUpRight, BookOpen, Boxes, CheckCircle2, CircleAlert, Clock3, ExternalLink, FolderGit2, GitBranch, GitPullRequest, Plus, Search, Server, ShieldCheck, Terminal, Trash2 } from "lucide-react";

export type WorkspacePage = "overview" | "projects" | "reviews" | "findings" | "scanner" | "integrations" | "status";
type WorkspaceRecord = { id: string; name: string; url: string; branch: string; createdAt: string };

const storageKey = "codeguard:workspace-repositories:v1";
const sampleReviews = [
  { id: "demo-review-001", repository: "codeguard/demo-service", branch: "feature/auth-hardening", status: "Sample", findings: 8, date: "Illustrative" },
  { id: "demo-review-002", repository: "codeguard/api-gateway", branch: "main", status: "Sample", findings: 4, date: "Illustrative" },
];

function readRepositories(): WorkspaceRecord[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(storageKey) ?? "[]");
    if (!Array.isArray(value)) return [];
    return value.filter((item): item is WorkspaceRecord => Boolean(item && typeof item.id === "string" && typeof item.name === "string" && typeof item.url === "string" && typeof item.branch === "string" && typeof item.createdAt === "string"));
  } catch { return []; }
}

export function WorkspaceView({ page, onNavigate }: { page: Exclude<WorkspacePage, "overview">; onNavigate: (page: WorkspacePage) => void }) {
  const [repositories, setRepositories] = useState<WorkspaceRecord[]>(readRepositories);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [query, setQuery] = useState("");
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">("checking");
  const [formError, setFormError] = useState("");

  useEffect(() => {
    let active = true;
    fetch("/health", { signal: AbortSignal.timeout(3500) })
      .then((response) => { if (!response.ok) throw new Error("API unavailable"); return response.json(); })
      .then(() => { if (active) setApiStatus("online"); })
      .catch(() => { if (active) setApiStatus("offline"); });
    return () => { active = false; };
  }, []);

  function saveRepository(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    const normalizedUrl = url.trim().replace(/\.git$/i, "");
    if (!/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/.test(normalizedUrl)) {
      setFormError("Enter a valid public GitHub repository URL, for example https://github.com/owner/repository.");
      return;
    }
    const cleanUrl = normalizedUrl.replace(/\/$/, "");
    if (repositories.some((repo) => repo.url.toLowerCase() === cleanUrl.toLowerCase())) {
      setFormError("That repository is already in this browser workspace.");
      return;
    }
    const repo: WorkspaceRecord = {
      id: crypto.randomUUID(),
      name: name.trim() || cleanUrl.split("/").slice(-2).join("/"),
      url: cleanUrl,
      branch: branch.trim() || "main",
      createdAt: new Date().toISOString(),
    };
    const next = [repo, ...repositories];
    setRepositories(next);
    try { localStorage.setItem(storageKey, JSON.stringify(next)); }
    catch { setFormError("Browser storage is unavailable. Enable local storage and try again."); return; }
    setName(""); setUrl(""); setBranch("main"); setShowForm(false);
  }

  function removeRepository(id: string) {
    const next = repositories.filter((repo) => repo.id !== id);
    setRepositories(next);
    try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* Current view still updates. */ }
  }

  const filteredRepositories = repositories.filter((repo) => `${repo.name} ${repo.url} ${repo.branch}`.toLowerCase().includes(query.toLowerCase()));
  const headings: Record<Exclude<WorkspacePage, "overview">, { kicker: string; title: string; description: string }> = {
    projects: { kicker: "YOUR WORKSPACE", title: "Projects & repositories", description: "Keep track of the repositories you want to review. Repository entries are saved in this browser only; they are not connected to GitHub yet." },
    reviews: { kicker: "REVIEW HISTORY", title: "Code reviews", description: "Review history from the connected API will appear here. Sample entries below are illustrative, not real runs." },
    findings: { kicker: "ISSUE TRIAGE", title: "Findings", description: "Browse the sample findings in the dashboard, or connect a real review API to load repository-specific results." },
    scanner: { kicker: "LOCAL TOOLING", title: "CLI scanner", description: "Run CodeGuard scans from your terminal. This page links to the existing CLI instructions; browser-based scanning is not wired up yet." },
    integrations: { kicker: "CONNECT YOUR TOOLCHAIN", title: "API & integrations", description: "Check the API connection and review the integrations that are available in this repository today." },
    status: { kicker: "SERVICE HEALTH", title: "System status", description: "Live health status for the API, plus an honest summary of the local demo's current boundaries." },
  };
  const heading = headings[page];

  return <section className="workspace-page" aria-labelledby="workspace-page-title">
    <div className="workspace-page-heading">
      <div><span className="section-kicker">{heading.kicker}</span><h1 id="workspace-page-title">{heading.title}</h1><p>{heading.description}</p></div>
      {page === "projects" && <button className="primary-button" onClick={() => { setShowForm((value) => !value); setFormError(""); }}><Plus size={16} /> Add repository</button>}
      {page === "reviews" && <button className="secondary-button" onClick={() => onNavigate("overview")}>Open sample review <ArrowUpRight size={14} /></button>}
      {page === "findings" && <button className="secondary-button" onClick={() => onNavigate("overview")}>Explore sample findings <ArrowUpRight size={14} /></button>}
    </div>

    {page === "projects" && <>
      <div className="workspace-notice"><CircleAlert size={16} /><span><strong>Workspace storage:</strong> repositories are saved in local browser storage. Adding a repository here does not clone it, authenticate with GitHub, or start a scan.</span></div>
      {showForm && <form className="workspace-form" onSubmit={saveRepository}>
        <div className="workspace-form-heading"><FolderGit2 size={18} /><div><strong>Add a repository</strong><span>Save a repository shortcut to this browser workspace.</span></div></div>
        <label>Repository name <input value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. My API" maxLength={80} /></label>
        <label>GitHub URL <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://github.com/owner/repository" required /></label>
        <label>Default branch <input value={branch} onChange={(event) => setBranch(event.target.value)} placeholder="main" maxLength={100} /></label>
        {formError && <p className="workspace-form-error" role="alert">{formError}</p>}
        <div className="workspace-form-actions"><button type="button" className="secondary-button" onClick={() => setShowForm(false)}>Cancel</button><button className="primary-button" type="submit"><Plus size={15} /> Save repository</button></div>
      </form>}
      <div className="workspace-toolbar"><label className="search-box"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search repositories…" aria-label="Search repositories" /></label><span>{repositories.length} saved {repositories.length === 1 ? "repository" : "repositories"}</span></div>
      {filteredRepositories.length ? <div className="workspace-repository-grid">{filteredRepositories.map((repo) => <article className="workspace-repository-card" key={repo.id}><div className="workspace-card-icon"><FolderGit2 size={20} /></div><div className="workspace-repo-name">{repo.name}</div><a className="workspace-repo-url" href={repo.url} target="_blank" rel="noreferrer">{repo.url.replace("https://github.com/", "")} <ExternalLink size={12} /></a><span className="workspace-branch"><GitBranch size={13} /> {repo.branch}</span><div className="workspace-repo-actions"><a className="secondary-button" href={repo.url} target="_blank" rel="noreferrer">Open on GitHub <ArrowUpRight size={13} /></a><button className="workspace-icon-action" onClick={() => removeRepository(repo.id)} aria-label={`Remove ${repo.name} from this browser workspace`} title="Remove repository"><Trash2 size={15} /></button></div><small>Saved locally · {new Date(repo.createdAt).toLocaleDateString()}</small></article>)}</div> : <div className="workspace-empty"><FolderGit2 size={28} /><h3>{query ? "No repositories found" : "Your workspace is ready"}</h3><p>{query ? "Try another repository name or URL." : "Add a GitHub repository shortcut to start organizing your workspace."}</p>{!query && <button className="primary-button" onClick={() => setShowForm(true)}><Plus size={15} /> Add your first repository</button>}</div>}
    </>}

    {page === "reviews" && <><div className="workspace-stats"><article><span>Saved repositories</span><strong>{repositories.length}</strong></article><article><span>Live API</span><strong>{apiStatus === "online" ? "Online" : apiStatus === "offline" ? "Offline" : "Checking…"}</strong></article><article><span>Real review runs</span><strong>Not connected</strong></article></div><div className="workspace-table"><div className="workspace-table-head"><span>REPOSITORY</span><span>BRANCH</span><span>STATUS</span><span>FINDINGS</span><span>DATE</span></div>{sampleReviews.map((review) => <button className="workspace-table-row" key={review.id} onClick={() => onNavigate("overview")}><span><GitPullRequest size={15} />{review.repository}</span><span>{review.branch}</span><span><i className="workspace-sample-dot" />{review.status}</span><span>{review.findings}</span><span>{review.date}</span></button>)}</div></>}
    {page === "findings" && <div className="workspace-feature-card"><ShieldCheck size={24} /><div><h3>Sample findings are available</h3><p>The current dashboard includes filterable, illustrative findings with evidence panels and local triage controls. They are not results from a scan of your repository.</p><button className="primary-button" onClick={() => onNavigate("overview")}>Open findings dashboard <ArrowUpRight size={14} /></button></div></div>}
    {page === "scanner" && <div className="workspace-feature-grid"><article className="workspace-feature-card"><Terminal size={24} /><div><h3>Run a local scan</h3><p>From the repository root, install the backend package and run the CLI against a local file or directory.</p><pre>cd backend{"\n"}python -m pip install -e ".[dev]"{"\n"}codeguard scan path/to/source</pre><a className="secondary-button" href="https://github.com/nischalk987/CodeGuardAI/tree/main/backend" target="_blank" rel="noreferrer">CLI documentation <ArrowUpRight size={13} /></a></div></article><article className="workspace-feature-card"><BookOpen size={24} /><div><h3>Before scanning</h3><p>Source stays local for deterministic CLI checks. AI review is a separate opt-in and may send the selected file to your configured provider.</p><a href="https://github.com/nischalk987/CodeGuardAI#run-a-real-local-static-scan" target="_blank" rel="noreferrer">Read the scan guide <ArrowUpRight size={13} /></a></div></article></div>}
    {page === "integrations" && <><div className="workspace-stats"><article><span>FastAPI</span><strong>{apiStatus === "online" ? "Connected" : apiStatus === "offline" ? "Unavailable" : "Checking…"}</strong></article><article><span>GitHub App</span><strong>Webhook foundation</strong></article><article><span>AI provider</span><strong>Optional</strong></article></div><div className="workspace-integration-list"><div><Server size={19} /><span><strong>FastAPI</strong><small>Health endpoint is checked from this page.</small></span><b className={apiStatus === "online" ? "workspace-status-good" : "workspace-status-muted"}>{apiStatus === "online" ? "Online" : apiStatus === "offline" ? "Offline" : "Checking"}</b></div><div><GitPullRequest size={19} /><span><strong>GitHub pull requests</strong><small>Webhook intake exists; full diff analysis and inline comments are not complete.</small></span><b className="workspace-status-muted">Partial</b></div><div><Activity size={19} /><span><strong>Groq / Hugging Face</strong><small>Optional AI review requires backend credentials and explicit opt-in.</small></span><b className="workspace-status-muted">Optional</b></div></div></>}
    {page === "status" && <><div className="workspace-health-card"><span className={apiStatus === "online" ? "workspace-health-icon good" : "workspace-health-icon"}>{apiStatus === "online" ? <CheckCircle2 size={25} /> : apiStatus === "offline" ? <CircleAlert size={25} /> : <Activity size={25} />}</span><div><span className="section-kicker">API HEALTH CHECK</span><h3>{apiStatus === "online" ? "API is responding" : apiStatus === "offline" ? "API could not be reached" : "Checking API…"}</h3><p>{apiStatus === "online" ? "The /health endpoint responded successfully." : apiStatus === "offline" ? "Start the FastAPI backend or use Docker Compose, then retry the health check." : "Waiting for the backend health endpoint."}</p><button className="secondary-button" onClick={() => { setApiStatus("checking"); fetch("/health", { signal: AbortSignal.timeout(3500) }).then((response) => { if (!response.ok) throw new Error(); return response.json(); }).then(() => setApiStatus("online")).catch(() => setApiStatus("offline")); }}>Check again <Activity size={14} /></button></div></div><div className="workspace-notice"><CircleAlert size={16} /><span>The UI demo is not a production account system. Authentication, team membership, and server-backed repository ownership need dedicated backend implementation.</span></div></>}
  </section>;
}
