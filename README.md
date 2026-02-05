# STRING_app

ローカルに構築した STRING SQLite DB から、指定した遺伝子/タンパク質のサブネットワークを抽出・可視化する Streamlit アプリ（MVP）。
入力は gene symbol / UniProt / STRING protein_id など混在OKで、機能的ネットワーク（protein.links）と物理的相互作用（protein.physical.links）を切り替えて表示できます。

## UI Preview
![STRING ローカル相互作用ネットワーク（MVP）](docs/image.png)
*例: TP53 を 1-hop 展開（physical）で可視化*

## 主な機能
- 混在IDの解決（gene symbol / UniProt / STRING protein_id）
- 機能的ネットワーク（functional）/ 物理的ネットワーク（physical）の切替
- スコア閾値でエッジをフィルタ
- 「誘導部分グラフ」または「1-hop展開」でサブネットワーク作成
- PyVis によるインタラクティブ可視化（ノードサイズ=degree、エッジ幅=score）
- nodes / edges を CSV でダウンロード

## 動作環境
- Python 3.9（venvで実行確認）
- OS: Windows でのみ動作確認（macOS/Linux 未検証）
- 依存関係: `requirements.txt`（streamlit / pyvis / pandas / networkx）
- DBサイズの目安: ヒト v12.0 で約 2.3GB（環境により変動）

## クイックスタート
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app/app.py
```

## データ準備
本リポジトリでは SQLite DB / 生データは `.gitignore` で除外されています。
以下の STRING データを取得し、`data/raw/` に配置してください。

必須ファイル（例: ヒト 9606 / v12.0）:
- `9606.protein.info.v12.0.txt.gz`
- `9606.protein.aliases.v12.0.txt.gz`
- `9606.protein.links.v12.0.txt.gz`
- `9606.protein.physical.links.v12.0.txt.gz`（物理ネットワークを使う場合）

## DB作成（生データからSQLiteを作る）
既に `data/string.sqlite` がある場合はスキップできます。

```powershell
python scripts/build_db.py `
  --db data/string.sqlite `
  --info data/raw/9606.protein.info.v12.0.txt.gz `
  --aliases data/raw/9606.protein.aliases.v12.0.txt.gz `
  --links data/raw/9606.protein.links.v12.0.txt.gz `
  --physical data/raw/9606.protein.physical.links.v12.0.txt.gz `
  --overwrite
```

- `--links` は `protein.links`（functional）を想定
- `--physical` を省略すると物理ネットワークは作成されません
- `combined_score` 列（0..1000）を使用します

## アプリの使い方
1. `streamlit run app/app.py` を実行
2. サイドバーで以下を設定
   - DBパス（既定: `data/string.sqlite`）
   - ネットワーク種別（functional / physical）
   - スコア閾値（0.0〜1.0）
   - モード（誘導部分グラフ / 1-hop 展開）
   - 最大ノード数（max_nodes）
   - `taxon_id`（任意: 例 9606）
3. テキストエリアにIDを入力（改行/カンマ区切り）
   - 例: `TP53`, `BRCA1`, `P04637`, `9606.ENSP00000354587`
4. 実行ボタンで可視化

### モードの違い
- 誘導部分グラフ: 入力ID同士の関係のみを抽出
- 1-hop 展開: 入力IDに直接つながる近傍ノードを加えて拡張
  近傍は `score` 合計が高い順で追加され、`max_nodes` まで制限されます

## 出力
- PyVis グラフ（ホバーで `preferred_name / protein_id / degree / score`）
- nodes / edges のテーブル
- nodes.csv / edges.csv のダウンロード

## スコアについて
- STRING の `combined_score`（0..1000）を保持
- UI の閾値は 0.0〜1.0 で指定し、内部で 0〜1000 に変換

## SQLite スキーマ
- `proteins(protein_id, preferred_name, annotation)`
- `aliases(alias, protein_id, source, taxon_id)`
- `edges_func(p1, p2, score_int)`
- `edges_phys(p1, p2, score_int)`

補足:
- エッジは無向グラフのため `p1 < p2` に正規化して保存

## ID 解決ロジック
- まず `proteins.protein_id` で完全一致
- 不一致の場合は `aliases.alias` を検索
- 複数ヒット時は `source` の優先順位で代表を選択し、他候補を表示

## プロジェクト構成
```
app/
  app.py      # Streamlit UI
  db.py       # SQLite アクセス/ID解決/グラフ構築
  viz.py      # PyVis 可視化
scripts/
  build_db.py # 生データからSQLiteを作成
data/
  raw/        # STRING 生データ（.txt.gz）
  string.sqlite
```

## 既知の制約・注意点
- IDが曖昧な場合は自動で候補が選ばれます（必要なら `taxon_id` を指定）
- ノード数が多いと描画が重くなります（閾値を上げる/`max_nodes` を下げる）
- `edges_phys` は `--physical` を指定してDBを作成しないと存在しません

## テスト
- 現状は自動テスト未整備

## データ取得元 / ライセンス / 引用
- Downloads（公式）: https://string-db.org/cgi/download
- Licensing（CC BY 4.0）: https://string-db.org/cgi/access.pl?footer_active_subpage=licensing
- Citation（How to cite STRING）: https://string-db.org/help/faq/
- 参考論文: https://academic.oup.com/nar/article/51/D1/D638/6825349
- リポジトリのライセンス: 要確認

## 要確認事項（ここを埋めれば完成）
- リポジトリのライセンス
- `scripts/backtest.py` / `scripts/ranmdom.py` をREADMEに含めるか（別用途の可能性）
