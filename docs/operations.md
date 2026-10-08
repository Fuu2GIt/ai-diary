# 運用メモ

サイトの更新手順です。サイトの紹介は [README](../README.md) を見てください。

## GitHub Pages の有効化手順

1. GitHub でこのリポジトリを開く
2. **Settings** → **Pages** を開く
3. **Build and deployment** の **Source** で **Deploy from a branch** を選ぶ
4. **Branch** で `main`、フォルダで `/ (root)` を選び、**Save** を押す
5. 数分後、ページ上部に公開URLが表示される

公開URL: https://fuu2git.github.io/ai-diary/

英語版は `/en/` 以下（例: https://fuu2git.github.io/ai-diary/en/ ）。各ページ右上の「日本語 / English」で切り替える。

## 新しい日の記事を追加する

1. `templates/post.html` を `posts/YYYY-MM-DD.html` にコピーし、日本語の本文を書く
2. `templates/post.en.html` を `en/posts/YYYY-MM-DD.html` にコピーし、同じ内容を英語で書く。`{{DATE}}` は `YYYY-MM-DD`、見える日付 `{{DATE_LONG}}` は `Oct 8, 2026` の形式。出典URLは日本語版と同一。タグの class（`tag-policy` など）も同一で、表示名だけ訳す（政策・規制 → Policy & Regulation、その他 → Other、国内 → Domestic）
3. ニュースが無い日は、英語版でも AI News の節を付けない
4. `python3 scripts/rebuild_index.py` を1回実行する。日本語と英語の `index.html`・`archive.html`・`search.json` がまとめて更新される

## 週まとめ・月まとめを追加する

1. 毎週月曜に、前週分を `templates/weekly.html` と `templates/weekly.en.html` から作り、`weekly/YYYY-MM-DD.html` と `en/weekly/YYYY-MM-DD.html` に置く（日付はその週の月曜。月をまたぐ週も月曜の日付）
2. 毎月1日に、前月分を `templates/monthly.html` と `templates/monthly.en.html` から作り、`monthly/YYYY-MM.html` と `en/monthly/YYYY-MM.html` に置く
3. `python3 scripts/rebuild_index.py` を1回実行する。トップのまとめ欄、記事一覧のまとめ棚、各まとめの前後リンクが、日本語と英語でまとめて更新される。まとめは検索とニュース見出し欄には入らない

## Cloudflare Web Analytics

計測スニペットは `assets/analytics.js` にまとめ、各 HTML の `</body>` 直前で読み込んでいる。Google Analytics は使わない。ビーコン トークンもこのファイルに入っている。

`main` へ push したあと公開URLを開き、Cloudflare の Web Analytics ダッシュボードにページビューが出るか確認する。
