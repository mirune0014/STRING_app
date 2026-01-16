# app/app.py
import io
import pandas as pd
import streamlit as st
from streamlit.components.v1 import html as st_html

from db import connect, resolve_ids, expand_1hop, fetch_edges_induced, get_node_attributes

st.set_page_config(page_title="STRING Local Network MVP", layout="wide")


def parse_input(text: str):
    # split by whitespace and commas/newlines
    raw = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = line.replace(",", " ")
        raw.extend([t.strip() for t in line.split() if t.strip()])
    # de-dup preserve order
    seen = set()
    out = []
    for t in raw:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


st.title("STRING ローカル相互作用ネットワーク (MVP)")

with st.sidebar:
    db_path = st.text_input("SQLite DB パス", value="data/string.sqlite")
    network_type = st.selectbox("ネットワーク種別", ["functional (links)", "physical (physical.links)"])
    table = "edges_func" if network_type.startswith("functional") else "edges_phys"

    thr = st.slider("スコア閾値 (0.0–1.0)", min_value=0.0, max_value=1.0, value=0.70, step=0.01)
    score_thr_int = int(round(thr * 1000))

    mode = st.radio("モード", ["入力集合内のみ", "1-hop拡張"], index=0)
    max_nodes = st.number_input("最大ノード数", min_value=50, max_value=2000, value=300, step=50)

    taxon_id = st.text_input("taxon_id（任意・例: 9606）", value="")

st.write("入力（遺伝子名 / UniProt / STRING protein_id 混在可、改行区切り）")
input_text = st.text_area("", height=160, placeholder="例:\nTP53\nBRCA1\n9606.ENSP00000354587\nP04637")

run = st.button("実行", type="primary")

if run:
    queries = parse_input(input_text)
    if not queries:
        st.error("入力が空です。")
        st.stop()

    try:
        conn = connect(db_path)
    except Exception as e:
        st.error(f"DBを開けません: {e}")
        st.stop()

    try:
        resolved = resolve_ids(conn, queries, taxon_id=taxon_id.strip() or None)
        df_res = pd.DataFrame([r.__dict__ for r in resolved])

        col1, col2 = st.columns([1, 2])

        with col1:
            st.subheader("ID解決結果")
            st.dataframe(df_res, use_container_width=True, height=360)

        # seeds
        seed_ids = [r.protein_id for r in resolved if r.status in ("resolved", "ambiguous") and r.protein_id]
        seed_ids = list(dict.fromkeys(seed_ids))  # unique preserve order

        if not seed_ids:
            st.error("解決できたIDがありません。")
            st.stop()

        # build graph
        if mode == "1-hop拡張":
            nodes, edges = expand_1hop(
                conn,
                seed_ids=seed_ids,
                score_thr_int=score_thr_int,
                table=table,
                max_nodes=int(max_nodes),
            )
        else:
            nodes = seed_ids
            edges = fetch_edges_induced(conn, nodes, score_thr_int, table)

        # enforce hard caps (safety)
        if len(nodes) > int(max_nodes):
            nodes = nodes[: int(max_nodes)]

        node_attrs = get_node_attributes(conn, nodes)

        # dataframes for export / display
        deg = {n: 0 for n in nodes}
        for a, b, _ in edges:
            if a in deg:
                deg[a] += 1
            if b in deg:
                deg[b] += 1

        df_nodes = pd.DataFrame(
            {
                "protein_id": nodes,
                "preferred_name": [node_attrs[n]["preferred_name"] for n in nodes],
                "degree": [deg.get(n, 0) for n in nodes],
            }
        )

        df_edges = pd.DataFrame(edges, columns=["p1", "p2", "score_int"])
        df_edges["score"] = df_edges["score_int"] / 1000.0

        with col2:
            st.subheader("ネットワーク")
            st.caption("注意: スコアは相互作用の“強度”ではなく、関係が真である“確信度”の指標として扱ってください。")
            from viz import build_pyvis_html

            html = build_pyvis_html(nodes, edges, node_attrs, height_px=650)
            st_html(html, height=680, scrolling=True)

        st.subheader("エクスポート")
        c1, c2 = st.columns(2)

        with c1:
            st.write(f"nodes: {len(df_nodes)}")
            st.dataframe(df_nodes.head(30), use_container_width=True, height=260)
            buf = io.StringIO()
            df_nodes.to_csv(buf, index=False)
            st.download_button("nodes.csv をダウンロード", data=buf.getvalue(), file_name="nodes.csv", mime="text/csv")

        with c2:
            st.write(f"edges: {len(df_edges)}")
            st.dataframe(df_edges.head(30), use_container_width=True, height=260)
            buf2 = io.StringIO()
            df_edges.to_csv(buf2, index=False)
            st.download_button("edges.csv をダウンロード", data=buf2.getvalue(), file_name="edges.csv", mime="text/csv")

    finally:
        try:
            conn.close()
        except Exception:
            pass
