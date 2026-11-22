import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

export default function Account() {
  const [usage, setUsage] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [keys, setKeys] = useState<any[]>([]);
  const [newKey, setNewKey] = useState("");
  const [msg, setMsg] = useState("");

  const load = () => {
    api("/usage").then(setUsage);
    api("/history").then(setHistory).catch(() => {});
    api("/api-keys").then(setKeys).catch(() => {});
  };
  useEffect(load, []);

  const createKey = () =>
    api("/api-keys", { method: "POST" }).then((r) => { setNewKey(r.key); load(); }).catch((e) => setMsg(String(e.detail)));
  const revoke = (id: string) => api(`/api-keys/${id}`, { method: "DELETE" }).then(load);

  if (!usage) return null;
  if (!usage.email)
    return <p className="card narrow"><Link to="/login">Sign in</Link> or <Link to="/register">register</Link> to manage your account.</p>;

  return (
    <div className="stack">
      <div className="card">
        <h2>{usage.email}</h2>
        <p>{usage.limit > 0
          ? `${usage.used} / ${usage.limit} searches in the last ${usage.window_days} days`
          : `${usage.used} searches in the last ${usage.window_days} days (no limit)`}</p>
        {msg && <p className="error">{msg}</p>}
      </div>
      <div className="card">
        <h2>API keys</h2>
        <p className="muted small">Use header <code>X-API-Key</code> with <code>/api/v1/…</code>.</p>
        <button onClick={createKey}>Create key</button>
        {newKey && <p>Copy now (shown once): <code>{newKey}</code></p>}
        {keys.map((k) => (
          <p key={k.id}><code>{k.prefix}…</code> <button onClick={() => revoke(k.id)}>Revoke</button></p>
        ))}
      </div>
      <div className="card">
        <h2>Saved profiles</h2>
        {history.map((h) => (
          <p key={h.job_id}>
            <Link to={h.status === "completed" ? `/entities/${h.job_id}` : `/research/${h.job_id}`}>{h.query}</Link>
            <span className="muted small"> · {h.status} · {String(h.created_at).slice(0, 10)}</span>
          </p>
        ))}
      </div>
    </div>
  );
}
