"""Agent 3 - Synthesize: profile, timeline, graph. Graph is built deterministically from validated
claims so no edge can exist without evidence; the LLM only writes the summary and entity typing."""
import re
from collections import defaultdict
from datetime import datetime, timezone

from ..llm import generate_json

SYSTEM = """You write a short neutral profile of a TARGET entity using ONLY the numbered claims given.
Return JSON: {"summary": str (max 120 words, no facts outside the claims),
"entity_type":"person|organization|place|other","limitations":[str]}.
Mention uncertainty where claims are inferred or sparse."""

MAX_NODES, MAX_EDGES = 50, 100
ENTITY_TYPES = ("person", "organization", "place", "event", "work")


def _id(name: str) -> str:
    return re.sub(r"\W+", "_", name.lower()).strip("_")


async def run(job_id: str, target: str, claims: list[dict], sources: list[dict]) -> dict:
    src_index = {s["id"]: s for s in sources}
    listing = "\n".join(f"{i}. {c['subject']} | {c['predicate']} | {c['object']} (conf {c['confidence']:.2f})"
                        for i, c in enumerate(claims[:80]))
    try:
        meta = await generate_json(SYSTEM, f"TARGET: {target}\nCLAIMS:\n{listing or '(none)'}")
    except Exception:
        meta = {}
    summary = meta.get("summary") if claims else "No evidence-backed information was found."
    target_id = _id(target)

    nodes: dict[str, dict] = {target_id: {"id": target_id, "label": target,
                                          "type": meta.get("entity_type", "other")}}
    edges, facts, timeline = [], [], []
    used_sources: set[str] = set()
    for i, c in enumerate(claims):
        ev = [{**e, "url": src_index[e["source_id"]]["url"],
               "title": src_index[e["source_id"]]["title"]}
              for e in c["evidence"] if e["source_id"] in src_index]
        if not ev:
            continue
        used_sources.update(e["source_id"] for e in ev)
        status = "supported" if c["explicit"] and (len(ev) > 1 or c["confidence"] >= 0.8) else "candidate"
        sid, oid = _id(c["subject"]), _id(c["object"])
        entity_obj = c["object_type"] in ENTITY_TYPES
        if entity_obj and len(nodes) < MAX_NODES and len(edges) < MAX_EDGES:
            for nid, label, t in ((sid, c["subject"], c.get("subject_type", "other")),
                                  (oid, c["object"], c["object_type"])):
                t = t if t in ENTITY_TYPES else "other"
                node = nodes.setdefault(nid, {"id": nid, "label": label, "type": t})
                if node["type"] == "other" and t != "other":  # upgrade to a more specific type
                    node["type"] = t
            edges.append({"id": f"e{i}", "source": sid, "target": oid,
                          "label": c["predicate"].replace("_", " "), "status": status,
                          "confidence": c["confidence"], "date": c["date"], "evidence": ev})
        if sid == target_id or _id(c["object"]) == target_id:
            facts.append({"text": f"{c['predicate'].replace('_', ' ')}: {c['object']}",
                          "status": status, "confidence": c["confidence"], "evidence": ev})
        if c["date"]:
            timeline.append({"date": c["date"], "summary": f"{c['subject']} {c['predicate'].replace('_', ' ')} {c['object']}",
                             "status": status, "evidence": ev})
    timeline.sort(key=lambda t: t["date"])

    # surface contradictions: same subject+predicate with different objects
    seen = defaultdict(set)
    for c in claims:
        seen[(_id(c["subject"]), c["predicate"])].add(c["object"])
    conflicts = [f"Conflicting values for '{p.replace('_', ' ')}' of {s}: {sorted(v)}"
                 for (s, p), v in seen.items() if len(v) > 1 and p in
                 ("founded_on", "headquartered_in", "ceo_is", "founded_by")]
    limitations = list(meta.get("limitations", [])) + conflicts
    limitations.append("Generated automatically from public web sources; verify before relying on it.")

    return {
        "research_job_id": job_id,
        "target_entity": {"id": job_id, "name": target, "type": nodes[target_id]["type"]},
        "profile": {"summary": summary, "key_facts": facts, "limitations": limitations},
        "timeline": timeline,
        "graph": {"nodes": list(nodes.values()), "edges": edges},
        "sources": [{k: v for k, v in src_index[s].items() if k != "text"} for s in sorted(used_sources)],
        "metadata": {"generated_at": datetime.now(timezone.utc).isoformat(),
                     "research_status": "completed", "claims": len(claims)},
    }
