import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";

export default function Home({ onSearch, signedIn }: { onSearch: () => void; signedIn: boolean }) {
  const [q, setQ] = useState("");
  const [err, setErr] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (q.trim().length < 2) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await api("/research", { method: "POST", body: JSON.stringify({ query: q }) });
      onSearch();
      nav(r.status === "completed" ? `/entities/${r.job_id}` : `/research/${r.job_id}`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : { message: "Something went wrong" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="hero">
      <h1>Discover the connections.</h1>
      <p className="muted">Turn public information into a source-backed profile and relationship graph.</p>
      <form onSubmit={submit} className="searchbar">
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)}
               placeholder="Search a company, organization or public figure…" />
        <button disabled={busy}>{busy ? "Starting…" : "Research"}</button>
      </form>
      {err && (
        <p className="error">
          {err.message || String(err)}{" "}
          {err.code === "quota_exceeded" && <Link to="/account">Sign in for a higher limit</Link>}
        </p>
      )}
      <p className="muted small">Public sources only · every claim links to its evidence</p>
      {!signedIn && (
        <p className="muted small"><Link to="/register">Create a free account</Link> to save your profiles and reopen them instantly instead of searching again.</p>
      )}
    </div>
  );
}
