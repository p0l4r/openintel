import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, setToken } from "../api";

function AuthForm({ mode, onAuth }: { mode: "login" | "register"; onAuth: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const nav = useNavigate();

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      const r = await api(`/auth/${mode}`, { method: "POST", body: JSON.stringify({ email, password }) });
      setToken(r.token);
      onAuth();
      nav("/");
    } catch (e: any) {
      setErr(typeof e.detail === "string" ? e.detail : "Check your email and password (min 8 chars).");
    }
  }

  return (
    <form className="card narrow" onSubmit={submit}>
      <h2>{mode === "login" ? "Sign in" : "Create account"}</h2>
      <input type="email" required placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input type="password" required minLength={8} placeholder="Password" value={password}
             onChange={(e) => setPassword(e.target.value)} />
      <button>{mode === "login" ? "Sign in" : "Register"}</button>
      {err && <p className="error">{err}</p>}
      <p className="muted small">
        {mode === "login" ? <Link to="/register">Need an account?</Link> : <Link to="/login">Already registered?</Link>}
      </p>
    </form>
  );
}

export const Login = (p: { onAuth: () => void }) => <AuthForm mode="login" {...p} />;
export const Register = (p: { onAuth: () => void }) => <AuthForm mode="register" {...p} />;
