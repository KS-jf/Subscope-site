#!/usr/bin/env python3
"""trials.json から trials.html（無料体験の解約期限 早見表）を生成する。

    python build_trials.py

trials.json を見直したら（毎月の価格チェックのたびに確認日を更新したら）これを回して、
生成物ごと commit / push する。依存ライブラリなし。sitemap.xml は build_prices.py が
trials.json の確認日を読んで書く（このスクリプトは sitemap を触らない）。

- 表に載せるのは「有料プランに無料体験（お試し期間）があるか・何日か」。価格は prices.html に任せる。
- 「いつまでに解約すれば課金されないか」の数え方は、サービスごとに違うので型（◯日間／◯か月）で説明し、
  ページ内の計算機（JS・通信なし）で登録日から逆算できるようにする。JS が無くても表と説明は読める。
"""
from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "trials.json"
OUT = ROOT / "trials.html"

SITE_URL = "https://ks-jf.github.io/Subscope-site/"
APP_STORE_URL = "https://apps.apple.com/jp/app/id6785280296"
SUPPORT_MAIL = "subscope.app@proton.me"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def load() -> dict:
    return json.loads(SRC.read_text(encoding="utf-8"))


def jp_date(iso: str) -> str:
    """'2026-11-01' → '2026年11月1日'。'2026-03' のような月までの物はそのまま年月に。"""
    parts = iso.split("-")
    if len(parts) == 3:
        return f"{int(parts[0])}年{int(parts[1])}月{int(parts[2])}日"
    if len(parts) == 2:
        return f"{int(parts[0])}年{int(parts[1])}月"
    return iso


def render_row(s: dict) -> str:
    kind = s["kind"]
    label = esc(s["label"])
    if kind == "none":
        trial = f"<span class=\"none\">{label}</span>"
    else:
        trial = f"<strong>{label}</strong>"
        if s.get("unverified"):
            trial += "<br><small class=\"warn\">公式ページでは未確認</small>"
    src = s["source"]
    badge = "公式" if src.get("kind") == "official" else "記事"
    source = (f"<a href=\"{esc(src['url'])}\" rel=\"noopener\" target=\"_blank\">{esc(src['label'])}</a>"
              f"<br><small class=\"muted\">{badge}・{esc(jp_date(src['date']))} 確認</small>")
    cls = "trial none-row" if kind == "none" else "trial"
    return (
        "<tr>"
        f"<th scope=\"row\">{esc(s['name'])}</th>"
        f"<td class=\"{cls}\" data-label=\"無料体験\">{trial}</td>"
        f"<td class=\"note\" data-label=\"条件・注意\">{esc(s['note'])}</td>"
        f"<td class=\"src\" data-label=\"出典\">{source}</td>"
        "</tr>"
    )


def render_group(name: str, items: list[dict], idx: int) -> str:
    rows = "".join(render_row(s) for s in items)
    n_yes = sum(1 for s in items if s["kind"] != "none")
    cap = f"{len(items)}サービスのうち無料体験があるのは {n_yes}" if items else ""
    return (
        f"<h2 id=\"g{idx}\">{esc(name)}</h2>"
        "<div class=\"tablewrap\"><table>"
        "<thead><tr><th scope=\"col\">サービス</th><th scope=\"col\">無料体験</th>"
        "<th scope=\"col\">条件・注意</th><th scope=\"col\">出典</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
        + (f"<p class=\"total\">{cap}</p>" if cap else "")
    )


def render_page(data: dict, today: dt.date) -> str:
    checked = data["checked"]
    services = data["services"]
    groups = [(g, [s for s in services if s["group"] == g]) for g in data["groups"]]
    groups = [(g, items) for g, items in groups if items]
    n = len(services)
    n_yes = sum(1 for s in services if s["kind"] != "none")
    n_no = n - n_yes
    yes_names = [s["name"] for s in services if s["kind"] != "none"]
    no_names = [s["name"] for s in services if s["kind"] == "none"]

    nav = " ／ ".join(f"<a href=\"#g{i}\">{esc(g)}</a>" for i, (g, _) in enumerate(groups))
    sections = "".join(render_group(g, items, i) for i, (g, items) in enumerate(groups))

    label = jp_date(checked)
    title = f"サブスクの無料体験はいつまでに解約すればいい？ 主要{n}サービスの無料期間と解約期限の数え方（{label[:label.index('月')+1]}確認）"
    description = (
        f"Spotify・Apple Music・U-NEXT・Amazon プライム・Kindle Unlimited など主要{n}サービスの無料体験の長さを一覧化。"
        "「30日間」「1か月」の数え方と、課金されない解約期限を登録日から逆算する計算機つき。"
        f"無料体験が無いサービス（Netflix・Hulu・Disney+ など）も明記。{label}確認。"
    )

    ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": description,
        "dateModified": today.isoformat(),
        "inLanguage": "ja",
        "mainEntityOfPage": SITE_URL + "trials.html",
        "author": {"@type": "Organization", "name": "Subscope"},
        "publisher": {"@type": "Organization", "name": "Subscope",
                      "logo": {"@type": "ImageObject", "url": SITE_URL + "icon.png"}},
    }
    faq = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": "「30日間無料」はいつまでに解約すれば課金されませんか？",
             "acceptedAnswer": {"@type": "Answer", "text": "登録した日を1日目として30日目が無料の最終日で、31日目に初回の請求が入るのが一般的です。例: 11月20日に登録すると12月19日まで無料、12月20日に課金。登録時刻から数えるサービスもあるので、最終日の前日までに解約すると安全です。"}},
            {"@type": "Question", "name": "「1か月無料」は何日間ですか？",
             "acceptedAnswer": {"@type": "Answer", "text": "翌月の同じ日付に請求が入り、その前日までが無料です。例: 11月20日に登録すると12月19日まで無料。1月31日に登録すると翌月に31日が無いため2月28日（または29日）に請求されます。"}},
            {"@type": "Question", "name": "App Store 経由のサブスクの無料トライアルは、いつまでに解約すればいいですか？",
             "acceptedAnswer": {"@type": "Answer", "text": "Apple のサポートページでは、更新を希望しない場合はトライアルが終了する24時間以上前に解約するよう案内しています。終了日の前日より前に解約しておくと確実です。"}},
            {"@type": "Question", "name": "無料体験が無いサブスクはどれですか？",
             "acceptedAnswer": {"@type": "Answer", "text": f"{label}時点で、{'・'.join(no_names)} には有料プランの無料体験がありません。"}},
        ],
    }

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}｜Subscope</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{SITE_URL}trials.html">
<meta property="og:type" content="article">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{SITE_URL}trials.html">
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
  table{{border-collapse:collapse;width:100%;min-width:560px;font-size:.93em;}}
  th,td{{padding:10px 12px;border-bottom:1px solid #eee;text-align:left;vertical-align:top;}}
  thead th{{background:#f6f8fb;font-weight:700;font-size:.88em;color:var(--muted);white-space:nowrap;}}
  tbody th{{font-weight:600;white-space:nowrap;}}
  tbody tr:last-child th,tbody tr:last-child td{{border-bottom:none;}}
  td.trial{{white-space:nowrap;}}
  td.note{{font-size:.9em;color:#3a3a44;}}
  td.src{{font-size:.85em;white-space:nowrap;}}
  .none{{color:var(--muted);}}
  .warn{{color:var(--warn);}}
  .muted{{color:var(--muted);}}
  p.total{{font-size:.9em;color:var(--muted);margin:8px 0 0 4px;}}
  .card{{background:#f6f8fb;border:1px solid #e7ebf1;border-radius:14px;padding:18px 20px;margin-top:14px;}}
  .card.calc{{border-color:#cfe6ef;background:#f3fbfd;}}
  .calc label{{display:block;font-size:.9em;color:var(--muted);margin-top:8px;}}
  .calc input,.calc select{{font:inherit;padding:8px 10px;border:1px solid #c9d2dd;border-radius:8px;background:#fff;max-width:100%;}}
  .calc .row{{display:flex;flex-wrap:wrap;gap:12px 18px;align-items:flex-end;}}
  .calc .row > div{{flex:1 1 180px;}}
  .calc .out{{margin-top:14px;padding:12px 14px;background:#fff;border:1px solid #e7ebf1;border-radius:10px;font-size:.95em;line-height:1.9;}}
  .calc .out b{{color:var(--blue);}}
  .calc .chk{{display:flex;align-items:center;gap:8px;font-size:.92em;margin-top:10px;}}
  .steps{{counter-reset:s;list-style:none;padding:0;margin:0;}}
  .steps li{{counter-increment:s;position:relative;padding:8px 0 8px 2.2em;border-bottom:1px solid #eee;}}
  .steps li:last-child{{border-bottom:none;}}
  .steps li::before{{content:counter(s);position:absolute;left:0;top:10px;width:1.6em;height:1.6em;border-radius:50%;
       background:var(--cyan);color:#fff;font-weight:700;font-size:.85em;display:flex;align-items:center;justify-content:center;}}
  .ex{{display:inline-block;background:#eef1f5;border-radius:6px;padding:2px 8px;font-size:.9em;margin:2px 0;}}
  .cta{{background:linear-gradient(135deg,var(--blue),var(--cyan));color:#fff;border-radius:16px;padding:24px 22px;margin-top:40px;text-align:center;}}
  .cta h2{{color:#fff;border:none;padding:0;margin:0 0 6px;font-size:1.15em;}}
  .cta p{{margin:0 0 16px;opacity:.95;}}
  .cta a.btn{{display:inline-block;background:#fff;color:var(--blue);text-decoration:none;font-weight:700;
       padding:12px 26px;border-radius:999px;box-shadow:0 6px 18px rgba(0,0,0,.18);}}
  .note ul{{padding-left:1.3em;margin:.4em 0;}}
  footer{{color:var(--muted);font-size:.85em;text-align:center;padding:28px 20px 60px;}}
  footer a{{margin:0 8px;}}
  code{{background:#eef1f5;padding:2px 6px;border-radius:4px;}}

  /* 狭い画面では 1サービス=1カードに積み替える（prices.html と同じ作り）。
     4列を 375px に収めると「条件・注意」が読めなくなるため。表のマークアップはそのまま。 */
  @media (max-width:640px){{
    .tablewrap{{overflow:visible;border:none;border-radius:0;}}
    table{{min-width:0;display:block;}}
    thead{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;}}
    tbody,tr,th,td{{display:block;}}
    tbody tr{{border:1px solid #e7ebf1;border-radius:12px;padding:10px 14px;margin-bottom:10px;}}
    tbody th{{font-size:1.02em;padding:0 0 6px;border-bottom:1px solid #eee;white-space:normal;}}
    tbody td{{padding:6px 0 0;border:none;display:flex;justify-content:space-between;
        align-items:baseline;gap:12px;text-align:right;}}
    tbody td::before{{content:attr(data-label);color:var(--muted);font-size:.85em;text-align:left;flex:none;}}
    tbody td.trial,tbody td.src{{white-space:normal;}}
    tbody td.note{{display:block;text-align:left;}}
    tbody td.note::before{{display:block;margin-bottom:2px;}}
    tbody tr:last-child th,tbody tr:last-child td{{border-bottom:none;}}
    p.total{{margin-top:0;}}
  }}
</style>
</head>
<body>
  <div class="hero"><div class="in">
    <div class="brand"><img src="./icon.png" alt=""><a href="./">Subscope</a></div>
    <h1>サブスクの無料体験、いつまでに解約すればいい？</h1>
    <p>主要{n}サービスの無料体験（お試し）の長さと、課金されない解約期限の数え方。{esc(label)}に確認。</p>
  </div></div>

  <main>
    <p>「初月無料」で登録して、解約を忘れて自動課金された経験のある人は半数にのぼります（オカネコ「サブスクに関する調査」330人・2025年12月実施、初月無料の解約忘れによる自動課金の経験 50.5%）。
    無料体験は <strong>「◯日間」なのか「◯か月」なのか</strong>で終わる日が変わり、App Store 経由なら<strong>終了の24時間以上前</strong>に解約が要ります。
    このページでは、日本で利用者の多い{n}サービスの無料体験の有無と長さを<strong>出典つき</strong>でまとめ、登録日から解約期限を逆算できるようにしました。
    無料体験があるのは {n_yes} サービス、無いのは {n_no} サービスです（{esc('・'.join(no_names))}）。</p>

    <p class="nav"><a href="#howto">解約期限の数え方</a> ／ <a href="#calc">計算機</a> ／ {nav} ／ <a href="#about">このデータについて</a></p>

    <h2 id="howto">解約期限の数え方（3つの型）</h2>
    <ol class="steps">
      <li><strong>「◯日間」型</strong>（30日間・31日間・7日間など）<br>
        登録した日を1日目と数え、◯日目が無料の最終日。翌日に初回の請求が入るのが一般的です。
        <span class="ex">例: 11月20日に登録・30日間 → 12月19日まで無料、12月20日に課金</span><br>
        <small class="muted">登録した「時刻」から 24時間×◯日で数えるサービスもあるため、最終日の前日までに解約すると安全です。</small></li>
      <li><strong>「◯か月」型</strong>（1か月無料・3か月無料など）<br>
        翌月（◯か月後）の同じ日付に請求が入り、その前日までが無料。
        <span class="ex">例: 11月20日に登録・1か月 → 12月19日まで無料、12月20日に課金</span><br>
        <small class="muted">月末に登録すると翌月に同じ日付が無いことがあります（1月31日に登録 → 2月28日か29日に課金）。</small></li>
      <li><strong>アプリストア経由</strong>（App Store・Google Play で登録した場合）<br>
        Apple は「トライアルが終了する24時間以上前に解約」と案内しています（<a href="https://support.apple.com/ja-jp/118428" rel="noopener" target="_blank">Apple サポート</a>）。
        無料トライアル中に解約すると、その時点で使えなくなるサービスが多い点にも注意（Spotify も同じ）。
        Google Play は定期購入を解約しても支払い済みの期間は使え、以後の請求は止まります（<a href="https://support.google.com/googleplay/answer/7018481?hl=ja" rel="noopener" target="_blank">Google Play ヘルプ</a>）。
        <span class="ex">安全策: 終了日の2日前までに解約</span></li>
    </ol>
    <p class="muted" style="font-size:.9em;">どの型でも「無料期間の最終日」ではなく<strong>その前日</strong>を自分の締め切りにしておくと、時刻やタイムゾーンの差で課金されることがありません。</p>

    <h2 id="calc">解約期限の計算機</h2>
    <div class="card calc">
      <div class="row">
        <div><label for="c-date">登録した日</label><input type="date" id="c-date"></div>
        <div><label for="c-kind">無料体験の長さ</label>
          <select id="c-kind">
            <option value="d7">7日間</option>
            <option value="d14">14日間</option>
            <option value="d30" selected>30日間</option>
            <option value="d31">31日間</option>
            <option value="m1">1か月</option>
            <option value="m2">2か月</option>
            <option value="m3">3か月</option>
            <option value="custom">日数を入力</option>
          </select></div>
        <div id="c-custom-wrap" style="display:none"><label for="c-custom">日数</label><input type="number" id="c-custom" min="1" max="400" value="60"></div>
      </div>
      <label class="chk"><input type="checkbox" id="c-store"> App Store / Google Play 経由で登録した（終了の24時間以上前に解約が要る）</label>
      <div class="out" id="c-out">登録した日を選ぶと、無料の最終日・課金が始まる日・解約の目安を出します（この計算は端末内だけで行い、どこにも送りません）。</div>
      <p class="muted" style="font-size:.85em;margin:10px 0 0;">※ 一般的な数え方にもとづく目安です。実際の請求日は各サービスの登録画面・確認メールに表示される日付を優先してください。</p>
    </div>

    {sections}

    <p class="muted" style="font-size:.9em;margin-top:18px;">{esc(data.get('no_trial_freemium',''))}</p>

    <h2 id="about">このデータについて</h2>
    <div class="card note">
      <ul>
        <li>無料体験の有無と長さは <strong>{esc(label)}時点</strong>の確認です。各行の「出典」に、公式ページで確認した物（<strong>公式</strong>）と、公式ページが読み取れず記事で確認した物（<strong>記事</strong>）を分けて書いています。キャンペーンで延びることや、終了することがあるため、登録前に必ず公式サイトでご確認ください。</li>
        <li>セール時の延長（プライムデー・ブラックフライデーの「3か月無料」「3か月99円」など）は、通常の長さの欄には入れず、条件・注意に書いています。</li>
        <li>通信キャリアやデバイス購入のセット特典（「◯か月無料」）は、サービス自体の無料体験ではないので表には入れていません。</li>
        <li>料金は <a href="./prices.html">サブスク料金一覧（税込）</a>、解約の窓口と公式の解約ページは <a href="./cancel.html">解約方法の早見表</a> をご覧ください。毎月1日に価格を確認するときに、このページの確認日も見直します。</li>
        <li>誤りに気づかれた場合は <a href="mailto:{SUPPORT_MAIL}">{SUPPORT_MAIL}</a> までお知らせください。</li>
      </ul>
      <p class="muted" style="margin:6px 0 0;font-size:.85em;">最終更新: {today.isoformat()}</p>
    </div>

    <div class="cta">
      <h2>無料体験の終了日、忘れずに解約できますか？</h2>
      <p>Subscope は、サブスクと固定費を登録するだけで次の支払日をひと目で見通せる iPhone アプリです。無料体験の終了日を「次の支払日」として登録しておけば、数日前にプッシュ通知でお知らせします。</p>
      <a class="btn" href="{APP_STORE_URL}">App Store でダウンロード</a>
    </div>
  </main>

  <footer>
    <a href="./">Subscope トップ</a><a href="./prices.html">サブスク料金一覧</a><a href="./cancel.html">解約方法</a><a href="./privacy.html">プライバシーポリシー</a><br>© 2026 Subscope
  </footer>

  <script>
  // 解約期限の計算機。入力はこの端末の中だけで使い、どこにも送らない。
  (function () {{
    var $ = function (id) {{ return document.getElementById(id); }};
    var dateEl = $('c-date'), kindEl = $('c-kind'), customWrap = $('c-custom-wrap'), customEl = $('c-custom'), storeEl = $('c-store'), out = $('c-out');
    if (!dateEl || !kindEl || !out) return;
    var W = ['日', '月', '火', '水', '木', '金', '土'];
    function fmt(d) {{ return d.getFullYear() + '年' + (d.getMonth() + 1) + '月' + d.getDate() + '日（' + W[d.getDay()] + '）'; }}
    function addDays(d, n) {{ var r = new Date(d.getTime()); r.setDate(r.getDate() + n); return r; }}
    function addMonths(d, n) {{
      // 翌月に同じ日付が無いときは、その月の末日に寄せる（1/31 + 1か月 → 2/28 か 2/29）
      var y = d.getFullYear(), m = d.getMonth() + n, day = d.getDate();
      var last = new Date(y, m + 1, 0).getDate();
      return new Date(y, m, Math.min(day, last));
    }}
    function parse(v) {{ var p = (v || '').split('-'); if (p.length !== 3) return null; var d = new Date(+p[0], +p[1] - 1, +p[2]); return isNaN(d.getTime()) ? null : d; }}
    function update() {{
      customWrap.style.display = kindEl.value === 'custom' ? '' : 'none';
      var d0 = parse(dateEl.value);
      if (!d0) {{ out.textContent = '登録した日を選ぶと、無料の最終日・課金が始まる日・解約の目安を出します（この計算は端末内だけで行い、どこにも送りません）。'; return; }}
      var k = kindEl.value, bill, how;
      if (k === 'custom') {{ var n = Math.max(1, Math.min(400, parseInt(customEl.value, 10) || 1)); bill = addDays(d0, n); how = n + '日間'; }}
      else if (k.charAt(0) === 'd') {{ var nd = parseInt(k.slice(1), 10); bill = addDays(d0, nd); how = nd + '日間'; }}
      else {{ var nm = parseInt(k.slice(1), 10); bill = addMonths(d0, nm); how = nm + 'か月'; }}
      var last = addDays(bill, -1);
      var safe = addDays(last, storeEl.checked ? -1 : 0);   // ストア経由は「終了の24時間以上前」= 最終日の前日より前に
      var deadline = addDays(safe, -1);                      // 時刻の差で課金されないよう、さらに前日を目安に
      out.innerHTML =
        '登録日 <b>' + fmt(d0) + '</b>・' + how + 'の場合<br>' +
        '無料で使える最終日: <b>' + fmt(last) + '</b><br>' +
        '課金が始まる日: <b>' + fmt(bill) + '</b><br>' +
        '解約の目安（この日までに）: <b>' + fmt(deadline) + '</b>' +
        (storeEl.checked ? '<br><small>App Store / Google Play 経由は終了の24時間以上前に解約が要るため、1日早めています。</small>' : '') +
        '<br><small>月末に登録した場合や、登録時刻から数えるサービスでは前後することがあります。登録画面の日付を優先してください。</small>';
    }}
    [dateEl, kindEl, customEl, storeEl].forEach(function (el) {{ if (el) {{ el.addEventListener('change', update); el.addEventListener('input', update); }} }});
    // 既定値: 今日
    try {{ var t = new Date(); dateEl.value = t.getFullYear() + '-' + String(t.getMonth() + 1).padStart(2, '0') + '-' + String(t.getDate()).padStart(2, '0'); }} catch (e) {{}}
    update();
  }})();
  </script>
</body>
</html>
"""


def main() -> None:
    data = load()
    today = dt.date.today()
    page = render_page(data, today)
    OUT.write_text(page, encoding="utf-8", newline="\n")
    n = len(data["services"])
    print(f"wrote {OUT.name} ({n} services, checked {data['checked']})")


if __name__ == "__main__":
    main()
