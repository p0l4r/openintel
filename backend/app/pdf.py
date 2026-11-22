"""PDF exports from the saved result (no re-research)."""
import io
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402
from xml.sax.saxutils import escape  # noqa: E402

ss = getSampleStyleSheet()
NOTICE = "Automatically generated from public sources at the time of research. Verify before relying on it."


def _footer(canvas, doc):
    canvas.setFont("Helvetica", 8)
    canvas.drawString(15 * mm, 10 * mm, NOTICE[:95])
    canvas.drawRightString(195 * mm, 10 * mm, f"Page {doc.page}")


def _table(rows, widths):
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                           ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    return t


def _p(text, style="BodyText"):
    return Paragraph(escape(str(text)), ss[style])


def _cell(text):
    return Paragraph(escape(str(text)), ss["BodyText"])


def _src_links(ev):
    return ", ".join(sorted({e["url"] for e in ev}))


def profile_pdf(r: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, bottomMargin=20 * mm)
    t = r["target_entity"]
    s = [_p(t["name"], "Title"), _p(f"{t['type']} · generated {r['metadata']['generated_at'][:10]}", "Italic"),
         Spacer(1, 8), _p("Overview", "Heading2"), _p(r["profile"]["summary"])]
    s += [Spacer(1, 8), _p("Key facts", "Heading2")]
    rows = [["Fact", "Status", "Conf.", "Sources"]] + [
        [_cell(f["text"]), f["status"], f"{f['confidence']:.2f}", _cell(_src_links(f["evidence"]))]
        for f in r["profile"]["key_facts"]]
    s.append(_table(rows, [60 * mm, 22 * mm, 14 * mm, 84 * mm]))
    s += [Spacer(1, 8), _p("Timeline", "Heading2")]
    rows = [["Date", "Event", "Sources"]] + [[x["date"], _cell(x["summary"]), _cell(_src_links(x["evidence"]))]
                                            for x in r["timeline"]]
    s.append(_table(rows, [22 * mm, 78 * mm, 80 * mm]))
    s += [Spacer(1, 8), _p("Related entities", "Heading2")]
    rows = [["Entity", "Type"]] + [[n["label"], n["type"]] for n in r["graph"]["nodes"] if n["id"] != t["id"]]
    s.append(_table(rows, [120 * mm, 60 * mm]))
    s += [Spacer(1, 8), _p("Limitations", "Heading2")] + [_p("• " + x) for x in r["profile"]["limitations"]]
    s += [Spacer(1, 8), _p("Sources", "Heading2")] + [_p(f"[{x['id']}] {x['title']} - {x['url']}") for x in r["sources"]]
    doc.build(s, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def _graph_png(r: dict) -> bytes:
    g = nx.DiGraph()
    for n in r["graph"]["nodes"]:
        g.add_node(n["id"], label=n["label"])
    for e in r["graph"]["edges"]:
        g.add_edge(e["source"], e["target"], label=e["label"], status=e["status"])
    fig, ax = plt.subplots(figsize=(9, 7))
    pos = nx.spring_layout(g, seed=1, k=1.2 / math.sqrt(max(len(g), 1)))
    tid = r["target_entity"]["id"]
    nx.draw_networkx_nodes(g, pos, ax=ax, node_size=700,
                           node_color=["#2563eb" if n == tid else "#94a3b8" for n in g])
    nx.draw_networkx_labels(g, pos, {n: d["label"][:22] for n, d in g.nodes(data=True)}, font_size=7, ax=ax)
    style = ["solid" if d["status"] == "supported" else "dashed" for *_, d in g.edges(data=True)]
    nx.draw_networkx_edges(g, pos, ax=ax, style=style, arrows=True, edge_color="#475569")
    nx.draw_networkx_edge_labels(g, pos, {(a, b): d["label"][:18] for a, b, d in g.edges(data=True)},
                                 font_size=6, ax=ax)
    ax.axis("off")
    out = io.BytesIO()
    fig.savefig(out, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out.getvalue()


def graph_pdf(r: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, bottomMargin=20 * mm)
    labels = {n["id"]: n["label"] for n in r["graph"]["nodes"]}
    s = [_p(f"Knowledge graph: {r['target_entity']['name']}", "Title"),
         _p("Blue = target · dashed edges = candidate (not corroborated)", "Italic"),
         Image(io.BytesIO(_graph_png(r)), width=180 * mm, height=140 * mm), Spacer(1, 8),
         _p("Relationships and evidence", "Heading2")]
    rows = [["From", "Relation", "To", "Status", "Evidence"]] + [
        [_cell(labels[e["source"]]), _cell(e["label"]), _cell(labels[e["target"]]), e["status"],
         _cell("; ".join(f"\"{x['excerpt'][:140]}\" ({x['url']})" for x in e["evidence"]))]
        for e in r["graph"]["edges"]]
    s.append(_table(rows, [28 * mm, 24 * mm, 28 * mm, 18 * mm, 82 * mm]))
    doc.build(s, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
