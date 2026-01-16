# app/viz.py
from typing import Dict, List, Tuple
from pyvis.network import Network


def build_pyvis_html(
    nodes: List[str],
    edges: List[Tuple[str, str, int]],
    node_attrs: Dict[str, Dict[str, str]],
    height_px: int = 650,
) -> str:
    net = Network(height=f"{height_px}px", width="100%", directed=False, notebook=False)
    net.barnes_hut(gravity=-8000, central_gravity=0.3, spring_length=120, spring_strength=0.02, damping=0.09)

    # degree for size
    deg = {n: 0 for n in nodes}
    for a, b, _ in edges:
        if a in deg:
            deg[a] += 1
        if b in deg:
            deg[b] += 1

    for n in nodes:
        name = node_attrs.get(n, {}).get("preferred_name", n)
        size = 10 + min(30, deg.get(n, 0))
        title = f"{name}<br>{n}<br>degree={deg.get(n, 0)}"
        net.add_node(n, label=name, title=title, size=size)

    for a, b, sc in edges:
        # score_int: 0..1000
        width = 1 + (sc / 200.0)  # 0..1000 -> 1..6
        title = f"score={sc/1000:.3f} ({sc})"
        net.add_edge(a, b, value=sc, title=title, width=width)

    # UX tweaks
    net.set_options(
        """
        var options = {
          "interaction": {"hover": true, "multiselect": true},
          "physics": {"enabled": true},
          "nodes": {"font": {"size": 16}},
          "edges": {"smooth": {"type": "dynamic"}}
        }
        """
    )

    return net.generate_html()
