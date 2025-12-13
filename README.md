# STRING_app

# フォルダ構成
string_app/
  data/
    string.sqlite           # 作成物
    raw/                    # 既存のSTRINGファイル置き場（任意）
  scripts/
    build_db.py             # raw→sqlite変換（1回だけ）
  app/
    app.py                  # Streamlit本体
    db.py                   # クエリ関数（ID解決、サブグラフ取得）
    viz.py                  # 描画（pyvis等）
  requirements.txt
