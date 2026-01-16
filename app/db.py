# app/db.py
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass
class ResolvedItem:
    query: str
    status: str  # "resolved" | "ambiguous" | "unresolved"
    protein_id: Optional[str]
    preferred_name: Optional[str]
    source: Optional[str]
    candidates: Optional[str]  # semicolon separated


def _chunked(seq: Sequence[str], n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_preferred_name(conn: sqlite3.Connection, protein_id: str) -> Optional[str]:
    row = conn.execute(
        "SELECT preferred_name FROM proteins WHERE protein_id = ?",
        (protein_id,),
    ).fetchone()
    return row["preferred_name"] if row else None


def resolve_ids(
    conn: sqlite3.Connection,
    queries: List[str],
    taxon_id: Optional[str] = None,
) -> List[ResolvedItem]:
    """
    Resolve mixed identifiers to STRING protein_id.
    - If query matches proteins.protein_id directly => resolved.
    - Else search aliases(alias == query, NOCASE). If multiple => ambiguous.
    - If taxon_id is provided => filter candidates by taxon_id.
    """
    out: List[ResolvedItem] = []
    priority_sources = [
        "Ensembl", "Ensembl_HGNC", "Ensembl_EntrezGene", "HGNC", "UniProt", "Gene_Name", "BLAST_UniProt",
        "RefSeq", "EntrezGene", "BioMart_HUGO"
    ]

    for q in queries:
        q2 = q.strip()
        if not q2:
            continue

        # direct match
        row = conn.execute(
            "SELECT protein_id, preferred_name FROM proteins WHERE protein_id = ?",
            (q2,),
        ).fetchone()
        if row:
            out.append(ResolvedItem(q2, "resolved", row["protein_id"], row["preferred_name"], "direct", None))
            continue

        # alias match
        if taxon_id:
            rows = conn.execute(
                "SELECT a.protein_id, a.source, p.preferred_name "
                "FROM aliases a LEFT JOIN proteins p ON a.protein_id = p.protein_id "
                "WHERE a.alias = ? AND a.taxon_id = ? "
                "LIMIT 50",
                (q2, taxon_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT a.protein_id, a.source, p.preferred_name "
                "FROM aliases a LEFT JOIN proteins p ON a.protein_id = p.protein_id "
                "WHERE a.alias = ? "
                "LIMIT 50",
                (q2,),
            ).fetchall()

        if not rows:
            out.append(ResolvedItem(q2, "unresolved", None, None, None, None))
            continue

        if len(rows) == 1:
            r = rows[0]
            out.append(ResolvedItem(q2, "resolved", r["protein_id"], r["preferred_name"], r["source"], None))
            continue

        # choose best candidate deterministically by source priority, then stable sort
        def score_source(src: str) -> int:
            if src is None:
                return 10_000
            for i, s in enumerate(priority_sources):
                if src == s:
                    return i
            return 9_999

        sorted_rows = sorted(
            rows,
            key=lambda r: (score_source(r["source"]), r["protein_id"]),
        )
        best = sorted_rows[0]
        candidates = "; ".join([f'{r["protein_id"]}({r["source"]})' for r in sorted_rows[:10]])
        out.append(
            ResolvedItem(q2, "ambiguous", best["protein_id"], best["preferred_name"], best["source"], candidates)
        )

    return out


def fetch_edges_induced(
    conn: sqlite3.Connection,
    protein_ids: List[str],
    score_thr_int: int,
    table: str,
) -> List[Tuple[str, str, int]]:
    """
    Induced subgraph edges among protein_ids with score >= threshold.
    Uses canonical storage p1 < p2; we query both endpoints in set.
    """
    if not protein_ids:
        return []

    # SQLite has a bound variable limit (often 999). Chunk safely.
    edges: List[Tuple[str, str, int]] = []
    pid_set = set(protein_ids)
    # Strategy: query all edges where p1 in set AND p2 in set, using chunk on p1 and p2 is hard.
    # With max_nodes limited (e.g., 300), we can do a single IN list. Still chunk to be safe.
    for chunk in _chunked(list(pid_set), 900):
        qmarks = ",".join(["?"] * len(chunk))
        rows = conn.execute(
            f"SELECT p1, p2, score_int FROM {table} "
            f"WHERE score_int >= ? AND p1 IN ({qmarks})",
            (score_thr_int, *chunk),
        ).fetchall()
        # filter p2 in set in python (fast for <=300 nodes)
        for r in rows:
            if r["p2"] in pid_set:
                edges.append((r["p1"], r["p2"], int(r["score_int"])))
    return edges


def fetch_edges_adjacent(
    conn: sqlite3.Connection,
    seed_ids: List[str],
    score_thr_int: int,
    table: str,
) -> List[Tuple[str, str, int]]:
    """
    Fetch edges where either endpoint is in seed_ids (score >= thr).
    """
    if not seed_ids:
        return []

    edges: List[Tuple[str, str, int]] = []
    seed_set = set(seed_ids)

    # Query p1 in seed OR p2 in seed; since stored canonical p1<p2, both possible.
    # We'll do two queries and union in python.
    for chunk in _chunked(list(seed_set), 900):
        qmarks = ",".join(["?"] * len(chunk))

        rows1 = conn.execute(
            f"SELECT p1, p2, score_int FROM {table} "
            f"WHERE score_int >= ? AND p1 IN ({qmarks})",
            (score_thr_int, *chunk),
        ).fetchall()
        for r in rows1:
            edges.append((r["p1"], r["p2"], int(r["score_int"])))

        rows2 = conn.execute(
            f"SELECT p1, p2, score_int FROM {table} "
            f"WHERE score_int >= ? AND p2 IN ({qmarks})",
            (score_thr_int, *chunk),
        ).fetchall()
        for r in rows2:
            edges.append((r["p1"], r["p2"], int(r["score_int"])))

    # dedupe (p1,p2) because overlap can happen in chunking
    uniq: Dict[Tuple[str, str], int] = {}
    for p1, p2, sc in edges:
        key = (p1, p2)
        if key not in uniq or sc > uniq[key]:
            uniq[key] = sc
    return [(k[0], k[1], v) for k, v in uniq.items()]


def expand_1hop(
    conn: sqlite3.Connection,
    seed_ids: List[str],
    score_thr_int: int,
    table: str,
    max_nodes: int,
) -> Tuple[List[str], List[Tuple[str, str, int]]]:
    """
    1-hop expansion:
    - Get all edges adjacent to seeds
    - Rank neighbor nodes by sum(score) to seeds
    - Add top neighbors until max_nodes
    - Return induced edges in final node set
    """
    seed_set = set(seed_ids)
    if not seed_set:
        return [], []

    adj_edges = fetch_edges_adjacent(conn, list(seed_set), score_thr_int, table)

    # accumulate neighbor scores
    neighbor_score: Dict[str, int] = {}
    for p1, p2, sc in adj_edges:
        a_in = p1 in seed_set
        b_in = p2 in seed_set
        if a_in and not b_in:
            neighbor_score[p2] = neighbor_score.get(p2, 0) + sc
        elif b_in and not a_in:
            neighbor_score[p1] = neighbor_score.get(p1, 0) + sc

    # choose neighbors
    nodes = list(seed_set)
    if len(nodes) < max_nodes and neighbor_score:
        remain = max_nodes - len(nodes)
        top_neighbors = sorted(neighbor_score.items(), key=lambda x: (-x[1], x[0]))[:remain]
        nodes.extend([n for n, _ in top_neighbors])

    # induced edges among final nodes (fast because <= max_nodes)
    induced_edges = fetch_edges_induced(conn, nodes, score_thr_int, table)
    return nodes, induced_edges


def get_node_attributes(
    conn: sqlite3.Connection,
    protein_ids: List[str],
) -> Dict[str, Dict[str, str]]:
    if not protein_ids:
        return {}
    attrs: Dict[str, Dict[str, str]] = {}
    for chunk in _chunked(protein_ids, 900):
        qmarks = ",".join(["?"] * len(chunk))
        rows = conn.execute(
            f"SELECT protein_id, preferred_name FROM proteins WHERE protein_id IN ({qmarks})",
            (*chunk,),
        ).fetchall()
        for r in rows:
            attrs[r["protein_id"]] = {"preferred_name": r["preferred_name"] or r["protein_id"]}
    # fallback name
    for pid in protein_ids:
        if pid not in attrs:
            attrs[pid] = {"preferred_name": pid}
    return attrs
