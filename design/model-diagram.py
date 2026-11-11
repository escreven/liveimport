#
# Reproduce the LiveImport state model diagram using gvdot 1.5 or later.
# Write demo files beside this script, preserving the original diagram.
#

from pathlib import Path
from gvdot import Dot, Port
from gvdot.markup import B, BR, Span, Table, TD, TR


def _lines(*lines:str, trailing:bool=True) -> Span:
    content = Span()
    for index, line in enumerate(lines):
        content.add(line)
        if trailing or index < len(lines)-1:
            content.add(BR(align="left"))
    return content


def _table(*cells:TD, color:str="#506985") -> Table:
    return Table(*(TR(cell) for cell in cells),
                 border=1, cellborder=0, cellspacing=0, cellpadding=9,
                 color=color)


def model_diagram() -> Dot:

    dot = Dot(directed=True,id="LiveImportState")

    dot.graph(rankdir="TB", bgcolor="white", pad=0.35, nodesep=0.65,
              ranksep=0.7, fontname="Helvetica", fontsize=20,
              outputorder="edgesfirst")

    dot.node_default(shape="plain", fontname="Helvetica", fontsize=12)

    dot.edge_default(fontname="Helvetica", fontsize=11, color="#41566e",
                     fontcolor="#334155", arrowsize=0.8)

    #
    # Define nodes in their rank groups before assigning labels.  Keep the
    # remaining node and the edges in later subgraphs so Graphviz encounters
    # the nodes in the order needed to reproduce the original layout.
    #

    (dot.subgraph().graph(rank="same")
     .node("module").node("ns"))

    (dot.subgraph().graph(rank="same")
     .node("journal").node("pyModule").node("namespace").node("watched"))

    dot.subgraph().node("record")

    dot.node("module",label=_table(
        TD(B("_ModuleInfo"),bgcolor="#e5edf7"),
        TD(_lines(
            "module: ModuleType",
            "file: str | None",
            "parent: str",
            "mtime: float",
            "attachedto: set[int]",
            "dependencies: list[str]",
            "next_mtime: float",
            "mark: int"),align="left")))

    dot.node("ns",label=_table(
        TD(B("_NamespaceInfo"),bgcolor="#e5edf7"),
        TD(_lines(
            "namespace: dict[str, Any]",
            "journal: _ImportJournal"),align="left")))

    dot.node("journal",label=_table(
        TD(B("_ImportJournal"),bgcolor="#e5edf7"),
        TD("sequence: list[_ImportRecord]",align="left")))

    dot.node("record",label=_table(
        TD(B("_ImportRecord")," · abstract",bgcolor="#e5edf7"),
        TD("modulename: str",align="left"),
        TD(B("Concrete types · additional instance fields"),
           bgcolor="#f1f5f9", align="left"),
        TD(_lines(
            "_ImportNameRecord",
            "    topname: str",
            "",
            "_ImportNameAsRecord",
            "    asname: str",
            "",
            "_ImportFromNamesRecord",
            "    namepairs: list[tuple[str, str]]",
            "",
            "_ImportFromStarRecord",
            "    no additional fields"),align="left"),
        TD(_lines(
            "All four inherit modulename.",
            "namepairs contains (name, asname) pairs.",
            trailing=False),bgcolor="#f8fafc",align="left")))

    for nodeid, title, typename in (
        ("pyModule", "Python module object", "ModuleType"),
        ("namespace", "Target namespace", "dict[str, Any]"),
        ("watched", "_REIFY_WATCH entry", "str"),
    ):
        dot.node(nodeid,label=_table(
            TD(B(title),bgcolor="#f1f5f9"),
            TD(typename),color="#94a3b8"))

    #
    # The invisible edge places the watch entry before the module object.
    #

    edges = dot.subgraph()

    edges.edge("watched","pyModule",style="invis")

    edges.edge("module","ns",style="dashed",
             label="attachedto · 0..* namespace IDs\n"
                   "via _NAMESPACE_TABLE[id(namespace)]")

    edges.edge(Port("module",cp="w"),Port("module",cp="nw"),style="dashed",
             label="dependencies · 0..* names\n"
                   "via _MODULE_TABLE.get(name)\n"
                   "only tracked names resolve")

    edges.edge("module","pyModule",label="module · 1 object")

    edges.edge("ns","namespace",label="namespace · 1 dictionary")

    edges.edge("ns","journal",dir="both",arrowtail="diamond",
             label="journal · 1 owned object")

    edges.edge("journal","record",dir="both",arrowtail="diamond",
             label="sequence · 0..* owned records\n"
                   "references in registration order")

    edges.edge("record","pyModule",style="dashed",constraint=False,
             label="modulename · 1 name\nvia sys.modules[name]")

    edges.edge("module","watched",style="dashed",
             label="dependencies · *..* lazily\nimported modules names")

    return dot


if __name__ == "__main__":
    directory = Path(__file__).resolve().parent
    dot = model_diagram()
    dot.save(directory / "model-diagram.svg")
