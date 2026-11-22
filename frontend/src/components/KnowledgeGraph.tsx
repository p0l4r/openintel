import { ReactNode, useEffect, useRef } from "react";
import cytoscape from "cytoscape";

export const TYPE_COLORS: Record<string, string> = {
  person: "#f59e0b",
  organization: "#3b82f6",
  place: "#10b981",
  event: "#a855f7",
  work: "#ec4899",
  other: "#94a3b8",
};

type Props = {
  graph: { nodes: any[]; edges: any[] };
  targetId: string;
  onNode: (n: any) => void;
  onEdge: (e: any) => void;
  onClear: () => void;
  children?: ReactNode; // details panel, drawn over the graph
};

const evCount = (e: any) => Math.min((e.data("evidence") || []).length || 1, 4);

// Force layout whose spacing varies per edge: hubs push their neighbours further away,
// uncorroborated links are longer, well-evidenced links are shorter.
const layoutOptions = (randomize: boolean) =>
  ({
    name: "cose", animate: true, animationDuration: 900, randomize, fit: true, padding: 60,
    nodeRepulsion: () => 70000, nodeOverlap: 70, componentSpacing: 160, gravity: 0.12, numIter: 2500,
    idealEdgeLength: (e: any) => {
      const hub = Math.max(e.source().degree(), e.target().degree());
      return 130 + Math.min(hub, 12) * 16 + (e.data("status") === "candidate" ? 60 : 0) - evCount(e) * 10;
    },
    edgeElasticity: () => 90,
  }) as any;

export default function KnowledgeGraph({ graph, targetId, onNode, onEdge, onClear, children }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const cb = useRef({ onNode, onEdge, onClear });
  cb.current = { onNode, onEdge, onClear };

  const present = Array.from(new Set(graph.nodes.map((n) => (TYPE_COLORS[n.type] ? n.type : "other"))));
  // the canvas grows with the graph so nodes get room instead of being squeezed together
  const height = Math.min(1200, Math.max(720, 440 + graph.nodes.length * 14));
  const manyEdges = graph.edges.length > 30;

  useEffect(() => {
    if (!box.current) return;
    const color = (ele: any) => TYPE_COLORS[ele.data("type")] || TYPE_COLORS.other;
    const size = (ele: any) => 26 + Math.min(ele.degree() * 5, 36);
    const cy = cytoscape({
      container: box.current,
      elements: [
        ...graph.nodes.map((n) => ({ data: { ...n } })),
        ...graph.edges.map((e) => ({ data: { ...e } })),
      ],
      wheelSensitivity: 0.25, minZoom: 0.2, maxZoom: 3,
      layout: layoutOptions(true),
      style: [
        { selector: "node", style: {
            label: "data(label)", "font-size": 11, "font-weight": 600, color: "#1e293b",
            "text-wrap": "wrap", "text-max-width": "110px", "text-valign": "bottom", "text-margin-y": 7,
            "text-outline-color": "#ffffff", "text-outline-width": 3,
            "background-color": color, "border-width": 3, "border-color": "#ffffff",
            width: size, height: size,
        } as any },
        { selector: `node[id = "${targetId}"]`, style: { width: 66, height: 66, "font-size": 14,
            "border-color": "#0f172a", "border-width": 4 } },
        { selector: "edge", style: {
            // thickness = how much evidence backs the link (1 to 4 sources)
            width: (e: any) => 1.8 + evCount(e) * 0.9,
            "line-color": "#cbd5e1", "target-arrow-color": "#94a3b8", "target-arrow-shape": "triangle",
            "arrow-scale": 0.9, "curve-style": "bezier", "control-point-step-size": 50,
            // with many edges, names appear only on hover or selection to keep the picture calm
            label: manyEdges ? "" : "data(label)",
            "font-size": 9, color: "#475569", "text-rotation": "autorotate", "text-margin-y": -9,
            "text-wrap": "wrap", "text-max-width": "90px", "text-background-color": "#ffffff",
            "text-background-opacity": 0.85, "text-background-padding": "2px", "min-zoomed-font-size": 7,
        } as any },
        { selector: 'edge[status = "candidate"]', style: { "line-style": "dashed", "line-color": "#fcd34d",
            "target-arrow-color": "#f59e0b" } },
        { selector: ".faded", style: { opacity: 0.12 } },
        { selector: ".hl", style: { "line-color": "#475569", "target-arrow-color": "#475569", color: "#0f172a",
            label: "data(label)", "z-index": 10 } as any },
        { selector: "edge:selected", style: { "line-color": "#0f172a", "target-arrow-color": "#0f172a",
            label: "data(label)" } as any },
        { selector: "node:selected", style: { "border-color": "#0f172a", "border-width": 5 } },
      ],
    });
    cyRef.current = cy;

    const pointer = (on: boolean) => { if (box.current) box.current.style.cursor = on ? "pointer" : "default"; };
    cy.on("mouseover", "node", (ev) => {
      pointer(true);
      const hood = ev.target.closedNeighborhood();
      cy.elements().not(hood).addClass("faded");
      hood.edges().addClass("hl");
    });
    cy.on("mouseout", "node", () => { pointer(false); cy.elements().removeClass("faded hl"); });
    cy.on("mouseover", "edge", (ev) => { pointer(true); ev.target.addClass("hl"); });
    cy.on("mouseout", "edge", (ev) => { pointer(false); ev.target.removeClass("hl"); });
    cy.on("tap", "node", (ev) => cb.current.onNode(ev.target.data()));
    cy.on("tap", "edge", (ev) => cb.current.onEdge(ev.target.data()));
    cy.on("tap", (ev) => { if (ev.target === cy) cb.current.onClear(); });
    return () => { cy.destroy(); cyRef.current = null; };
  }, [graph, targetId]);

  useEffect(() => {
    const refit = () => setTimeout(() => { cyRef.current?.resize(); cyRef.current?.fit(undefined, 60); }, 150);
    document.addEventListener("fullscreenchange", refit);
    return () => document.removeEventListener("fullscreenchange", refit);
  }, []);

  const fullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else wrap.current?.requestFullscreen?.();
  };

  return (
    <div className="graphwrap" ref={wrap}>
      <div ref={box} className="graph" style={{ height }} />
      <div className="legend">
        {present.map((t) => (
          <span key={t}><i style={{ background: TYPE_COLORS[t] }} />{t}</span>
        ))}
        <span><i className="dash" />candidate link</span>
        <span>thicker line = more sources</span>
      </div>
      <div className="gtools">
        <button onClick={() => cyRef.current?.fit(undefined, 60)}>Fit</button>
        <button onClick={() => cyRef.current?.layout(layoutOptions(true)).run()}>Re-arrange</button>
        <button onClick={fullscreen}>Full screen</button>
      </div>
      <div className="ghint">Click a node or a line · drag to move · scroll to zoom</div>
      {children}
    </div>
  );
}
