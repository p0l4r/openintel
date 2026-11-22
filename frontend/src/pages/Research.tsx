import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";

const STEPS = [
  ["discover", "Searching public sources"],
  ["extract", "Extracting evidence"],
  ["synthesize", "Building profile and graph"],
];

export default function Research() {
  const { jobId } = useParams();
  const [job, setJob] = useState<any>(null);
  const nav = useNavigate();

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const j = await api(`/research/${jobId}`);
        if (stop) return;
        setJob(j);
        if (j.status === "completed") return nav(`/entities/${jobId}`, { replace: true });
        if (j.status !== "failed") setTimeout(tick, 2000);
      } catch { if (!stop) setTimeout(tick, 4000); }
    };
    tick();
    return () => { stop = true; };
  }, [jobId]);

  const idx = job ? STEPS.findIndex(([k]) => k === job.stage) : -1;
  return (
    <div className="card narrow">
      <h2>Researching “{job?.query}”</h2>
      <ol className="steps">
        {STEPS.map(([k, label], i) => (
          <li key={k} className={job?.status === "failed" ? "" : i < idx ? "done" : i === idx ? "active" : ""}>
            {label}
          </li>
        ))}
      </ol>
      {job?.status === "failed" && (
        <p className="error">Research failed: {job.error} <Link to="/">Try again</Link></p>
      )}
    </div>
  );
}
