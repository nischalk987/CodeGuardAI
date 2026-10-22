import { useState, type FormEvent } from "react";
import { ShieldCheck, Eye, EyeOff, ArrowRight, LoaderCircle, CircleAlert } from "lucide-react";

type AuthUser = { id: string; email: string; display_name: string };
type AuthResponse = { access_token: string; token_type: string; expires_in: number; user: AuthUser };

export const AUTH_TOKEN_KEY = "codeguard:access-token";
export const AUTH_USER_KEY = "codeguard:auth-user";

export function readAuthToken(): string | null {
  try { return localStorage.getItem(AUTH_TOKEN_KEY); } catch { return null; }
}
export function clearAuth() {
  try { localStorage.removeItem(AUTH_TOKEN_KEY); localStorage.removeItem(AUTH_USER_KEY); } catch { /* storage may be disabled */ }
}

export default function AuthPage({ onAuthenticated }: { onAuthenticated: (user: AuthUser) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/v1/auth/${mode === "register" ? "register" : "login"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(mode === "register" ? { display_name: name.trim(), email: email.trim(), password } : { email: email.trim(), password }),
        signal: AbortSignal.timeout(12000),
      });
      const body = await response.json().catch(() => ({})) as AuthResponse & { detail?: string };
      if (!response.ok) throw new Error(body.detail || (response.status === 503 ? "Authentication is not configured on the server yet." : "Could not complete authentication."));
      localStorage.setItem(AUTH_TOKEN_KEY, body.access_token);
      localStorage.setItem(AUTH_USER_KEY, JSON.stringify(body.user));
      onAuthenticated(body.user);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error. Check that the API is running.");
    } finally { setBusy(false); }
  }

  return <main className="auth-screen">
    <section className="auth-brand-panel">
      <div className="auth-brand"><span className="auth-brand-mark"><ShieldCheck size={27}/></span><span>codeguard<span>AI</span><small>CODE INTELLIGENCE</small></span></div>
      <div className="auth-pitch"><span className="section-kicker">SECURE YOUR SHIPPING WORKFLOW</span><h1>Review code.<br/><em>Ship with confidence.</em></h1><p>Bring your code reviews, security findings, and engineering workflow into one workspace.</p><div className="auth-benefit"><ShieldCheck size={17}/> One account for your CodeGuardAI workspace</div></div>
      <span className="auth-footer-note">Your account is stored securely by the CodeGuardAI API.</span>
    </section>
    <section className="auth-form-panel">
      <div className="auth-form-wrap">
        <span className="section-kicker">{mode === "login" ? "WELCOME BACK" : "GET STARTED"}</span>
        <h2>{mode === "login" ? "Sign in to your account" : "Create your account"}</h2>
        <p className="auth-subtitle">{mode === "login" ? "Enter your credentials to continue to your workspace." : "Set up your personal CodeGuardAI workspace."}</p>
        <div className="auth-tabs"><button className={mode === "login" ? "selected" : ""} type="button" onClick={() => {setMode("login");setError("");}}>Sign in</button><button className={mode === "register" ? "selected" : ""} type="button" onClick={() => {setMode("register");setError("");}}>Sign up</button></div>
        <form onSubmit={submit} className="auth-form">
          {mode === "register" && <label>Full name<input value={name} onChange={e=>setName(e.target.value)} autoComplete="name" placeholder="Your name" minLength={1} maxLength={80} required/></label>}
          <label>Email address<input type="email" value={email} onChange={e=>setEmail(e.target.value)} autoComplete="email" placeholder="you@example.com" maxLength={254} required/></label>
          <label>Password<div className="auth-password"><input type={showPassword?"text":"password"} value={password} onChange={e=>setPassword(e.target.value)} autoComplete={mode==="register"?"new-password":"current-password"} minLength={mode==="register"?10:1} maxLength={128} placeholder={mode==="register"?"At least 10 characters":"Enter your password"} required/><button type="button" aria-label={showPassword?"Hide password":"Show password"} onClick={()=>setShowPassword(v=>!v)}>{showPassword?<EyeOff size={16}/>:<Eye size={16}/>}</button></div></label>
          {error && <div className="auth-error" role="alert"><CircleAlert size={16}/><span>{error}</span></div>}
          <button className="auth-submit" type="submit" disabled={busy}>{busy?<LoaderCircle className="auth-spinner" size={17}/>:<>{mode==="login"?"Sign in":"Create account"} <ArrowRight size={16}/></>}</button>
        </form>
        <p className="auth-switch">{mode==="login"?"New to CodeGuardAI?":"Already have an account?"} <button onClick={()=>{setMode(mode==="login"?"register":"login");setError("");}}>{mode==="login"?"Create an account":"Sign in"}</button></p>
        <p className="auth-security-note"><ShieldCheck size={14}/> Passwords are never stored in plain text.</p>
      </div>
    </section>
  </main>;
}
