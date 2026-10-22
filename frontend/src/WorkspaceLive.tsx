import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Activity, CircleAlert, ExternalLink, FolderGit2, GitBranch, LoaderCircle, Plus, RefreshCw, ScanLine, Trash2, Github, FileCode2, ShieldCheck, Unplug } from "lucide-react";
import { readAuthToken } from "./AuthPage";

type Repo = { id:string; name:string; url:string; default_branch:string; created_at:string };
type GithubRepo = { id:number; full_name:string; private:boolean; html_url:string; default_branch:string; description?:string|null };
type Branch = { name:string; commit_sha:string };
type SourceFile = { path:string; size:number };
type Review = { review_id:string; repository:string; branch:string; status:string; risk_score:number; created_at:string; failure_reason?:string|null };
type Tab = "projects" | "reviews" | "scan";

async function api<T>(path:string, init:RequestInit = {}):Promise<T>{
  const token=readAuthToken();
  if(!token) throw new Error("Your session has expired. Please sign in again.");
  const response=await fetch(path,{...init,headers:{"Content-Type":"application/json",Authorization:`Bearer ${token}`,...(init.headers||{})}});
  if(!response.ok){
    const body=await response.json().catch(()=>({}));
    throw new Error(typeof body.detail==="string"?body.detail:`Request failed (${response.status})`);
  }
  if(response.status===204) return undefined as T;
  return response.json() as Promise<T>;
}
const message=(error:unknown,fallback:string)=>error instanceof Error?error.message:fallback;
const encoded=(value:string)=>encodeURIComponent(value);

export default function WorkspaceView({userName}:{userName:string}){
  const [tab,setTab]=useState<Tab>("projects");
  const [repos,setRepos]=useState<Repo[]>([]);
  const [reviews,setReviews]=useState<Review[]>([]);
  const [name,setName]=useState("");
  const [url,setUrl]=useState("");
  const [manualBranch,setManualBranch]=useState("main");
  const [filePath,setFilePath]=useState("snippet.py");
  const [source,setSource]=useState("");
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

  const refresh=useCallback(async()=>{
    setLoading(true);setError("");
    try{
      const [r,v]=await Promise.all([api<Repo[]>("/api/v1/workspace/repositories"),api<Review[]>("/api/v1/workspace/reviews")]);
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
  useEffect(()=>{void refresh();void refreshGithubStatus();},[refresh,refreshGithubStatus]);
  useEffect(()=>{
    const query=new URLSearchParams(window.location.search);
    if(query.get("github")==="connected"){setNotice("GitHub account connected securely.");setTab("projects");void refreshGithubStatus();}
    if(query.get("github")==="error")setError("GitHub authorization did not complete. Try connecting again.");
    if(query.has("github")){query.delete("github");const suffix=query.toString();window.history.replaceState({}, "", window.location.pathname+(suffix?"?"+suffix:"")+window.location.hash);}
  },[refreshGithubStatus]);

  async function connectGithub(){
    setError("");setNotice("");
    try{
      const token=readAuthToken();
      if(!token)throw new Error("Sign in to CodeGuard before connecting GitHub.");
      const response=await fetch("/api/v1/github/oauth/start",{headers:{Authorization:`Bearer ${token}`}});
      if(!response.ok){const body=await response.json().catch(()=>({}));throw new Error(body.detail||"Could not start GitHub authorization.");}
      const result=await response.json() as {authorization_url:string};
      if(!result.authorization_url||!result.authorization_url.startsWith("https://github.com/login/oauth/authorize?"))throw new Error("GitHub returned an invalid authorization URL.");
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
      const result=await api<{review_id:string;status:string}>("/api/v1/reviews",{method:"POST",body:JSON.stringify({source_code:source,file_path:filePath,repository:repository.trim()||"local",branch:scanBranch.trim()||"local"})});
      setNotice(`Review ${result.review_id} was ${result.status}. Refresh review history to track its status.`);setTab("reviews");await refresh();
    }catch(e){setError(message(e,"Could not start the review. Confirm the API and queue are running."));}
    finally{setBusy(false);}
  }

  return <section className="workspace-live">
    <div className="workspace-live-heading"><div><span className="section-kicker">PERSONAL WORKSPACE</span><h1>Welcome, {userName}</h1><p>Connect GitHub to browse authorized repositories, select a branch and source file, then queue a real review.</p></div><button className="secondary-button" onClick={()=>void refresh()} disabled={loading}><RefreshCw size={14}/> Refresh</button></div>
    <div className="workspace-live-tabs"><button className={tab==="projects"?"selected":""} onClick={()=>{setTab("projects");setError("");}}><FolderGit2 size={15}/> Projects</button><button className={tab==="reviews"?"selected":""} onClick={()=>{setTab("reviews");setError("");}}><Activity size={15}/> Review history</button><button className={tab==="scan"?"selected":""} onClick={()=>{setTab("scan");setError("");}}><ScanLine size={15}/> Scan code</button></div>
    {error&&<div className="workspace-live-error" role="alert"><CircleAlert size={16}/>{error}</div>}
    {notice&&<div className="workspace-live-notice" role="status">{notice}</div>}
    {loading?<div className="workspace-live-empty"><LoaderCircle className="auth-spinner" size={22}/> Loading your account data…</div>:null}
    {!loading&&tab==="projects"&&<>
      <section className="github-connect-panel">
        <div className="github-connect-header"><div className="github-connect-icon"><Github size={21}/></div><div><span className="section-kicker">GITHUB INTEGRATION</span><h2>Connect your repositories</h2><p>Authorize GitHub to see repositories you can access, including private repositories allowed by your GitHub permissions. Tokens stay on the server.</p></div></div>
        {githubConnected?<div className="github-connected-row"><span className="github-state"><ShieldCheck size={15}/> Connected as <strong>{githubLogin||"GitHub user"}</strong></span><button className="secondary-button" onClick={()=>void refreshGithubStatus()} disabled={githubBusy}><RefreshCw size={14}/> Refresh</button><button className="workspace-live-remove" onClick={()=>void disconnectGithub()} disabled={githubBusy}><Unplug size={14}/> Disconnect</button></div>:<button className="primary-button" onClick={()=>void connectGithub()}><Github size={15}/> Connect GitHub account</button>}
        {githubConnected&&<><div className="github-picker-grid"><label>Repository<select value={selectedRepo} onChange={e=>void selectGithubRepo(e.target.value)}><option value="">Select repository…</option>{githubRepos.map(repo=><option key={repo.id} value={repo.full_name}>{repo.full_name}{repo.private?" · private":""}</option>)}</select></label><label>Branch<select value={selectedBranch} onChange={e=>void selectBranch(e.target.value)} disabled={!selectedRepo||githubBusy}><option value="">Select branch…</option>{branches.map(item=><option key={item.name} value={item.name}>{item.name}</option>)}</select></label><label>Source file<select value={selectedFile} onChange={e=>void selectSourceFile(e.target.value)} disabled={!selectedBranch||githubBusy}><option value="">Select source file…</option>{files.map(file=><option key={file.path} value={file.path}>{file.path} ({file.size.toLocaleString()} B)</option>)}</select></label></div><div className="github-picker-footer"><span>{githubBusy?<><LoaderCircle className="auth-spinner" size={14}/> Loading GitHub data…</>:`${githubRepos.length} repositories available · ${files.length} supported source files for selected branch`}</span><span>Source file limit: 40 KB</span></div>{githubRepos.length===0&&!githubBusy&&<p className="github-empty">No accessible repositories were returned. Check the GitHub account and granted repository permissions.</p>}{selectedFile&&source&&<div className="github-source-loaded"><FileCode2 size={15}/><span>Loaded <strong>{selectedFile}</strong>. Review the source below before queueing.</span><button className="secondary-button" onClick={()=>setTab("scan")}>Continue to review <ScanLine size={14}/></button></div>}</>}
      </section>
      <form className="workspace-live-form" onSubmit={addRepo}><div className="workspace-live-form-title"><Plus size={17}/><strong>Save a repository shortcut</strong></div><label>Repository name (optional)<input value={name} onChange={e=>setName(e.target.value)} maxLength={120} placeholder="team/my-service"/></label><label>GitHub repository URL<input type="url" value={url} onChange={e=>setUrl(e.target.value)} required placeholder="https://github.com/owner/repository"/></label><label>Default branch<input value={manualBranch} onChange={e=>setManualBranch(e.target.value)} maxLength={100} required/></label><button className="primary-button" type="submit" disabled={busy}>{busy?<LoaderCircle size={15} className="auth-spinner"/>:<Plus size={15}/>} Save shortcut</button></form>
      {repos.length===0?<div className="workspace-live-empty"><FolderGit2 size={28}/><h3>No saved shortcuts</h3><p>Connect GitHub above to browse repositories, or save a URL shortcut to find it quickly later.</p></div>:<div className="workspace-live-grid">{repos.map(repo=><article className="workspace-live-card" key={repo.id}><FolderGit2 size={20}/><h3>{repo.name}</h3><a href={repo.url} target="_blank" rel="noreferrer">{repo.url.replace("https://github.com/","")} <ExternalLink size={12}/></a><span><GitBranch size={13}/>{repo.default_branch}</span><small>Saved {new Date(repo.created_at).toLocaleDateString()}</small><button className="workspace-live-remove" onClick={()=>void removeRepo(repo.id)}><Trash2 size={14}/> Remove</button></article>)}</div>}
    </>}
    {!loading&&tab==="reviews"&&<><div className="workspace-live-summary"><strong>{reviews.length}</strong><span>reviews belonging to your account</span><button className="primary-button" onClick={()=>setTab("scan")}><ScanLine size={14}/> Start a review</button></div>{reviews.length===0?<div className="workspace-live-empty"><Activity size={28}/><h3>No real reviews yet</h3><p>Submit a source file in Scan code. Demo findings are not included in this history.</p><button className="primary-button" onClick={()=>setTab("scan")}>Scan code</button></div>:<div className="workspace-live-review-list">{reviews.map(r=><article key={r.review_id}><div><strong>{r.repository}</strong><small>{r.branch} · {new Date(r.created_at).toLocaleString()}</small>{r.failure_reason&&<p>{r.failure_reason}</p>}</div><span className={`workspace-live-status status-${r.status}`}>{r.status}</span><span>Risk {r.risk_score}/100</span><code>{r.review_id.slice(0,12)}</code></article>)}</div>}</>}
    {!loading&&tab==="scan"&&<form className="workspace-live-scan" onSubmit={startScan}><div><span className="section-kicker">DETERMINISTIC REVIEW</span><h2>Review selected source</h2><p>Confirm the selected source before queueing. The existing API queues real deterministic checks; a running Redis/Celery worker is required.</p></div><div className="workspace-live-scan-fields"><label>Repository label<input value={repository} onChange={e=>setRepository(e.target.value)} maxLength={200}/></label><label>Branch<input value={scanBranch} onChange={e=>setScanBranch(e.target.value)} maxLength={255}/></label><label>File path<input value={filePath} onChange={e=>setFilePath(e.target.value)} required/></label></div><label>Source code<textarea value={source} onChange={e=>setSource(e.target.value)} required maxLength={40000} rows={12} placeholder={"Load a GitHub file above, or paste a source file here.\ndef example():\n    return True"}/><small>{new TextEncoder().encode(source).length.toLocaleString()} / 40,000 bytes</small></label><button className="primary-button" type="submit" disabled={busy||!source.trim()}>{busy?<LoaderCircle size={15} className="auth-spinner"/>:<ScanLine size={15}/>} Queue review</button></form>}
  </section>;
}
