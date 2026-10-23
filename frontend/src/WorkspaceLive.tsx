import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  Activity, CircleAlert, ExternalLink, FolderGit2, GitBranch, LoaderCircle, Plus,
  RefreshCw, ScanLine, Trash2, Github, FileCode2, ShieldCheck, Unplug, ChevronLeft, Filter,
} from "lucide-react";
import { readAuthToken } from "./AuthPage";

type Repo = { id:string; name:string; url:string; default_branch:string; created_at:string };
type GithubRepo = { id:number; full_name:string; private:boolean; html_url:string; default_branch:string; description?:string|null };
type Branch = { name:string; commit_sha:string };
type SourceFile = { path:string; size:number };
type Finding = { id:string; severity:"critical"|"high"|"medium"|"low"; category:string; file_path:string; line:number; title:string; message:string; explanation:string; suggested_fix:string; source:"static"|"ai"; confidence:number };
type Review = { review_id:string; repository:string; branch:string; ai_review_requested?:boolean; ai_review_status?:"disabled"|"pending"|"completed"|"unavailable"|"failed"; ai_review_message?:string|null; status:"queued"|"running"|"completed"|"failed"; risk_score:number; created_at:string; updated_at?:string; summary?:{critical:number;high:number;medium:number;low:number;total_findings:number}; findings?:Finding[]; failure_reason?:string|null; correlation_id?:string|null };
type Tab = "projects" | "reviews" | "scan";
type SeverityFilter = "all" | Finding["severity"];
const terminal=(s:Review["status"])=>s==="completed"||s==="failed";
const message=(e:unknown,fallback:string)=>e instanceof Error?e.message:fallback;
const encoded=(s:string)=>encodeURIComponent(s);

async function api<T>(path:string, init:RequestInit = {}):Promise<T>{
  const token=readAuthToken();
  if(!token) throw new Error("Your session has expired. Please sign in again.");
  const response=await fetch(path,{...init,headers:{"Content-Type":"application/json",Authorization:`Bearer ${token}`,...(init.headers||{})}});
  if(!response.ok){
    const body=await response.json().catch(()=>({}));
    const detail=typeof body.detail==="string"?body.detail:typeof body.error?.message==="string"?body.error.message:null;
    throw new Error(detail||`Request failed (${response.status})`);
  }
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
}

export default function WorkspaceView({userName}:{userName:string}){
  const [tab,setTab]=useState<Tab>("projects");
  const [repos,setRepos]=useState<Repo[]>([]);
  const [reviews,setReviews]=useState<Review[]>([]);
  const [repositoryFilter,setRepositoryFilter]=useState("all");
  const [severityFilter,setSeverityFilter]=useState<SeverityFilter>("all");
  const [selectedReviewId,setSelectedReviewId]=useState("");
  const [selectedReview,setSelectedReview]=useState<Review|null>(null);
  const [detailLoading,setDetailLoading]=useState(false);
  const [name,setName]=useState("");
  const [url,setUrl]=useState("");
  const [manualBranch,setManualBranch]=useState("main");
  const [filePath,setFilePath]=useState("snippet.py");
  const [source,setSource]=useState("");
  const [aiReviewEnabled,setAiReviewEnabled]=useState(false);
  const [repository,setRepository]=useState("local");
  const [scanBranch,setScanBranch]=useState("local");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [loading,setLoading]=useState(true);
  const [githubConnected,setGithubConnected]=useState(false);
  const [githubLogin,setGithubLogin]=useState<string|null>(null);
  const [githubRepos,setGithubRepos]=useState<GithubRepo[]>([]);
  const [selectedRepo,setSelectedRepo]=useState("");
  const [branches,setBranches]=useState<Branch[]>([]);
  const [selectedBranch,setSelectedBranch]=useState("");
  const [files,setFiles]=useState<SourceFile[]>([]);
  const [selectedFile,setSelectedFile]=useState("");
  const [githubBusy,setGithubBusy]=useState(false);

  const recentReviews = reviews.slice(0, 5);
  const filteredReviews = reviews.filter(review =>
    (repositoryFilter === "all" || review.repository === repositoryFilter) &&
    (severityFilter === "all" || (review.findings || []).some(finding => finding.severity === severityFilter))
  );
  const reviewStats = {
    total: reviews.length,
    completed: reviews.filter(review => review.status === "completed").length,
    active: reviews.filter(review => review.status === "queued" || review.status === "running").length,
    failed: reviews.filter(review => review.status === "failed").length,
    findings: reviews.reduce((sum, review) => sum + (review.summary?.total_findings ?? review.findings?.length ?? 0), 0),
    critical: reviews.reduce((sum, review) => sum + (review.summary?.critical ?? review.findings?.filter(f => f.severity === "critical").length ?? 0), 0),
    high: reviews.reduce((sum, review) => sum + (review.summary?.high ?? review.findings?.filter(f => f.severity === "high").length ?? 0), 0),
  };
  const repositoryOptions = [...new Set(reviews.map(review => review.repository).filter(Boolean))].sort((a, b) => a.localeCompare(b));

  const refresh=useCallback(async()=>{
    setLoading(true);setError("");
    try{
      const [r,v]=await Promise.all([api<Repo[]>("/api/v1/workspace/repositories"),api<Review[]>("/api/v1/reviews?limit=100")]);
      setRepos(r);setReviews(v);
    }catch(e){setError(message(e,"Unable to load your workspace."));}
    finally{setLoading(false);}
  },[]);
  const refreshGithubStatus=useCallback(async()=>{
    try{
      const status=await api<{connected:boolean;login:string|null}>("/api/v1/github/oauth/status");
      setGithubConnected(status.connected);setGithubLogin(status.login);
      if(status.connected)setGithubRepos(await api<GithubRepo[]>("/api/v1/github/oauth/repositories"));
      else setGithubRepos([]);
    }catch(e){setGithubConnected(false);setGithubLogin(null);setGithubRepos([]);setError(message(e,"Could not check GitHub connection."));}
  },[]);
  const loadReview=useCallback(async(id:string)=>{
    setSelectedReviewId(id);setDetailLoading(true);setError("");
    try{setSelectedReview(await api<Review>(`/api/v1/reviews/${encoded(id)}`));setTab("reviews");}
    catch(e){setSelectedReview(null);setError(message(e,"Could not load review details."));}
    finally{setDetailLoading(false);}
  },[]);
  const refreshReviewDetail=useCallback(async()=>{
    if(!selectedReviewId)return;
    try{setSelectedReview(await api<Review>(`/api/v1/reviews/${encoded(selectedReviewId)}`));}
    catch(e){setError(message(e,"Could not refresh review status."));}
  },[selectedReviewId]);
  useEffect(()=>{void refresh();void refreshGithubStatus();},[refresh,refreshGithubStatus]);
  // Poll active reviews for real queued/running/completed/failed transitions.
  useEffect(()=>{
    const active=reviews.filter(r=>!terminal(r.status));
    if(active.length===0)return;
    let cancelled=false;
    const poll=async()=>{
      try{
        const updated=await Promise.all(active.map(r=>api<Review>(`/api/v1/reviews/${encoded(r.review_id)}`)));
        if(cancelled)return;
        setReviews(current=>current.map(item=>updated.find(next=>next.review_id===item.review_id)||item));
        if(selectedReviewId){
          const detail=updated.find(item=>item.review_id===selectedReviewId);
          if(detail)setSelectedReview(detail);
        }
      }catch(e){if(!cancelled)setError(message(e,"Review status refresh failed."));}
    };
    const timer=window.setInterval(()=>void poll(),2500);
    return()=>{cancelled=true;window.clearInterval(timer);};
  },[reviews,selectedReviewId]);
  useEffect(()=>{
    if(!selectedReviewId||selectedReview||detailLoading)return;
    void loadReview(selectedReviewId);
  },[selectedReviewId,selectedReview,detailLoading,loadReview]);
  useEffect(()=>{
    const query=new URLSearchParams(window.location.search);
    if(query.get("github")==="connected"){setNotice("GitHub account connected securely.");setTab("projects");void refreshGithubStatus();}
    if(query.get("github")==="error")setError("GitHub authorization did not complete. Try connecting again.");
    if(query.has("github")){query.delete("github");const suffix=query.toString();window.history.replaceState({}, "", window.location.pathname+(suffix?"?"+suffix:"")+window.location.hash);}
  },[refreshGithubStatus]);

  async function connectGithub(){
    setError("");setNotice("");
    try{
      const token=readAuthToken();if(!token)throw new Error("Sign in to CodeGuard before connecting GitHub.");
      const response=await fetch("/api/v1/github/oauth/start",{headers:{Authorization:`Bearer ${token}`}});
      if(!response.ok){const body=await response.json().catch(()=>({}));throw new Error(body.detail||body.error?.message||"Could not start GitHub authorization.");}
      const result=await response.json() as {authorization_url:string};
      if(!result.authorization_url?.startsWith("https://github.com/login/oauth/authorize?"))throw new Error("GitHub returned an invalid authorization URL.");
      window.location.assign(result.authorization_url);
    }catch(e){setError(message(e,"Could not connect to GitHub."));}
  }
  async function disconnectGithub(){
    setGithubBusy(true);setError("");setNotice("");
    try{await api<void>("/api/v1/github/oauth/disconnect",{method:"POST"});setGithubConnected(false);setGithubLogin(null);setGithubRepos([]);setBranches([]);setFiles([]);setSelectedRepo("");setNotice("GitHub account disconnected.");}
    catch(e){setError(message(e,"Could not disconnect GitHub."));}
    finally{setGithubBusy(false);}
  }
  async function selectGithubRepo(fullName:string){
    setSelectedRepo(fullName);setSelectedBranch("");setSelectedFile("");setBranches([]);setFiles([]);setSource("");setError("");setNotice("");
    if(!fullName)return;
    setGithubBusy(true);
    try{
      const [owner,repo]=fullName.split("/",2);
      const result=await api<Branch[]>(`/api/v1/github/oauth/repositories/${encoded(owner)}/${encoded(repo)}/branches`);
      setBranches(result);
      const defaultBranch=result.find(x=>x.name===githubRepos.find(item=>item.full_name===fullName)?.default_branch)?.name||result[0]?.name||"";
      if(defaultBranch){setSelectedBranch(defaultBranch);await loadFiles(fullName,defaultBranch);}
    }catch(e){setError(message(e,"Could not load branches. Check that this repository is accessible."));}
    finally{setGithubBusy(false);}
  }
  async function loadFiles(fullName:string,branchName:string){
    const [owner,repo]=fullName.split("/",2);
    const result=await api<SourceFile[]>(`/api/v1/github/oauth/repositories/${encoded(owner)}/${encoded(repo)}/files?branch=${encoded(branchName)}`);
    setFiles(result);setSelectedFile("");setSource("");
  }
  async function selectBranch(branchName:string){
    setSelectedBranch(branchName);setSelectedFile("");setSource("");setError("");
    if(!selectedRepo||!branchName)return;
    setGithubBusy(true);
    try{await loadFiles(selectedRepo,branchName);}
    catch(e){setFiles([]);setError(message(e,"Could not list source files for this branch."));}
    finally{setGithubBusy(false);}
  }
  async function selectSourceFile(path:string){
    setSelectedFile(path);setSource("");setFilePath(path);setError("");
    if(!selectedRepo||!selectedBranch||!path)return;
    setGithubBusy(true);
    try{
      const [owner,repo]=selectedRepo.split("/",2);
      const result=await api<{path:string;content:string;size:number}>(`/api/v1/github/oauth/repositories/${encoded(owner)}/${encoded(repo)}/file?path=${encoded(path)}&ref=${encoded(selectedBranch)}`);
      setSource(result.content);setNotice(`Loaded ${path} (${result.size.toLocaleString()} bytes).`);setRepository(selectedRepo);setScanBranch(selectedBranch);setTab("scan");
    }catch(e){setError(message(e,"Could not read this source file."));}
    finally{setGithubBusy(false);}
  }
  async function addRepo(e:FormEvent<HTMLFormElement>){
    e.preventDefault();setBusy(true);setError("");setNotice("");
    try{await api<Repo>("/api/v1/workspace/repositories",{method:"POST",body:JSON.stringify({name:name.trim()||undefined,url:url.trim(),default_branch:manualBranch.trim()||"main"})});setName("");setUrl("");setManualBranch("main");setNotice("Repository saved to your account.");await refresh();}
    catch(e){setError(message(e,"Could not save repository."));}
    finally{setBusy(false);}
  }
  async function removeRepo(id:string){
    if(!window.confirm("Remove this repository from your workspace?"))return;
    setError("");setNotice("");
    try{await api<void>(`/api/v1/workspace/repositories/${encoded(id)}`,{method:"DELETE"});setNotice("Repository removed.");await refresh();}
    catch(e){setError(message(e,"Could not remove repository."));}
  }
  async function startScan(e:FormEvent<HTMLFormElement>){
    e.preventDefault();setBusy(true);setError("");setNotice("");
    try{
      const result=await api<Review>("/api/v1/reviews",{method:"POST",body:JSON.stringify({source_code:source,file_path:filePath,repository:repository.trim()||"local",branch:scanBranch.trim()||"local",ai_review:aiReviewEnabled})});
      const record={...result,created_at:new Date().toISOString()};
      setReviews(current=>[record,...current.filter(item=>item.review_id!==result.review_id)]);
      setSelectedReviewId(result.review_id);setSelectedReview(result);setSource("");setTab("reviews");
      setNotice(`Review queued: ${result.review_id}. Status updates automatically.`);
      void refresh();
    }catch(e){setError(message(e,"Could not start the review. Confirm the API and queue are running."));}
    finally{setBusy(false);}
  }

  return <section className="workspace-live">
    <div className="workspace-live-heading"><div><span className="section-kicker">PERSONAL WORKSPACE</span><h1>Welcome, {userName}</h1><p>Start code reviews and follow live status, findings, severity, file paths and line numbers.</p></div><button className="secondary-button" onClick={()=>void refresh()} disabled={loading}><RefreshCw size={14}/> Refresh</button></div>
    <div className="workspace-live-tabs"><button className={tab==="projects"?"selected":""} onClick={()=>{setTab("projects");setError("");}}><FolderGit2 size={15}/> Projects</button><button className={tab==="reviews"?"selected":""} onClick={()=>{setSelectedReviewId("");setSelectedReview(null);setTab("reviews");setError("");}}><Activity size={15}/> Review history</button><button className={tab==="scan"?"selected":""} onClick={()=>{setTab("scan");setError("");}}><ScanLine size={15}/> Scan code</button></div>
    {!loading&&<section className="workspace-dashboard" aria-label="Workspace review statistics">
      <div className="workspace-dashboard-heading"><div><span className="section-kicker">LIVE WORKSPACE</span><h2>Review activity</h2><p>Metrics are calculated from reviews saved to your account, not demo data.</p></div><span className="workspace-live-data-badge"><span/> Persisted data</span></div>
      <div className="workspace-dashboard-metrics">
        <article><span>Total reviews</span><strong>{reviewStats.total}</strong><small>All saved reviews</small></article>
        <article><span>Completed</span><strong>{reviewStats.completed}</strong><small>Successfully analyzed</small></article>
        <article><span>In progress</span><strong>{reviewStats.active}</strong><small>Queued or running</small></article>
        <article><span>Findings</span><strong>{reviewStats.findings}</strong><small>{reviewStats.critical} critical · {reviewStats.high} high</small></article>
      </div>
      <div className="workspace-dashboard-recent"><div className="workspace-dashboard-section-heading"><div><h3>Recent reviews</h3><p>Latest five reviews, newest first.</p></div><button className="secondary-button" onClick={()=>{setSelectedReviewId("");setSelectedReview(null);setTab("reviews");}}>View history <ExternalLink size={13}/></button></div>
      {recentReviews.length===0?<div className="workspace-dashboard-empty"><Activity size={20}/><div><strong>No review activity yet</strong><p>Scan a source file to generate your first real review. Demo findings are intentionally excluded from these metrics.</p></div><button className="primary-button" onClick={()=>setTab("scan")}><ScanLine size={14}/> Start first review</button></div>:<div className="workspace-dashboard-recent-list">{recentReviews.map(review=><button type="button" key={review.review_id} onClick={()=>{setSelectedReview(null);void loadReview(review.review_id);}}><span className="workspace-dashboard-review-main"><strong>{review.repository}</strong><small>{review.branch} · {new Date(review.created_at).toLocaleString()}</small></span><span className={`workspace-live-status status-${review.status}`}>{review.status}</span><span className="workspace-dashboard-review-risk">{review.summary?.total_findings ?? review.findings?.length ?? 0} findings</span><span className="workspace-open-review">Open <ExternalLink size={12}/></span></button>)}</div>}
      {reviewStats.failed>0&&<p className="workspace-dashboard-footnote">{reviewStats.failed} review{reviewStats.failed===1?"":"s"} failed. Open review history to inspect failure details.</p>}
      </div>
    </section>}
    {error&&<div className="workspace-live-error" role="alert"><CircleAlert size={16}/>{error}</div>}
    {notice&&<div className="workspace-live-notice" role="status">{notice}</div>}
    {loading?<div className="workspace-live-empty"><LoaderCircle className="auth-spinner" size={22}/> Loading your account data…</div>:null}
    {!loading&&tab==="projects"&&<>
      <section className="github-connect-panel">
        <div className="github-connect-header"><div className="github-connect-icon"><Github size={21}/></div><div><span className="section-kicker">GITHUB INTEGRATION</span><h2>Connect your repositories</h2><p>Authorize GitHub to see repositories you can access, including private repositories allowed by your GitHub permissions. Tokens stay on the server.</p></div></div>
        {githubConnected?<div className="github-connected-row"><span className="github-state"><ShieldCheck size={15}/> Connected as <strong>{githubLogin||"GitHub user"}</strong></span><button className="secondary-button" onClick={()=>void refreshGithubStatus()} disabled={githubBusy}><RefreshCw size={14}/> Refresh</button><button className="workspace-live-remove" onClick={()=>void disconnectGithub()} disabled={githubBusy}><Unplug size={14}/> Disconnect</button></div>:<button className="primary-button" onClick={()=>void connectGithub()}><Github size={15}/> Connect GitHub account</button>}
        {githubConnected&&<><div className="github-picker-grid"><label>Repository<select value={selectedRepo} onChange={e=>void selectGithubRepo(e.target.value)}><option value="">Select repository…</option>{githubRepos.map(repo=><option key={repo.id} value={repo.full_name}>{repo.full_name}{repo.private?" · private":""}</option>)}</select></label><label>Branch<select value={selectedBranch} onChange={e=>void selectBranch(e.target.value)} disabled={!selectedRepo||githubBusy}><option value="">Select branch…</option>{branches.map(item=><option key={item.name} value={item.name}>{item.name}</option>)}</select></label><label>Source file<select value={selectedFile} onChange={e=>void selectSourceFile(e.target.value)} disabled={!selectedBranch||githubBusy}><option value="">Select source file…</option>{files.map(file=><option key={file.path} value={file.path}>{file.path} ({file.size.toLocaleString()} B)</option>)}</select></label></div><div className="github-picker-footer"><span>{githubBusy?<><LoaderCircle className="auth-spinner" size={14}/> Loading GitHub data…</>:`${githubRepos.length} repositories available · ${files.length} supported source files for selected branch`}</span><span>Source file limit: 40 KB</span></div>{githubRepos.length===0&&!githubBusy&&<p className="github-empty">No accessible repositories were returned. Check the GitHub account and granted repository permissions.</p>}</>}
      </section>
      <form className="workspace-live-form" onSubmit={addRepo}><div className="workspace-live-form-title"><Plus size={17}/><strong>Save a repository shortcut</strong></div><label>Repository name (optional)<input value={name} onChange={e=>setName(e.target.value)} maxLength={120} placeholder="team/my-service"/></label><label>GitHub repository URL<input type="url" value={url} onChange={e=>setUrl(e.target.value)} required placeholder="https://github.com/owner/repository"/></label><label>Default branch<input value={manualBranch} onChange={e=>setManualBranch(e.target.value)} maxLength={100} required/></label><button className="primary-button" type="submit" disabled={busy}>{busy?<LoaderCircle size={15} className="auth-spinner"/>:<Plus size={15}/>} Save shortcut</button></form>
      {repos.length===0?<div className="workspace-live-empty"><FolderGit2 size={28}/><h3>No saved shortcuts</h3><p>Connect GitHub above to browse repositories, or save a URL shortcut to find it quickly later.</p></div>:<div className="workspace-live-grid">{repos.map(repo=><article className="workspace-live-card" key={repo.id}><FolderGit2 size={20}/><h3>{repo.name}</h3><a href={repo.url} target="_blank" rel="noreferrer">{repo.url.replace("https://github.com/","")} <ExternalLink size={12}/></a><span><GitBranch size={13}/>{repo.default_branch}</span><small>Saved {new Date(repo.created_at).toLocaleDateString()}</small><button className="workspace-live-remove" onClick={()=>void removeRepo(repo.id)}><Trash2 size={14}/> Remove</button></article>)}</div>}
    </>}
    {!loading&&tab==="reviews"&&<>
      {detailLoading&&!selectedReview?<div className="workspace-live-empty"><LoaderCircle className="auth-spinner" size={22}/><h3>Loading review details</h3><p>Fetching the selected review from saved workspace data.</p></div>:selectedReviewId&&selectedReview?<section className="review-detail-panel">
        <button className="secondary-button" onClick={()=>{setSelectedReviewId("");setSelectedReview(null);}}><ChevronLeft size={14}/> Back to review history</button>
        <div className="review-detail-heading"><div><span className="section-kicker">REVIEW DETAILS</span><h2>{selectedReview.repository}</h2><p>{selectedReview.branch} · {selectedReview.review_id}</p></div><span className={`workspace-live-status status-${selectedReview.status}`}>{selectedReview.status}</span></div>
        <div className="review-progress" role="status"><span className={selectedReview.status==="queued"?"progress-current":""}>Queued</span><i/><span className={selectedReview.status==="running"?"progress-current":""}>Running</span><i/><span className={selectedReview.status==="completed"?"progress-current":selectedReview.status==="failed"?"progress-failed":""}>{selectedReview.status==="failed"?"Failed":"Completed"}</span><button className="secondary-button" onClick={()=>void refreshReviewDetail()}><RefreshCw size={13}/> Refresh status</button></div>
        {selectedReview.status==="failed"&&<div className="workspace-live-error"><CircleAlert size={15}/>{selectedReview.failure_reason||"The review failed. Check the queue worker and retry."}</div>}
        <div className="review-result-summary"><div><strong>{selectedReview.risk_score}</strong><small>Risk score / 100</small></div><div><strong>{selectedReview.summary?.total_findings??selectedReview.findings?.length??0}</strong><small>Total findings</small></div>{(["critical","high","medium","low"] as const).map(level=><div key={level}><strong>{selectedReview.summary?.[level]??selectedReview.findings?.filter(f=>f.severity===level).length??0}</strong><small>{level}</small></div>)}</div>
        <div className="review-ai-status" role="status"><strong>AI reviewer: {selectedReview.ai_review_requested ? (selectedReview.ai_review_status||"unavailable") : "not requested"}</strong><p>{selectedReview.ai_review_message || (selectedReview.ai_review_requested ? "AI status is not available for this review." : "Deterministic findings are shown independently of optional AI suggestions.")}</p>{selectedReview.ai_review_requested&&selectedReview.ai_review_status==="completed"&&<small>AI-generated findings are suggestions, not confirmed defects.</small>}</div><div className="review-findings-heading"><h3>Findings</h3><span>{selectedReview.status==="completed"?"Actual persisted analyzer results":selectedReview.status==="failed"?"Results unavailable":"Findings will appear when the review completes"}</span></div>
        {selectedReview.status==="completed"&&(selectedReview.findings||[]).length===0?<div className="workspace-live-empty"><ShieldCheck size={25}/><h3>No findings detected</h3><p>The analyzer did not return any findings for the submitted file.</p></div>:<div className="review-findings-list">{(selectedReview.findings||[]).map(finding=><article key={finding.id} className="review-finding-card"><div className="review-finding-top"><span className={`finding-severity severity-${finding.severity}`}>{finding.severity}</span><span>{finding.category}</span><span className={`finding-origin origin-${finding.source}`}>{finding.source==="ai"?"AI suggestion":"Deterministic"}</span><span className="review-finding-location"><FileCode2 size={13}/>{finding.file_path}:{finding.line}</span></div><h4>{finding.title}</h4><p>{finding.message}</p><details><summary>{finding.source==="ai"?"AI explanation and suggested fix":"Explanation and suggested fix"}</summary><p>{finding.source==="ai"?"AI-generated explanation (verify independently): ":""}{finding.explanation}</p><pre>{finding.suggested_fix}</pre>{finding.source==="ai"&&<small className="ai-advisory-note">Suggestion only. Not applied automatically.</small>}</details></article>)}</div>}
      </section>:<><div className="workspace-live-summary"><strong>{filteredReviews.length}</strong><span>matching reviews · {reviews.length} total in your account</span><button className="primary-button" onClick={()=>setTab("scan")}><ScanLine size={14}/> Start a review</button></div>
      <div className="workspace-review-filters"><div><Filter size={15}/><strong>Filter review history</strong></div><label>Repository<select value={repositoryFilter} onChange={e=>setRepositoryFilter(e.target.value)}><option value="all">All repositories</option>{repositoryOptions.map(repo=><option key={repo} value={repo}>{repo}</option>)}</select></label><label>Severity<select value={severityFilter} onChange={e=>setSeverityFilter(e.target.value as SeverityFilter)}><option value="all">All severities</option><option value="critical">Critical</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label><button className="secondary-button" onClick={()=>{setRepositoryFilter("all");setSeverityFilter("all");}}>Reset filters</button></div>
      {reviews.length===0?<div className="workspace-live-empty"><Activity size={28}/><h3>No real reviews yet</h3><p>Your dashboard is ready. Submit a source file in Scan code to create the first persisted review; sample/demo findings are not counted as workspace activity.</p><button className="primary-button" onClick={()=>setTab("scan")}><ScanLine size={14}/> Scan your first file</button></div>:filteredReviews.length===0?<div className="workspace-live-empty"><Filter size={26}/><h3>No reviews match these filters</h3><p>Try another repository or severity. Severity filters match reviews that contain at least one finding at that severity.</p><button className="secondary-button" onClick={()=>{setRepositoryFilter("all");setSeverityFilter("all");}}>Clear filters</button></div>:<div className="workspace-live-review-list">{filteredReviews.map(r=><button type="button" key={r.review_id} className="workspace-review-row" onClick={()=>{setSelectedReview(null);void loadReview(r.review_id);}}><span><strong>{r.repository}</strong><small>{r.branch} · {new Date(r.created_at).toLocaleString()}</small><code>{r.review_id.slice(0,14)}</code></span><span className={`workspace-live-status status-${r.status}`}>{r.status}</span><span>Risk {r.risk_score}/100</span>{!terminal(r.status)&&<LoaderCircle size={15} className="auth-spinner"/>}<span className="workspace-open-review">Open details <ExternalLink size={12}/></span></button>)}</div>}</>}
    </>}
    {!loading&&tab==="scan"&&<form className="workspace-live-scan" onSubmit={startScan}><div><span className="section-kicker">DETERMINISTIC REVIEW</span><h2>Review selected source</h2><p>Confirm the selected source before queueing. The existing API queues real deterministic checks; a running Redis/Celery worker is required.</p></div><div className="workspace-live-scan-fields"><label>Repository label<input value={repository} onChange={e=>setRepository(e.target.value)} maxLength={200}/></label><label>Branch<input value={scanBranch} onChange={e=>setScanBranch(e.target.value)} maxLength={255}/></label><label>File path<input value={filePath} onChange={e=>setFilePath(e.target.value)} required/></label></div><label className="ai-review-toggle"><input type="checkbox" checked={aiReviewEnabled} onChange={e=>setAiReviewEnabled(e.target.checked)}/> Enable optional AI suggestions <small>Deterministic checks always run; AI may be unavailable.</small></label><label>Source code<textarea value={source} onChange={e=>setSource(e.target.value)} required maxLength={40000} rows={12} placeholder={"Load a GitHub file above, or paste a source file here.\ndef example():\n    return True"}/><small>{new TextEncoder().encode(source).length.toLocaleString()} / 40,000 bytes</small></label><button className="primary-button" type="submit" disabled={busy||!source.trim()}>{busy?<LoaderCircle size={15} className="auth-spinner"/>:<ScanLine size={15}/>} Queue review</button></form>}
  </section>;
}
