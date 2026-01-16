# scripts/build_db.py
import argparse
import gzip
import os
import re
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

BATCH = 50_000


def open_maybe_gz(path: Path):
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "rt", encoding="utf-8", errors="replace")


def sniff_header_and_split(line: str) -> Tuple[List[str], bool]:
    """
    STRING files often have a header line starting with '#'.
    Return (columns, is_header).
    """
    s = line.rstrip("\n")
    if not s:
        return ([], False)
    if s.startswith("#"):
        s2 = s.lstrip("#").strip()
        cols = re.split(r"\s+", s2)
        return (cols, True)
    # might be header without '#', but MVP: treat as data
    cols = re.split(r"\s+", s.strip())
    return (cols, False)


def ensure_parent(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)


def create_schema(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA temp_store=MEMORY;")

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS proteins (
            protein_id TEXT PRIMARY KEY,
            preferred_name TEXT,
            annotation TEXT
        );

        CREATE TABLE IF NOT EXISTS aliases (
            alias TEXT COLLATE NOCASE,
            protein_id TEXT,
            source TEXT,
            taxon_id TEXT
        );

        CREATE TABLE IF NOT EXISTS edges_func (
            p1 TEXT,
            p2 TEXT,
            score_int INTEGER
        );

        CREATE TABLE IF NOT EXISTS edges_phys (
            p1 TEXT,
            p2 TEXT,
            score_int INTEGER
        );
        """
    )
    conn.commit()


def recreate_indexes(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.executescript(
        """
        DROP INDEX IF EXISTS idx_aliases_alias;
        DROP INDEX IF EXISTS idx_aliases_pid;
        DROP INDEX IF EXISTS idx_edges_func_p1;
        DROP INDEX IF EXISTS idx_edges_func_p2;
        DROP INDEX IF EXISTS idx_edges_func_score;
        DROP INDEX IF EXISTS idx_edges_phys_p1;
        DROP INDEX IF EXISTS idx_edges_phys_p2;
        DROP INDEX IF EXISTS idx_edges_phys_score;

        CREATE INDEX idx_aliases_alias ON aliases(alias);
        CREATE INDEX idx_aliases_pid   ON aliases(protein_id);

        CREATE INDEX idx_edges_func_p1    ON edges_func(p1);
        CREATE INDEX idx_edges_func_p2    ON edges_func(p2);
        CREATE INDEX idx_edges_func_score ON edges_func(score_int);

        CREATE INDEX idx_edges_phys_p1    ON edges_phys(p1);
        CREATE INDEX idx_edges_phys_p2    ON edges_phys(p2);
        CREATE INDEX idx_edges_phys_score ON edges_phys(score_int);
        """
    )
    conn.commit()


def parse_taxon_id(protein_id: str) -> Optional[str]:
    # e.g., "9606.ENSP00000354587"
    m = re.match(r"^(\d+)\.", protein_id)
    return m.group(1) if m else None


def load_proteins_info(conn: sqlite3.Connection, info_path: Path):
    """
    Expected columns (common):
      #protein_id preferred_name annotation
    """
    cur = conn.cursor()
    inserted = 0

    with open_maybe_gz(info_path) as f:
        first = f.readline()
        cols, is_header = sniff_header_and_split(first)
        if not is_header:
            # treat first as data; fallback column positions
            cols = ["protein_id", "preferred_name", "annotation"]
            f = iter([first] + list(f))
        else:
            f = iter(f)

        # map columns
        colmap: Dict[str, int] = {c: i for i, c in enumerate(cols)}
        pid_i = colmap.get("protein_id", 0)
        name_i = colmap.get("preferred_name", 1)
        ann_i = colmap.get("annotation", 2)

        buf: List[Tuple[str, str, str]] = []
        for line in f:
            if not line.strip():
                continue
            if line.startswith("#"):
                continue
            parts = re.split(r"\s+", line.rstrip("\n"))
            if len(parts) <= max(pid_i, name_i, ann_i):
                continue
            pid = parts[pid_i]
            pname = parts[name_i] if name_i < len(parts) else ""
            ann = " ".join(parts[ann_i:]) if ann_i < len(parts) else ""
            buf.append((pid, pname, ann))
            if len(buf) >= BATCH:
                cur.executemany(
                    "INSERT OR REPLACE INTO proteins(protein_id, preferred_name, annotation) VALUES (?, ?, ?)",
                    buf,
                )
                inserted += len(buf)
                buf.clear()

        if buf:
            cur.executemany(
                "INSERT OR REPLACE INTO proteins(protein_id, preferred_name, annotation) VALUES (?, ?, ?)",
                buf,
            )
            inserted += len(buf)
    conn.commit()
    return inserted


def load_aliases(conn: sqlite3.Connection, aliases_path: Path):
    """
    Common columns:
      #protein_id alias source
    Some builds may include taxon separately; we infer from protein_id when possible.
    """
    cur = conn.cursor()
    inserted = 0

    with open_maybe_gz(aliases_path) as f:
        first = f.readline()
        cols, is_header = sniff_header_and_split(first)
        if not is_header:
            cols = ["protein_id", "alias", "source"]
            f = iter([first] + list(f))
        else:
            f = iter(f)

        colmap: Dict[str, int] = {c: i for i, c in enumerate(cols)}
        pid_i = colmap.get("protein_id", 0)
        alias_i = colmap.get("alias", 1)
        source_i = colmap.get("source", 2)

        buf: List[Tuple[str, str, str, str]] = []
        for line in f:
            if not line.strip():
                continue
            if line.startswith("#"):
                continue
            parts = re.split(r"\s+", line.rstrip("\n"))
            if len(parts) <= max(pid_i, alias_i, source_i):
                continue
            pid = parts[pid_i]
            alias = parts[alias_i]
            source = parts[source_i] if source_i < len(parts) else ""
            taxon = parse_taxon_id(pid) or ""
            buf.append((alias, pid, source, taxon))
            if len(buf) >= BATCH:
                cur.executemany(
                    "INSERT INTO aliases(alias, protein_id, source, taxon_id) VALUES (?, ?, ?, ?)",
                    buf,
                )
                inserted += len(buf)
                buf.clear()

        if buf:
            cur.executemany(
                "INSERT INTO aliases(alias, protein_id, source, taxon_id) VALUES (?, ?, ?, ?)",
                buf,
            )
            inserted += len(buf)

    conn.commit()
    return inserted


def load_edges(conn: sqlite3.Connection, links_path: Path, table: str):
    """
    Common columns:
      protein1 protein2 combined_score
    Score is usually integer (0..1000).
    """
    cur = conn.cursor()
    inserted = 0

    with open_maybe_gz(links_path) as f:
        first = f.readline()
        cols, is_header = sniff_header_and_split(first)
        if not is_header:
            cols = ["protein1", "protein2", "combined_score"]
            f = iter([first] + list(f))
        else:
            f = iter(f)

        colmap: Dict[str, int] = {c: i for i, c in enumerate(cols)}
        p1_i = colmap.get("protein1", 0)
        p2_i = colmap.get("protein2", 1)
        sc_i = colmap.get("combined_score", colmap.get("score", 2))

        buf: List[Tuple[str, str, int]] = []
        for line in f:
            if not line.strip():
                continue
            if line.startswith("#"):
                continue
            parts = re.split(r"\s+", line.rstrip("\n"))
            if len(parts) <= max(p1_i, p2_i, sc_i):
                continue
            p1 = parts[p1_i]
            p2 = parts[p2_i]
            try:
                sc = int(parts[sc_i])
            except ValueError:
                continue

            # canonical undirected edge storage
            if p2 < p1:
                p1, p2 = p2, p1

            buf.append((p1, p2, sc))
            if len(buf) >= BATCH:
                cur.executemany(f"INSERT INTO {table}(p1, p2, score_int) VALUES (?, ?, ?)", buf)
                inserted += len(buf)
                buf.clear()

        if buf:
            cur.executemany(f"INSERT INTO {table}(p1, p2, score_int) VALUES (?, ?, ?)", buf)
            inserted += len(buf)

    conn.commit()
    return inserted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=str, required=True, help="Output sqlite path")
    ap.add_argument("--info", type=str, required=True, help="protein.info(.gz)")
    ap.add_argument("--aliases", type=str, required=True, help="protein.aliases(.gz)")
    ap.add_argument("--links", type=str, required=True, help="protein.links(.gz) functional associations")
    ap.add_argument("--physical", type=str, default="", help="optional: protein.physical.links(.gz)")
    ap.add_argument("--overwrite", action="store_true", help="overwrite existing db")
    args = ap.parse_args()

    db_path = Path(args.db)
    ensure_parent(db_path)

    if args.overwrite and db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    try:
        create_schema(conn)

        print("[1/4] Loading proteins info...")
        n_info = load_proteins_info(conn, Path(args.info))
        print(f"  inserted/updated: {n_info}")

        print("[2/4] Loading aliases...")
        n_alias = load_aliases(conn, Path(args.aliases))
        print(f"  inserted: {n_alias}")

        print("[3/4] Loading functional links...")
        n_edges = load_edges(conn, Path(args.links), "edges_func")
        print(f"  inserted: {n_edges}")

        if args.physical:
            print("[4/4] Loading physical links...")
            n_phys = load_edges(conn, Path(args.physical), "edges_phys")
            print(f"  inserted: {n_phys}")
        else:
            print("[4/4] physical links: skipped")

        print("Creating indexes...")
        recreate_indexes(conn)
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
