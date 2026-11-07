#!/usr/bin/env python3
"""cancel.json から cancel.html（サブスクの解約方法・解約ページ早見表）を生成する。

    python build_cancel.py                # cancel.html を書く
    python build_cancel.py --check-links  # 書いたうえで、公式ページの URL が全部開けるか（HTTP の応答）を確かめる

cancel.json を見直したら（毎月の価格チェックのたびに確認日を更新したら）これを回して、
生成物ごと commit / push する。依存ライブラリなし。sitemap.xml は build_prices.py が
cancel.json の確認日を読んで書く（このスクリプトは sitemap を触らない）。

- 載せるのは「どこで解約するか（窓口）」と「公式の解約ページへのリンク＋確認日」と短い注意。
  手順の詳細は書かない（サービス側の画面が変わっても古くならないように。inbox ss-261105-2）。
- presets.json のサブスク（「固定費」以外）が全部 cancel.json に載っていることを確かめる。
  載っていなければ止まる（presets にサービスを足した時の足し忘れを防ぐ）。
- 🚨 Amazon・Adobe・ABEMA・OpenAI のヘルプは自動取得を 403/503 で弾くことがある。--check-links が
  それらで NG を出した時は、ブラウザで開いて確かめる（2026-11-07 の初回はブラウザで全部確認した）。
"""
from __future__ import annotations

import datetime as dt
import html
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "cancel.json"
PRESETS = ROOT / "presets.json"
OUT = ROOT / "cancel.html"

SITE_URL = "https://ks-jf.github.io/Subscope-site/"
APP_STORE_URL = "https://apps.apple.com/jp/app/id6785280296"
SUPPORT_MAIL = "subscope.app@proton.me"
EXCLUDED_CATEGORIES = {"固定費"}

# 解約の窓口（cancel.json の where）の表示
WHERE_LABEL = {
    "site": "サービスのサイト・アプリの設定",
    "apple": "Apple の「サブスクリプション」設定",
    "store": "App Store / Google Play の定期購入",
    "both": "登録した経路で違う（サイトで登録ならサイト、ストアで登録ならストア）",
}
WHERE_SHORT = {
    "site": "サービスのサイト",
    "apple": "Apple の設定",
    "store": "ストア",
    "both": "登録した経路",
}


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def load() -> dict:
    return json.loads(SRC.read_text(encoding="utf-8"))


def preset_names() -> list[str]:
    data = json.loads(PRESETS.read_text(encoding="utf-8"))
    return [p["name"] for p in data["presets"] if p.get("category") not in EXCLUDED_CATEGORIES]


def jp_date(iso: str) -> str:
    parts = iso.split("-")
    if len(parts) == 3:
        return f"{int(parts[0])}年{int(parts[1])}月{int(parts[2])}日"
    if len(parts) == 2:
        return f"{int(parts[0])}年{int(parts[1])}月"
    return iso


def check(data: dict) -> None:
    """presets.json のサブスクが全部載っているか・where の値が決まった物か。外れたら止まる。"""
    names = {s["name"] for s in data["services"]}
    missing = [n for n in preset_names() if n not in names]
    if missing:
        sys.exit(f"cancel.json に無いサービス（presets.json にはある）: {', '.join(missing)}")
    bad = [s["name"] for s in data["services"] if s["where"] not in WHERE_LABEL]
    if bad:
        sys.exit(f"where が決まった値でない: {', '.join(bad)}")
    groups = set(data["groups"])
    off = [s["name"] for s in data["services"] if s["group"] not in groups]
    if off:
        sys.exit(f"group が groups に無い: {', '.join(off)}")


def check_links(data: dict) -> int:
    """公式ページの URL が開けるか（HEAD → だめなら GET）。NG の数を返す。"""
    urls: list[tuple[str, str]] = [(s["name"], s["url"]) for s in data["services"]]
    urls += [(k, v["url"]) for k, v in data["stores"].items()]
    seen: set[str] = set()
    ng = 0
    for name, url in urls:
        if url in seen:
            continue
        seen.add(url)
        status = "?"
        for method in ("HEAD", "GET"):
            req = urllib.request.Request(url, method=method, headers={
                "User-Agent": "Mozilla/5.0 (Subscope-site link check)", "Accept-Language": "ja,en;q=0.8"})
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    status = str(r.status)
                break
            except urllib.error.HTTPError as e:
                status = str(e.code)
                if e.code in (405, 403, 404) and method == "HEAD":
                    continue
                break
            except Exception as e:  # noqa: BLE001
                status = f"error {type(e).__name__}"
                break
        ok = status.startswith("2") or status.startswith("3")
        if not ok:
            ng += 1
        print(f"{'OK ' if ok else 'NG '} {status:>5}  {name}  {url}")
    return ng


def render_row(s: dict) -> str:
    where = WHERE_LABEL[s["where"]]
    src = (f"<a href=\"{esc(s['url'])}\" rel=\"noopener\" target=\"_blank\">{esc(s['label'])}</a>"
           f"<br><small class=\"muted\">{esc(jp_date(s['date']))} 確認</small>")
    return (
        "<tr>"
        f"<th scope=\"row\">{esc(s['name'])}</th>"
        f"<td class=\"where where-{esc(s['where'])}\" data-label=\"解約の窓口\">{esc(where)}</td>"
        f"<td class=\"src\" data-label=\"公式の解約ページ\">{src}</td>"
        f"<td class=\"note\" data-label=\"注意\">{esc(s['note'])}</td>"
        "</tr>"
    )


def render_group(name: str, items: list[dict], idx: int) -> str:
    rows = "".join(render_row(s) for s in items)
    return (
        f"<h2 id=\"g{idx}\">{esc(name)}</h2>"
        "<div class=\"tablewrap\"><table>"
        "<thead><tr><th scope=\"col\">サービス</th><th scope=\"col\">解約の窓口</th>"
        "<th scope=\"col\">公式の解約ページ</th><th scope=\"col\">注意</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )


def render_page(data: dict, today: dt.date) -> str:
    checked = data["checked"]
    services = data["services"]
    stores = data["stores"]
    groups = [(g, [s for s in services if s["group"] == g]) for g in data["groups"]]
    groups = [(g, items) for g, items in groups if items]
    n = len(services)
    n_both = sum(1 for s in services if s["where"] == "both")
    label = jp_date(checked)
    month = label[:label.index("月") + 1]

    nav = " ／ ".join(f"<a href=\"#g{i}\">{esc(g)}</a>" for i, (g, _) in enumerate(groups))
    sections = "".join(render_group(g, items, i) for i, (g, items) in enumerate(groups))
    app = stores["App Store"]
    play = stores["Google Play"]

    title = f"サブスクの解約方法 早見表｜主要{n}サービスの「どこで解約するか」と公式の解約ページ（{month}確認）"
    description = (
        f"Netflix・Spotify・Amazon プライム・YouTube Premium・ChatGPT Plus・iCloud+ など主要{n}サービスの解約方法を一覧化。"
        "サービスのサイトで解約するのか、App Store / Google Play の定期購入から解約するのかの見分け方と、"
        f"各サービスの公式の解約ページへのリンク（{label}確認）、解約後いつまで使えるか・年払いの注意をまとめました。"
    )

    ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": description,
        "dateModified": today.isoformat(),
        "inLanguage": "ja",
        "mainEntityOfPage": SITE_URL + "cancel.html",
        "author": {"@type": "Organization", "name": "Subscope"},
        "publisher": {"@type": "Organization", "name": "Subscope",
                      "logo": {"@type": "ImageObject", "url": SITE_URL + "icon.png"}},
    }
    faq = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": "サブスクはどこで解約すればいいですか？",
             "acceptedAnswer": {"@type": "Answer", "text": "登録した経路で決まります。サービスの Web サイトやアプリで登録した場合はそのサービスのアカウント設定、iPhone のアプリ内で登録した場合は iPhone の「設定」→ 自分の名前 →「サブスクリプション」（App Store）、Android のアプリ内で登録した場合は Google Play の「定期購入」から解約します。アプリを削除しても解約にはなりません。"}},
            {"@type": "Question", "name": "App Store 経由で登録したかどうかは、どう見分けますか？",
             "acceptedAnswer": {"@type": "Answer", "text": "iPhone の「設定」→ 自分の名前 →「サブスクリプション」の一覧にそのサービスが出ていれば App Store 経由です。出ていなければ、サービスのサイトか Google Play、または携帯電話会社などのパートナー決済で登録しています。"}},
            {"@type": "Question", "name": "解約するとすぐに使えなくなりますか？",
             "acceptedAnswer": {"@type": "Answer", "text": "多くのサービス（Netflix・Spotify・YouTube Premium・ChatGPT Plus・Google One など）は、解約しても支払い済みの期間の終わりまで使えます。ただし U-NEXT の Web 登録のように解約した時点で見られなくなるサービスもあるので、各サービスの公式ページで確認してください。"}},
            {"@type": "Question", "name": "年払いのサブスクを途中で解約したら、残りの期間分は返金されますか？",
             "acceptedAnswer": {"@type": "Answer", "text": "返金されないか、期間の終わりまで請求が続くのが一般的です（DAZN の年間プラン（月々払い）は 12 か月分の請求が続きます）。Adobe のように購入から 14 日以内なら全額返金という例外もあるので、年払いにする前に各サービスの解約ページで条件を確かめてください。"}},
        ],
    }

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}｜Subscope</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{SITE_URL}cancel.html">
<meta property="og:type" content="article">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{SITE_URL}cancel.html">
<meta property="og:image" content="{SITE_URL}icon.png">
<meta property="og:site_name" content="Subscope">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">
{json.dumps(ld, ensure_ascii=False, indent=1)}
</script>
<script type="application/ld+json">
{json.dumps(faq, ensure_ascii=False, indent=1)}
</script>
<style>
  :root{{ --blue:#0d47c9; --cyan:#2bd2e4; --ink:#1c1c22; --muted:#6a6c75; --warn:#b4541a; }}
  *{{box-sizing:border-box}}
  body{{font-family:-apple-system,'Helvetica Neue',Arial,"Hiragino Kaku Gothic ProN",Meiryo,sans-serif;
       margin:0;color:var(--ink);line-height:1.8;background:#fff;}}
  .hero{{background:linear-gradient(135deg,var(--blue),var(--cyan));color:#fff;padding:36px 20px 32px;}}
  .hero .in{{max-width:760px;margin:0 auto;}}
  .hero .brand{{display:flex;align-items:center;gap:10px;font-weight:700;font-size:.95em;margin-bottom:14px;}}
  .hero .brand img{{width:32px;height:32px;border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,.25);}}
  .hero .brand a{{color:#fff;text-decoration:none;}}
  .hero h1{{font-size:1.6em;margin:0 0 8px;line-height:1.4;letter-spacing:.01em;}}
  .hero p{{margin:0;opacity:.95;}}
  main{{max-width:760px;margin:0 auto;padding:28px 20px 60px;}}
  h2{{font-size:1.2em;margin:2em 0 .6em;padding-left:12px;border-left:4px solid var(--cyan);}}
  h3{{font-size:1.02em;margin:1.4em 0 .4em;}}
  p.nav{{font-size:.92em;line-height:2.2;}}
  a{{color:var(--blue);}}
  .tablewrap{{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid #e7ebf1;border-radius:12px;}}
  table{{border-collapse:collapse;width:100%;min-width:620px;font-size:.93em;}}
  th,td{{padding:10px 12px;border-bottom:1px solid #eee;text-align:left;vertical-align:top;}}
  thead th{{background:#f6f8fb;font-weight:700;font-size:.88em;color:var(--muted);white-space:nowrap;}}
  tbody th{{font-weight:600;white-space:nowrap;}}
  tbody tr:last-child th,tbody tr:last-child td{{border-bottom:none;}}
  td.where{{font-size:.9em;min-width:9em;}}
  td.where-both{{color:var(--warn);}}
  td.note{{font-size:.88em;color:#3a3a44;min-width:16em;}}
  td.src{{font-size:.88em;white-space:nowrap;}}
  .muted{{color:var(--muted);}}
  .warn{{color:var(--warn);}}
  .card{{background:#f6f8fb;border:1px solid #e7ebf1;border-radius:14px;padding:18px 20px;margin-top:14px;}}
  .routes{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:12px;}}
  .routes .r{{background:#fff;border:1px solid #e7ebf1;border-radius:12px;padding:14px 16px;font-size:.93em;}}
  .routes .r b{{display:block;color:var(--blue);margin-bottom:4px;}}
  .steps{{counter-reset:s;list-style:none;padding:0;margin:0;}}
  .steps li{{counter-increment:s;position:relative;padding:8px 0 8px 2.2em;border-bottom:1px solid #eee;}}
  .steps li:last-child{{border-bottom:none;}}
  .steps li::before{{content:counter(s);position:absolute;left:0;top:10px;width:1.6em;height:1.6em;border-radius:50%;
       background:var(--cyan);color:#fff;font-weight:700;font-size:.85em;display:flex;align-items:center;justify-content:center;}}
  .cta{{background:linear-gradient(135deg,var(--blue),var(--cyan));color:#fff;border-radius:16px;padding:24px 22px;margin-top:40px;text-align:center;}}
  .cta h2{{color:#fff;border:none;padding:0;margin:0 0 6px;font-size:1.15em;}}
  .cta p{{margin:0 0 16px;opacity:.95;}}
  .cta a.btn{{display:inline-block;background:#fff;color:var(--blue);text-decoration:none;font-weight:700;
       padding:12px 26px;border-radius:999px;box-shadow:0 6px 18px rgba(0,0,0,.18);}}
  .note ul{{padding-left:1.3em;margin:.4em 0;}}
  footer{{color:var(--muted);font-size:.85em;text-align:center;padding:28px 20px 60px;}}
  footer a{{margin:0 8px;}}

  /* 狭い画面では 1サービス=1カードに積み替える（prices.html・trials.html と同じ作り）。 */
  @media (max-width:640px){{
    .tablewrap{{overflow:visible;border:none;border-radius:0;}}
    table{{min-width:0;display:block;}}
    thead{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;}}
    tbody,tr,th,td{{display:block;}}
    tbody tr{{border:1px solid #e7ebf1;border-radius:12px;padding:10px 14px;margin-bottom:10px;}}
    tbody th{{font-size:1.02em;padding:0 0 6px;border-bottom:1px solid #eee;white-space:normal;}}
    tbody td{{padding:6px 0 0;border:none;display:flex;justify-content:space-between;
        align-items:baseline;gap:12px;text-align:right;min-width:0;}}
    tbody td::before{{content:attr(data-label);color:var(--muted);font-size:.85em;text-align:left;flex:none;}}
    tbody td.src,tbody td.where{{white-space:normal;}}
    tbody td.note{{display:block;text-align:left;}}
    tbody td.note::before{{display:block;margin-bottom:2px;}}
    tbody tr:last-child th,tbody tr:last-child td{{border-bottom:none;}}
  }}
</style>
</head>
<body>
  <div class="hero"><div class="in">
    <div class="brand"><img src="./icon.png" alt=""><a href="./">Subscope</a></div>
    <h1>サブスクの解約方法 早見表</h1>
    <p>主要{n}サービスの「どこで解約するか」と、公式の解約ページへのリンク。{esc(label)}に確認。</p>
  </div></div>

  <main>
    <p>サブスクの解約でいちばん多いつまずきは、<strong>「解約ボタンがどこにも無い」</strong>です。
    多くのサービスは<strong>登録した経路（サービスのサイトか、App Store / Google Play か）</strong>で解約する場所が変わり、
    このページの{n}サービスのうち {n_both} サービスがそうです。アプリを削除しても解約にはなりません。
    ここでは、サービスごとの解約の窓口と、公式の解約ページへのリンクを<strong>確認日つき</strong>でまとめました。
    手順そのものは各社の画面が変わるたびに古くなるので、ここには書かずに公式ページへつないでいます。</p>

    <p class="nav"><a href="#route">まず登録した経路を確かめる</a> ／ {nav} ／ <a href="#yearly">年払いと解約後の注意</a> ／ <a href="#about">このデータについて</a></p>

    <h2 id="route">まず「どこで登録したか」を確かめる</h2>
    <div class="card">
      <ol class="steps">
        <li><strong>iPhone の「設定」→ 自分の名前 →「サブスクリプション」</strong>を開く。<br>
          一覧にそのサービスが出ていれば <strong>App Store 経由</strong>。ここから解約します
          （<a href="{esc(app['url'])}" rel="noopener" target="_blank">{esc(app['label'])}</a>・{esc(jp_date(app['date']))}確認）。<br>
          <small class="muted">{esc(app['note'])}</small></li>
        <li><strong>Android なら Google Play の「定期購入」</strong>を開く。<br>
          出ていれば <strong>Google Play 経由</strong>
          （<a href="{esc(play['url'])}" rel="noopener" target="_blank">{esc(play['label'])}</a>・{esc(jp_date(play['date']))}確認）。<br>
          <small class="muted">{esc(play['note'])}</small></li>
        <li>どちらにも出ていなければ、<strong>サービスのサイト（アカウント設定）</strong>か、携帯電話会社などの<strong>パートナー決済</strong>で登録しています。
          下の表の「公式の解約ページ」へ。</li>
      </ol>
      <div class="routes">
        <div class="r"><b>{esc(WHERE_LABEL['site'])}</b>サービスの Web サイトやアプリのアカウント設定から解約する物。</div>
        <div class="r"><b>{esc(WHERE_LABEL['apple'])}</b>Apple Music・Apple TV+・iCloud+ など Apple のサービス。iPhone の「設定」→ 自分の名前 →「サブスクリプション」から。</div>
        <div class="r"><b>{esc(WHERE_LABEL['both'])}</b>表で <span class="warn">橙色</span>の物。サイトで登録した人はサイトから、アプリ内で登録した人は App Store / Google Play から。</div>
      </div>
    </div>

    {sections}

    <h2 id="yearly">年払いと解約後の注意</h2>
    <div class="card note">
      <ul>
        <li><strong>解約後いつまで使えるか</strong>はサービスで違います。多くは支払い済みの期間の終わりまで使えますが、U-NEXT の Web 登録のように解約した時点で止まる物もあります（表の「注意」）。</li>
        <li><strong>年払いの途中解約</strong>は、残りの期間分が返金されないか、期間の終わりまで請求が続くのが一般的です。DAZN の年間プラン（月々払い）は 12 か月分の請求が続きます。Adobe のように購入から 14 日以内なら全額返金という例外もあります。年払いにする前に、各サービスの解約ページで条件を確かめてください。</li>
        <li><strong>更新日の直前</strong>は間に合わないことがあります。ABEMA・ChatGPT・Claude は「更新の 24 時間前まで」、Nintendo Switch Online は「決済が有効期限の 48 時間前」。無料体験の数え方は <a href="./trials.html">無料体験の解約期限 早見表</a> に。</li>
        <li><strong>ストレージ系（iCloud+・Google One・Dropbox・Microsoft 365）</strong>は、無料枠を超えたまま解約すると同期やバックアップ、メールの送受信が止まります。先にデータを減らすか別の場所へ移してから。</li>
        <li><strong>「解約」と「退会（アカウント削除）」は別</strong>です。退会しただけでは課金が止まらないサービスがあります。</li>
      </ul>
    </div>

    <h2 id="about">このデータについて</h2>
    <div class="card note">
      <ul>
        <li>解約の窓口と公式ページは <strong>{esc(label)}時点</strong>の確認です。各行の「公式の解約ページ」の確認日は、そのページを開いて解約の説明があることを確かめた日です。各社の画面や手順は変わるため、必ずリンク先の公式ページを見てから手続きしてください。</li>
        <li>載せているサービスは、サブスク管理アプリ <a href="./">Subscope</a> の料金プリセットと同じ{n}サービスです。料金は <a href="./prices.html">サブスク料金一覧（税込）</a>、無料体験の長さは <a href="./trials.html">無料体験の解約期限 早見表</a> をご覧ください。毎月1日に価格を確認するときに、このページのリンク切れと確認日も見直します。</li>
        <li>リンク切れや誤りに気づかれた場合は <a href="mailto:{SUPPORT_MAIL}">{SUPPORT_MAIL}</a> までお知らせください。</li>
      </ul>
      <p class="muted" style="margin:6px 0 0;font-size:.85em;">最終更新: {today.isoformat()}</p>
    </div>

    <div class="cta">
      <h2>解約したいサブスク、次の請求日はいつですか？</h2>
      <p>Subscope は、サブスクと固定費を登録するだけで次の支払日と月額・年額の合計をひと目で見通せる iPhone アプリです。更新日の数日前にプッシュ通知でお知らせするので、「更新の 24 時間前まで」に間に合います。</p>
      <a class="btn" href="{APP_STORE_URL}">App Store でダウンロード</a>
    </div>
  </main>

  <footer>
    <a href="./">Subscope トップ</a><a href="./prices.html">サブスク料金一覧</a><a href="./trials.html">無料体験の解約期限</a><a href="./privacy.html">プライバシーポリシー</a><br>© 2026 Subscope
  </footer>
</body>
</html>
"""


def main() -> None:
    data = load()
    check(data)
    today = dt.date.today()
    OUT.write_text(render_page(data, today), encoding="utf-8", newline="\n")
    n = len(data["services"])
    print(f"wrote {OUT.name} ({n} services, checked {data['checked']})")
    if "--check-links" in sys.argv[1:]:
        ng = check_links(data)
        print(f"links: {'all OK' if ng == 0 else f'{ng} NG'}")
        if ng:
            sys.exit(1)


if __name__ == "__main__":
    main()
