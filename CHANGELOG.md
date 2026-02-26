# CHANGELOG

## v0.1.0
- STRING の SQLite DB をローカルで参照し、入力 ID から相互作用ネットワークを可視化できる
- gene symbol / UniProt / STRING protein_id の混在入力に対応
- functional と physical の 2 種類のネットワークを切り替えて表示できる
- スコア閾値（0.0〜1.0）でエッジをフィルタリングできる
- 誘導部分グラフと 1-hop 展開の 2 モードでサブネットワークを作成できる
- PyVis によるインタラクティブなグラフ表示ができる
- ノード・エッジ一覧をテーブルで確認し、CSV でダウンロードできる
- STRING 配布ファイルから `scripts/build_db.py` で SQLite DB を作成できる
- SQLite 生データと生成物をリポジトリ外管理しやすい構成になっている
