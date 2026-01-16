# STRING_app


### protein.physical.links

protein.physical.links(=*.protein.physical.links.vXX.X.txt.gz)には、STRINGが定義する「物理的相互作用サブネットワーク」のエッジが入っている。
protein.linksよりも直接結合や同一複合体など、物理的に接触し得る関係に寄せたネットワーク。





## 1) protein.physical.links は何のデータか

* **protein.physical.links.*.txt.gz** は、STRING が提供する **“physical subnetwork（物理的相互作用ネットワーク）”** のリンク集合です（タンパク質ペアとスコア）。([STRING][1])
* 物理サブネットワークは、主に **experiments / database / textmining** の3チャネル由来の情報を使って構成され、通常の「機能的関連（functional association）」ネットワークとは **スコア計算が異なる** と明記されています。([PMC][2])
* “detailed” 版は **チャネル別サブスコア付き**、 “full” 版は **direct vs interologs（同種内の直接証拠か、オルソログ転移か）** の区別付きです。([STRING][1])

## 2) experiments / database / textmining の違い（STRING内での定義）

STRING v12 系の説明（NAR/PMC）に沿うと、概ねこう分かれます。([PMC][2])

* **experiments（実験）**
  「相互作用（会合）を見つける目的で行われた実験」に由来するエビデンスを、BioGRID・DIP・PDB・IntAct/IMEx などの一次DBから取り込み。([PMC][2])

* **database（知識DB、いわゆる“textbook knowledge”）**
  KEGG・Reactome・MetaCyc・Complex Portal・GO Complexes 等、キュレーション済み知識ベースからの複合体・経路・機能的つながりを取り込み。([PMC][2])

* **textmining（文献テキストマイニング）**
  PMC OA（本文）、PubMed 抄録、OMIM/SGD の要約テキスト等からタンパク質名の共起・関係抽出を行い、頻度などに基づいてスコア化。([PMC][2])

（補足）物理サブネットワークは、この3チャネル（experiments/database/textmining）からも作られますが、**スコアの推定法自体が functional network と違う**、というのが重要点です。([PMC][2])

## 3) まず「通常の STRING スコア」はどういう意味か（functional network）

* STRING の各スコアは **相互作用の“強さ”ではなく“真である確からしさ（confidence）”** を 0〜1 で表す、という立て付けです。([STRING][3])
* 各エビデンスはチャネルごとにまずスコア化され、（代表例として）**KEGG パスウェイ同一マップへの共所属**などを “ground truth” としたベンチマークでキャリブレーションされ、最後に **combined score** に統合されます。([PMC][2])

### combined score の統合式（重要）

STRING Help では、各チャネルスコア (s_i) から **prior (p=0.041)** を外して結合し、最後に prior を戻す形が明示されています。([STRING][4])

* prior除去: ((s_i-p)/(1-p))
* 結合: (1-\prod (1-s_i'))（逐次計算の形で説明）
* prior復元: (s + p(1-s)) ([STRING][4])

## 4) 「physical interaction の確信度」はどう計算されるのか（ポイント）

STRING 2021 の更新論文で、**physical interaction score（物理スコア）**の導出が説明されています。([PMC][5])

要点だけ抜くと：

1. **gold standard（正解データ）として信頼できるタンパク質複合体集合が必要**
   STRING は、十分な量と質のある gold standard として **Complex Portal の“酵母複合体”**を使う、としています。([PMC][5])

2. **実験由来の相互作用から、純粋に機能的（非物理）になりがちなものを除外**
   具体的に、**遺伝学的干渉（genetic interference）だけに基づく相互作用は除外**し、残りを物理相互作用の候補としてベンチマークします。([PMC][5])

3. **“同一複合体に一緒に入る確率”として physical score を定義**
   物理相互作用では「同じ複合体に同時に含まれる」ことを真陽性の基準にし、巨大複合体でペアが爆増して過大評価されないよう、複合体内の次数（degree）に基づく重み付けで補正しながらベンチマークする、と説明されています。([PMC][5])

4. **gold standard に直接かからない部分は “functional↔physical の関係”でキャリブレーションして推定し、他生物にも適用**
   gold standard から得た対応関係（キャリブレーション曲線）を使って、未カバー部分や他種にも physical スコアを割り当てる（酵母で得た校正を他種へ適用）流れです。([PMC][5])

つまり、「physical.links のスコア」は単に experiments/database/textmining の合算ではなく、**“複合体共所属（物理）”を基準にした別の確率校正**が入っています。([PMC][5])

## 5) ローカルで見るときの実務的な対応

* ダウンロードページ上、links 系ファイルは **スコアが 1000 倍（整数）**で入る注意があります。([STRING][1])

  * 例：`872` は 0.872 相当。([STRING][4])
* “detailed” のサブスコア列名は、FAQで **nscore/fscore/pscore/ascore/escore/dscore/tscore** などの意味がまとまっています（physical.detailed でも列名がこれに沿うことが多い）。([STRING][4])
* direct vs interologs を明確に分けたい場合は “full” を使うのが前提です（physical でも full が提供されています）。([STRING][1])

以上が、STRING の **physical.links の中身**と、**物理的相互作用スコアの作り方（考え方）**、および **実験・知識DB・文献の違い**の整理です。

[1]: https://string-db.org/cgi/download "Downloads - STRING functional protein association networks"
[2]: https://pmc.ncbi.nlm.nih.gov/articles/PMC9825434/ "
            The STRING database in 2023: protein–protein association networks and functional enrichment analyses for any sequenced genome of interest - PMC
        "
[3]: https://string-db.org/cgi/info?utm_source=chatgpt.com "Info - STRING functional protein association networks"
[4]: https://string-db.org/help/faq/ "FAQ - STRING Help"
[5]: https://pmc.ncbi.nlm.nih.gov/articles/PMC7779004/ "
            The STRING database in 2021: customizable protein–protein networks, and functional characterization of user-uploaded gene/measurement sets - PMC
        "
