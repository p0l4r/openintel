import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, download } from "../api";
import KnowledgeGraph, { TYPE_COLORS } from "../components/KnowledgeGraph";

type Tab = "overview" | "graph" | "timeline" | "sources";

function Evidence({ items }: { items: any[] }) {
  return (
    <ul className="evidence">
      {items.map((e, i) => (
        <li key={i}>
          “{e.excerpt}” — <a href={e.url} target="_blank" rel="noreferrer noopener">{e.title || e.url}</a>
        </li>
      ))}
    </ul>
  );
}

const Badge = ({ s }: { s: string }) => <span className={`badge ${s}`}>{s}</span>;

export default function Entity({ signedIn }: { signedIn: boolean }) {
  const { id } = useParams();
  const nav = useNavigate();
  const [r, setR] = useState<any>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [sel, setSel] = useState<{ kind: "node" | "edge"; data: any } | null>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => { api(`/research/${id}/result`).then(setR).catch((e) => setMsg(e.message)); }, [id]);
  if (!r) return <p className="card narrow">{msg || "Loading…"}</p>;

  const exp = (kind: string) =>
    download(`/entities/${id}/export/${kind}`, kind).catch((e: ApiError) =>
      setMsg(e.status === 401 ? "Sign in to export." : String(e.detail)));
  const t = r.target_entity;
  const nodeEdges = (n: any) => r.graph.edges.filter((e: any) => e.source === n.id || e.target === n.id);
  const label = (nid: string) => r.graph.nodes.find((n: any) => n.id === nid)?.label ?? nid;

  const saveProfile = () =>
    api(`/research/${id}/save`, { method: "POST" }).then(() => setMsg("Saved to your account.")).catch((e) => setMsg(String(e?.detail || e?.message)));
  const refreshProfile = () =>
    api("/research", { method: "POST", body: JSON.stringify({ query: r.metadata?.original_query || t.name, refresh: true }) })
      .then((j) => nav(`/research/${j.job_id}`)).catch((e) => setMsg(e?.detail?.message || String(e?.detail || e?.message)));

  // clicking "Research this entity" in the graph starts a new search for that node
  async function researchEntity(name: string) {
    setMsg("");
    try {
      const j = await api("/research", { method: "POST", body: JSON.stringify({ query: name }) });
      nav(j.status === "completed" ? `/entities/${j.job_id}` : `/research/${j.job_id}`);
    } catch (e: any) {
      setMsg(e?.detail?.message || String(e?.detail || e?.message || "Could not start research"));
    }
  }

  const panel = sel && (
    <aside className="graphpanel">
      <button className="x" aria-label="Close" onClick={() => setSel(null)}>×</button>
      {sel.kind === "node" && (<>
        <h3>{sel.data.label}</h3>
        <p className="muted">
          <i className="dot" style={{ background: TYPE_COLORS[sel.data.type] || TYPE_COLORS.other }} />
          {sel.data.type} · {nodeEdges(sel.data).length} connections
        </p>
        {sel.data.id !== t.id && (
          <button onClick={() => researchEntity(sel.data.label)}>Research this entity</button>
        )}
        {nodeEdges(sel.data).map((e: any) => (
          <div key={e.id} className="fact">
            <b>{label(e.source)}</b> → {e.label} → <b>{label(e.target)}</b> <Badge s={e.status} />
            <Evidence items={e.evidence} />
          </div>
        ))}
      </>)}
      {sel.kind === "edge" && (<>
        <h3>{label(sel.data.source)} → {sel.data.label} → {label(sel.data.target)}</h3>
        <p className="muted">
          <Badge s={sel.data.status} /> confidence {Number(sel.data.confidence).toFixed(2)}
          {sel.data.date && ` · ${sel.data.date}`} · {sel.data.evidence.length} source(s)
        </p>
        <Evidence items={sel.data.evidence} />
      </>)}
    </aside>
  );

  return (
    <div>
      <div className="row between">
        <div>
          <h1>{t.name}</h1>
          <span className="muted">{t.type} · {r.sources.length} sources · {r.profile.key_facts.length} facts ·{" "}
            {r.graph.edges.length} connections</span>
        </div>
        <div className="row">
          <button onClick={() => exp("profile.pdf")}>Profile PDF</button>
          <button onClick={() => exp("graph.pdf")}>Graph PDF</button>
          {signedIn && <button onClick={refreshProfile} title="Search again and replace the saved profile">Refresh</button>}
          {signedIn && <button onClick={saveProfile} title="Keep this profile in your account">Save</button>}
        </div>
      </div>
      {!signedIn && (
        <p className="muted small">This profile is not saved. <Link to="/register">Create an account</Link> or <Link to="/login">sign in</Link> to keep it and reopen it without searching again.</p>
      )}
      {r.metadata?.corrected_query && (
        <p className="muted">Showing results for <b>{r.metadata.corrected_query}</b>{" "}
          (you searched “{r.metadata.original_query}”)</p>
      )}
      {msg && <p className="error">{msg}</p>}
      <div className="tabs">
        {(["overview", "graph", "timeline", "sources"] as Tab[]).map((x) => (
          <button key={x} className={tab === x ? "on" : ""} onClick={() => setTab(x)}>{x}</button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="card">
          <p>{r.profile.summary}</p>
          <h3>Key facts</h3>
          {r.profile.key_facts.length === 0 && <p className="muted">No supported facts found.</p>}
          {r.profile.key_facts.map((f: any, i: number) => (
            <div key={i} className="fact"><b>{f.text}</b> <Badge s={f.status} /><Evidence items={f.evidence} /></div>
          ))}
          <h3>Limitations</h3>
          <ul>{r.profile.limitations.map((l: string, i: number) => <li key={i}>{l}</li>)}</ul>
        </div>
      )}

      {tab === "graph" && (
        <KnowledgeGraph graph={r.graph} targetId={t.id}
          onNode={(d) => setSel({ kind: "node", data: d })}
          onEdge={(d) => setSel({ kind: "edge", data: d })}
          onClear={() => setSel(null)}>
          {panel}
        </KnowledgeGraph>
      )}

      {tab === "timeline" && (
        <div className="card">
          {r.timeline.length === 0 && <p className="muted">No dated events found.</p>}
          {r.timeline.map((e: any, i: number) => (
            <div key={i} className="fact"><b>{e.date}</b> — {e.summary} <Badge s={e.status} /><Evidence items={e.evidence} /></div>
          ))}
        </div>
      )}

      {tab === "sources" && (
        <div className="card">
          {r.sources.map((s: any) => (
            <p key={s.id}><a href={s.url} target="_blank" rel="noreferrer noopener">{s.title || s.url}</a>
              <span className="muted small"> · retrieved {s.retrieved_at.slice(0, 10)}</span></p>
          ))}
        </div>
      )}
    </div>
  );
}
