import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Activity, CircleAlert, ExternalLink, FolderGit2, GitBranch, LoaderCircle, Plus, RefreshCw, ScanLine, Trash2 } from "lucide-react";
import { readAuthToken } from "./AuthPage";

type Repo = { id:string; name:string; url:string; default_branch:string; created_at:string };
type Review = { review_id:string; repository:string; branch:string; status:string; risk_score:number; created_at:string; failure_reason?:string|null };
type Tab = "projects" | "reviews" | "scan";

async function api<T>(path:string, init:RequestInit = {}):Promise<T>{
  const token=readAuthToken();
  if(!token) throw new Error("Your session has expired. Please sign in again.");
  const response=await fetch(path,{...init,headers:{"Content-Type":"application/json",Authorization:`Bearer ${token}`,...(init.headers||{})}});
  if(!response.ok){const body=await response.json().catch(()=>({}));throw new Error(body.detail||`Request failed (${response.status})`);}
  if(response.status===204) return undefined as T;
  return response.json() as Promise<T>;
}

export default function WorkspaceView({userName}:{userName:string}){
  const [tab,setTab]=useState<Tab>("projects");
  const [repos,setRepos]=useState<Repo[]>([]);
  const [reviews,setReviews]=useState<Review[]>([]);
  const [name,setName]=useState("");
  const [url,setUrl]=useState("");
  const [branch,setBranch]=useState("main");
  const [filePath,setFilePath]=useState("snippet.py");
  const [source,setSource]=useState("");
  const [repository,setRepository]=useState("local");
  const [scanBranch,setScanBranch]=useState("local");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [loading,setLoading]=useState(true);

  const refresh=useCallback(async()=>{
    setLoading(true);setError("");
    try{const [r,v]=await Promise.all([api<Repo[]>("/api/v1/workspace/repositories"),api<Review[]>("/api/v1/workspace/reviews")]);setRepos(r);setReviews(v);}
    catch(e){setError(e instanceof Error?e.message:"Unable to load your workspace.");}
    finally{setLoading(false);}
  },[]);
  useEffect(()=>{void refresh();},[refresh]);

  async function addRepo(e:FormEvent<HTMLFormElement>){
    e.preventDefault();setBusy(true);setError("");setNotice("");
    try{await api<Repo>("/api/v1/workspace/repositories",{method:"POST",body:JSON.stringify({name:name.trim()||undefined,url:url.trim(),default_branch:branch.trim()||"main"})});setName("");setUrl("");setBranch("main");setNotice("Repository saved to your account.");await refresh();}
    catch(err){setError(err instanceof Error?err.message:"Could not save repository.");}
    finally{setBusy(false);}
  }
  async function removeRepo(id:string){
    if(!window.confirm("Remove this repository from your workspace?"))return;
    setError("");setNotice("");
    try{await api<void>(`/api/v1/workspace/repositories/${encodeURIComponent(id)}`,{method:"DELETE"});setNotice("Repository removed.");await refresh();}
    catch(err){setError(err instanceof Error?err.message:"Could not remove repository.");}
  }
  async function startScan(e:FormEvent<HTMLFormElement>){
    e.preventDefault();setBusy(true);setError("");setNotice("");
    try{
      const result=await api<{review_id:string;status:string}>("/api/v1/reviews",{method:"POST",body:JSON.stringify({source_code:source,file_path:filePath,repository:repository.trim()||"local",branch:scanBranch.trim()||"local"})});
      setNotice(`Review ${result.review_id} was ${result.status}. Refresh review history to track its status.`);
      setSource("");setTab("reviews");await refresh();
    }catch(err){setError(err instanceof Error?err.message:"Could not start the review. Confirm the API and queue are running.");}
    finally{setBusy(false);}
  }

  return <section className="workspace-live">
    <div className="workspace-live-heading"><div><span className="section-kicker">PERSONAL WORKSPACE</span><h1>Welcome, {userName}</h1><p>Repositories and reviews are loaded from your account, not browser demo storage.</p></div><button className="secondary-button" onClick={()=>void refresh()} disabled={loading}><RefreshCw size={14}/> Refresh</button></div>
    <div className="workspace-live-tabs"><button className={tab==="projects"?"selected":""} onClick={()=>{setTab("projects");setError("");}}><FolderGit2 size={15}/> Projects</button><button className={tab==="reviews"?"selected":""} onClick={()=>{setTab("reviews");setError("");}}><Activity size={15}/> Review history</button><button className={tab==="scan"?"selected":""} onClick={()=>{setTab("scan");setError("");}}><ScanLine size={15}/> Scan code</button></div>
    {error&&<div className="workspace-live-error" role="alert"><CircleAlert size={16}/>{error}</div>}
    {notice&&<div className="workspace-live-notice" role="status">{notice}</div>}
    {loading?<div className="workspace-live-empty"><LoaderCircle className="auth-spinner" size={22}/> Loading your account data…</div>:null}
    {!loading&&tab==="projects"&&<>
      <form className="workspace-live-form" onSubmit={addRepo}><div className="workspace-live-form-title"><Plus size={17}/><strong>Add GitHub repository</strong></div><label>Repository name (optional)<input value={name} onChange={e=>setName(e.target.value)} maxLength={120} placeholder="team/my-service"/></label><label>GitHub repository URL<input type="url" value={url} onChange={e=>setUrl(e.target.value)} required placeholder="https://github.com/owner/repository"/></label><label>Default branch<input value={branch} onChange={e=>setBranch(e.target.value)} maxLength={100} required/></label><button className="primary-button" type="submit" disabled={busy}>{busy?<LoaderCircle size={15} className="auth-spinner"/>:<Plus size={15}/>} Save repository</button></form>
      {repos.length===0?<div className="workspace-live-empty"><FolderGit2 size={28}/><h3>Your workspace is empty</h3><p>Add a repository above. It will be saved to your account and remain available after you sign in again.</p></div>:<div className="workspace-live-grid">{repos.map(repo=><article className="workspace-live-card" key={repo.id}><FolderGit2 size={20}/><h3>{repo.name}</h3><a href={repo.url} target="_blank" rel="noreferrer">{repo.url.replace("https://github.com/","")} <ExternalLink size={12}/></a><span><GitBranch size={13}/>{repo.default_branch}</span><small>Saved {new Date(repo.created_at).toLocaleDateString()}</small><button className="workspace-live-remove" onClick={()=>void removeRepo(repo.id)}><Trash2 size={14}/> Remove</button></article>)}</div>}
    </>}
    {!loading&&tab==="reviews"&&<><div className="workspace-live-summary"><strong>{reviews.length}</strong><span>reviews belonging to your account</span><button className="primary-button" onClick={()=>setTab("scan")}><ScanLine size={14}/> Start a review</button></div>{reviews.length===0?<div className="workspace-live-empty"><Activity size={28}/><h3>No real reviews yet</h3><p>Submit a source file in Scan code. Demo findings are not included in this history.</p><button className="primary-button" onClick={()=>setTab("scan")}>Scan code</button></div>:<div className="workspace-live-review-list">{reviews.map(r=><article key={r.review_id}><div><strong>{r.repository}</strong><small>{r.branch} · {new Date(r.created_at).toLocaleString()}</small>{r.failure_reason&&<p>{r.failure_reason}</p>}</div><span className={`workspace-live-status status-${r.status}`}>{r.status}</span><span>Risk {r.risk_score}/100</span><code>{r.review_id.slice(0,12)}</code></article>)}</div>}</>}
    {!loading&&tab==="scan"&&<form className="workspace-live-scan" onSubmit={startScan}><div><span className="section-kicker">DETERMINISTIC REVIEW</span><h2>Scan a source file</h2><p>Paste up to 40 KB of supported source code. The API queues the real review; a running Redis/Celery worker is required to process it.</p></div><div className="workspace-live-scan-fields"><label>Repository label<input value={repository} onChange={e=>setRepository(e.target.value)} maxLength={200} placeholder="owner/repository or local"/></label><label>Branch<input value={scanBranch} onChange={e=>setScanBranch(e.target.value)} maxLength={255}/></label><label>File path<input value={filePath} onChange={e=>setFilePath(e.target.value)} required placeholder="src/main.py"/></label></div><label>Source code<textarea value={source} onChange={e=>setSource(e.target.value)} required maxLength={40000} rows={12} placeholder={"def example():\n    password = \"hardcoded-secret\"\n    print(password)"}/><small>{new TextEncoder().encode(source).length.toLocaleString()} / 40,000 bytes</small></label><button className="primary-button" type="submit" disabled={busy||!source.trim()}>{busy?<LoaderCircle size={15} className="auth-spinner"/>:<ScanLine size={15}/>} Queue real review</button></form>}
  </section>;
}
