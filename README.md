# Elsevier CAS 単段組・論文テンプレート

元フォルダ `2026_TRC_GIDL` の LaTeX 書式を再利用できる GitHub テンプレートです。
論文ごとにこのテンプレートから専用のリポジトリを作り、その中で執筆します。

**[このテンプレートから新しい論文を作成](https://github.com/FuruhashiFumihito/elsevier-cas-sc-template/generate)**

## 新しい論文を始める

1. 上のリンク、または GitHub の **Use this template → Create a new repository** を開きます。
2. 自分のアカウントを所有者にし、`2026-paper-topic` など論文ごとの名前を付けます。
   公開する予定がなければ **Private** を選びます。**Include all branches** はオフのままにします。
3. **Create repository from template** を押します。新しい論文は、できたリポジトリの中で編集します。
4. 新しいリポジトリを手元に取得し、フォルダ全体を VS Code などで開きます。
   GitHub の **Code** から GitHub Desktop で開くか、リポジトリをクローンできます。
5. `main.tex` の題名・著者・要旨・本文を置き換え、`references.bib` に文献、`figures/` に図を追加します。
6. Mac では `build.command` をダブルクリックします。完成PDFは `out/main.pdf` に出力されます。
   編集したソースを新しい論文のリポジトリにコミット・プッシュして保存します。

`preview.pdf` はテンプレートの見本で、自動更新されません。執筆中のPDFは `out/main.pdf` を確認します。
ビルド途中のファイルと `out/` は Git の管理から除外しています。

### テンプレートと各論文の関係

テンプレートから作ったリポジトリは、同じファイル構成で独立した履歴を始めます。
論文Aと論文Bは、それぞれこのテンプレートから作成してください。
テンプレートには共通の書式改善だけを戻し、本文・著者情報・研究データは各論文側で管理します。
テンプレートを更新しても、作成済みの論文には自動反映されません。
必要な書式修正だけを各論文へ取り込みます。

これは GitHub の **Template repository** 機能を使う運用です。
Fork は親リポジトリの履歴を引き継ぎますが、テンプレートからの新規作成は1つの初期コミットから始まります。
[GitHub公式ガイド](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-repository-from-a-template)
に手順と違いが説明されています。

### ターミナルで作成する場合

GitHub CLI が使える環境では、次の操作で非公開の論文リポジトリを作り、手元に取得できます。
`2026-paper-topic` は新しい論文の名前に置き換えてください。

```sh
gh repo create FuruhashiFumihito/2026-paper-topic \
  --template FuruhashiFumihito/elsevier-cas-sc-template \
  --private --clone
cd 2026-paper-topic
./build.command
```

Codex には「`FuruhashiFumihito/elsevier-cas-sc-template` から、新しい論文用の非公開リポジトリ
`論文名` を作って」と依頼できます。新論文の研究内容と投稿先は、その都度指定します。

### 執筆・ビルド環境

既存の TeX Live / MacTeX と `latexmk` が必要です。検証環境は `PROVENANCE.md` に記録しています。
VS Code ではフォルダ全体を開き、LaTeX Workshop のビルド操作を使えます。
`main.tex` だけを移動するとクラスや引用スタイルを見つけられないため、フォルダ単位で扱ってください。

## 引き継いだ形式

- `cas-sc` の単段組、題名・著者・所属、左側のキーワード欄と右側の要旨欄
- 独立ページの Graphical abstract と Highlights
- Introduction → Literature review → Methodology → Numerical experiments → Conclusion
- Acknowledgments、付録、著者年方式の参考文献
- 左寄せの数式、図表キャプション、サブ図、表の注記、アルゴリズム
- 元原稿のフォント、余白、キャプション幅修正、pLaTeX → dvipdfmx / pBibTeX のビルド設定

`a4paper` は元の指定のままですが、同梱クラスの geometry 設定により実際の用紙は
**192 × 262 mm** です。これは元PDFと同じ寸法です。A4へ変更すると元の見た目から変わります。

節見出しは出発点です。研究内容に合わせて Empirical analysis や Discussion などに変更できます。
元論文の科学的主張、モデル、結果、研究コード、データ、文献一覧、助成金番号は引き継いでいません。
著者名、メール、ORCID、所属も新しい論文で確認して記入してください。

## ファイルの役割

| ファイル | 用途 |
| --- | --- |
| `main.tex` | 著者情報、本文、付録、図表・数式・疑似コードの書式例 |
| `references.bib` | 新しい論文の文献。初期状態の1件は架空の書式確認用 |
| `figures/` | 新しい研究の図 |
| `cas-sc.cls`, `cas-common.sty` | 元フォルダからそのまま引き継いだクラスとスタイル |
| `cas-model2-names.bst` | 著者年方式の BibTeX スタイル |
| `cas-email.jpeg` | 著者欄のメールアイコン。削除しないでください |
| `latexmkrc` | 元の pLaTeX ビルド設定。出力先は `out/` |
| `latexmkrc-pdflatex` | 英文用の代替設定。出力先は `out-pdflatex/` |
| `build.command` | Mac のビルド入口。端末からも利用可能 |
| `.vscode/settings.json` | LaTeX Workshop の設定 |
| `preview.pdf` | テンプレートの見本。執筆後は `out/main.pdf` を確認 |
| `paper/` | 新しい研究の主張・意思決定・根拠を整理する空の任意記録 |
| `PROVENANCE.md`, `source-assets.sha256` | 引き継いだファイルと検証の記録 |

## 必要な部分だけ残す

`main.tex` 冒頭付近のスイッチを変更します。

```latex
\showgraphicalabstractfalse  % Graphical abstract を表示しない
\showhighlightsfalse         % Highlights を表示しない
\showformattingexamplesfalse % 付録の書式例を表示しない
```

図表・数式・アルゴリズムの書式例は、必要な箇所へコピーして中身を差し替えてください。
表のダッシュは未記入を表し、数値データではありません。
`replace_me_reference` は架空の文献です。実際の根拠として引用せず、本文の引用例と一緒に削除します。
著者の CRediT 貢献、利益相反、データ公開、生成AI利用の記述は事実確認後に追加します。

投稿前に、`TODO`、`replace_me`、`example.com`、`First Author`、`Second Author`、
`Formatting example`、`PLACEHOLDER` が残っていないか確認してください。
図表参照・引用を確認し、最新の投稿先の指示に照らして必要な別ファイルを準備します。
これは元フォルダの書式を保存したもので、投稿先の最新規定への適合を保証するものではありません。

## ビルドの選択肢

通常は元と同じ設定を使います。

```sh
./build.command
# 同等の操作: latexmk -norc -r latexmkrc main.tex
```

英文のみで pdfLaTeX を使う場合は次の設定も利用できます。

```sh
./build.command pdflatex
# 出力先: out-pdflatex/main.pdf
```

LuaLaTeX / XeLaTeX 用には設定していません。日本語を本文に使う場合は既定の pLaTeX を使い、
最終的な文字や書式を確認してください。オンライン環境では同梱ファイルを一式アップロードし、
pdfLaTeX と BibTeX を選ぶ方法が考えられますが、オンラインでの実行は未検証です。

元の `cp.sh` にあった毎回の全再ビルドと後処理は必須ではないため含めず、
通常のビルド1回で必要な再実行を `latexmk` に任せます。

## Codex 内蔵プレビューについて

`main.tex` はエディタで編集できますが、今回の内蔵コンパイラは XeTeX ベースで、
同梱した CAS 2.4 と pLaTeX の複数ファイル構成をそのまま再現できませんでした。
見た目の確認は同梱の `preview.pdf`、編集後の確認は `build.command` で生成する
`out/main.pdf` を使ってください。既存の TeX 環境での生成は確認済みです。

## Codex と研究記録

`paper/` は `research-paper-system` の空の記録様式です。LaTeX のビルドには使いません。
新しい研究の問い・主張・根拠・意思決定が決まったときに記入してください。
元研究の科学的判断や、確認されていない「有効な決定」は登録していません。
