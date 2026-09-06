#!/usr/bin/env python3
"""presets.json から prices.html（サブスク料金一覧ページ）と sitemap.xml を生成する。

    python build_prices.py

presets.json を更新したら（月次価格チェックのたびに）これを回して、
生成物ごと commit / push する。依存ライブラリなし。

- 「固定費」カテゴリ（家賃・電気代など）は料金ではなく入力の目安なので載せない。
- 金額は presets.json の方針どおり税込。USD 建ては公式の税抜価格 +10% が入っている。
- 年払いプランがあるサービスは「年払いにすると年いくら安いか」を算出する。
"""
from __future__ import annotations

import datetime as dt
import html
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "presets.json"
OUT = ROOT / "prices.html"
SITEMAP = ROOT / "sitemap.xml"

SITE_URL = "https://ks-jf.github.io/Subscope-site/"
# 対円レートの取得元。アプリ本体（ExchangeRateService）と同じ・キー不要。
FX_API = "https://open.er-api.com/v6/latest/USD"
FX_CACHE = Path(__file__).resolve().parent / "fx-rate.json"
FALLBACK_USD_JPY = 156.0
APP_STORE_URL = "https://apps.apple.com/jp/app/id6785280296"
SUPPORT_MAIL = "subscope.app@proton.me"

# 表示用のグループ分け（presets.json の category より細かい）。
# 未登録のサービスは category にフォールバックする。
GROUP_OF = {
    "動画配信": [
        "Netflix", "Apple TV+", "YouTube Premium", "Disney+", "Hulu", "U-NEXT",
        "ABEMAプレミアム", "dアニメストア", "DAZN",
    ],
    "音楽": ["Spotify", "Apple Music", "Amazon Music Unlimited"],
    "電子書籍": ["Kindle Unlimited"],
    "ゲーム": ["Nintendo Switch Online", "PlayStation Plus"],
    "AI アシスタント": ["ChatGPT Plus", "Claude Pro", "Claude Max x5", "Claude Max x20"],
    "仕事・クリエイティブ": ["Adobe Creative Cloud", "Microsoft 365", "Dropbox"],
    "ストレージ・ショッピング": ["iCloud+", "Google One", "Amazon Prime"],
}
GROUP_ORDER = list(GROUP_OF)
EXCLUDED_CATEGORIES = {"固定費"}

CYCLE_LABEL = {"weekly": "週", "monthly": "月", "yearly": "年"}


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def money(amount: float, currency: str) -> str:
    if currency == "JPY":
        return f"{int(round(amount)):,}円"
    if currency == "USD":
        v = f"{amount:,.2f}".rstrip("0").rstrip(".")
        return f"US${v}"
    return f"{amount:,} {currency}"


def usd_jpy() -> tuple[float, str]:
    """(1米ドルあたりの円, 取得日)。オフラインなら前回値、それも無ければ概算シード。

    ランキングを円で一列に並べるためだけに使う。ページには取得日を明記して
    「更新時点のレート」であることを示す（為替で順位は前後する）。
    """
    try:
        with urllib.request.urlopen(FX_API, timeout=15) as r:
            rate = float(json.load(r)["rates"]["JPY"])
        date = dt.date.today().isoformat()
        FX_CACHE.write_text(
            json.dumps({"usd_jpy": rate, "date": date}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8", newline="\n")
        return rate, date
    except Exception as e:  # ネットワーク断でもページは生成できるようにする
        print(f"  ! 為替の取得に失敗（{e}）")
        if FX_CACHE.exists():
            d = json.loads(FX_CACHE.read_text(encoding="utf-8"))
            print(f"  → 前回値 {d['usd_jpy']}（{d['date']}）を使う")
            return float(d["usd_jpy"]), d["date"]
        print(f"  → 概算シード {FALLBACK_USD_JPY} を使う")
        return FALLBACK_USD_JPY, ""


def load() -> tuple[str, list[dict]]:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    presets = [p for p in data["presets"] if p.get("category") not in EXCLUDED_CATEGORIES]
    return data["version"], presets


def group_presets(presets: list[dict]) -> list[tuple[str, list[dict]]]:
    by_name = {p["name"]: p for p in presets}
    placed: set[str] = set()
    groups: list[tuple[str, list[dict]]] = []
    for g in GROUP_ORDER:
        items = [by_name[n] for n in GROUP_OF[g] if n in by_name]
        placed.update(p["name"] for p in items)
        if items:
            groups.append((g, items))
    # フォールバック: グループ未登録のサービスは category ごとにまとめて末尾へ
    rest: dict[str, list[dict]] = {}
    for p in presets:
        if p["name"] not in placed:
            rest.setdefault(p["category"], []).append(p)
    for cat, items in rest.items():
        groups.append((cat, items))
    return groups


def plan_of(p: dict, cycle: str) -> dict | None:
    return next((x for x in p["plans"] if x["cycle"] == cycle), None)


def yearly_saving(p: dict) -> tuple[float, float, str] | None:
    """年払いにしたときの年間の差額・割引率・通貨。月額と年額が同じ通貨で揃うときだけ。"""
    m, y = plan_of(p, "monthly"), plan_of(p, "yearly")
    if not m or not y or m["currency"] != y["currency"]:
        return None
    diff = m["amount"] * 12 - y["amount"]
    if diff <= 0:
        return None
    return diff, diff / (m["amount"] * 12), m["currency"]


def version_label(version: str) -> str:
    y, m = version.split("-")[:2]
    return f"{int(y)}年{int(m)}月"


def render_table(items: list[dict]) -> str:
    rows = []
    for p in items:
        m, y = plan_of(p, "monthly"), plan_of(p, "yearly")
        w = plan_of(p, "weekly")
        monthly = money(m["amount"], m["currency"]) if m else (
            f"{money(w['amount'], w['currency'])}／週" if w else "—")
        yearly = money(y["amount"], y["currency"]) if y else "—"
        if y and not m:
            yearly += f"<br><small class=\"muted\">月あたり {money(y['amount'] / 12, y['currency'])}</small>"
        sv = yearly_saving(p)
        saving = (f"年 {money(sv[0], sv[2])}お得"
                  f"<br><small class=\"muted\">約{sv[1]*100:.0f}%引き</small>") if sv else "—"
        # 値が無いセルはカード表示（狭い画面）では消す。"—" だけの行が並ぶと読みにくいため。
        def cell(value: str, label: str) -> str:
            cls = "num empty" if value == "—" else "num"
            return f"<td class=\"{cls}\" data-label=\"{label}\">{value}</td>"

        rows.append(
            "<tr>"
            f"<th scope=\"row\">{esc(p['name'])}</th>"
            + cell(monthly, "月額")
            + cell(yearly, "年額")
            + cell(saving, "年払いの割引")
            + "</tr>"
        )
    return (
        "<div class=\"tablewrap\"><table>"
        "<thead><tr><th scope=\"col\">サービス</th><th scope=\"col\">月額</th>"
        "<th scope=\"col\">年額</th><th scope=\"col\">年払いの割引</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def group_total(items: list[dict]) -> str | None:
    """グループ内の JPY 月額プランの合計（USD 建てや月額なしは除く）。"""
    jpy = [plan_of(p, "monthly") for p in items]
    jpy = [x for x in jpy if x and x["currency"] == "JPY"]
    if len(jpy) < 2:
        return None
    total = int(round(sum(x["amount"] for x in jpy)))
    return f"{len(jpy)}サービスすべて契約すると月 {total:,}円（年 {total*12:,}円）"


def render_savings_ranking(presets: list[dict], rate: float, rate_date: str) -> str:
    """差額の大きい順に並べる。米ドル建ては円に換算して同じ列に載せる。

    為替は生成時点の値で固定される（ページに取得日を明記する）。順位は為替でも動く。
    """
    ranked = []
    for p in presets:
        sv = yearly_saving(p)
        if not sv:
            continue
        diff, ratio, cur = sv
        jpy = diff if cur == "JPY" else diff * rate
        label = f"年 {money(diff, cur)}お得（約{ratio*100:.0f}%）"
        if cur != "JPY":
            label += f"<br><small class=\"muted\">約 {int(round(jpy)):,}円</small>"
        ranked.append((jpy, label, p["name"]))
    ranked.sort(key=lambda x: -x[0])
    if not ranked:
        return ""
    lis = "".join(
        f"<li><span class=\"name\">{esc(n)}</span><span class=\"val\">{label}</span></li>"
        for _, label, n in ranked
    )
    fx = (f"米ドル建てのサービスは 1米ドル＝{rate:.1f}円"
          f"{f'（{rate_date} 時点）' if rate_date else ''}で円に換算して並べています。"
          "為替は日々動くので、円換算の額と順位はこのページを更新した時点のものです。")
    return (
        "<h2 id=\"yearly\">年払いにすると、いくら安くなるか</h2>"
        "<p>月額プランと年額プランの両方があるサービスを、年払いにしたときの差額が大きい順に並べています。"
        "1年以上続ける確信があるサービスは年払いに切り替える余地があります。"
        "逆に、いつ解約するか分からないサービスは月払いのままの方が損をしにくいです。</p>"
        f"<p class=\"muted\" style=\"font-size:.9em;\">{fx}</p>"
        f"<ol class=\"rank\">{lis}</ol>"
    )


def render_page(version: str, presets: list[dict], today: dt.date,
                rate: float, rate_date: str) -> str:
    label = version_label(version)
    groups = group_presets(presets)
    n = len(presets)

    nav = " ／ ".join(f"<a href=\"#g{i}\">{esc(g)}</a>" for i, (g, _) in enumerate(groups))

    sections = []
    for i, (g, items) in enumerate(groups):
        total = group_total(items)
        sections.append(
            f"<h2 id=\"g{i}\">{esc(g)}</h2>"
            + render_table(items)
            + (f"<p class=\"total\">{total}</p>" if total else "")
        )

    title = f"サブスク料金一覧（{label}・税込）主要{n}サービスの月額・年額と年払い割引"
    description = (
        f"Netflix・Spotify・YouTube Premium・ChatGPT など主要{n}サービスの料金を{label}時点の税込価格で一覧化。"
        "月額・年額・年払いにしたときの割引額も掲載。毎月更新。"
    )

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}｜Subscope</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{SITE_URL}prices.html">
<meta property="og:type" content="article">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{SITE_URL}prices.html">
<meta property="og:image" content="{SITE_URL}icon.png">
<meta property="og:site_name" content="Subscope">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">
{json.dumps({
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": title,
    "description": description,
    "dateModified": today.isoformat(),
    "inLanguage": "ja",
    "mainEntityOfPage": SITE_URL + "prices.html",
    "author": {"@type": "Organization", "name": "Subscope"},
    "publisher": {"@type": "Organization", "name": "Subscope", "logo": {"@type": "ImageObject", "url": SITE_URL + "icon.png"}},
}, ensure_ascii=False, indent=1)}
</script>
<style>
  :root{{ --blue:#0d47c9; --cyan:#2bd2e4; --ink:#1c1c22; --muted:#6a6c75; }}
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
  p.nav{{font-size:.92em;line-height:2.2;}}
  a{{color:var(--blue);}}
  .tablewrap{{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid #e7ebf1;border-radius:12px;}}
  table{{border-collapse:collapse;width:100%;min-width:500px;font-size:.95em;}}
  th,td{{padding:10px 12px;border-bottom:1px solid #eee;text-align:left;vertical-align:top;}}
  thead th{{background:#f6f8fb;font-weight:700;font-size:.88em;color:var(--muted);white-space:nowrap;}}
  tbody th{{font-weight:600;white-space:nowrap;}}
  tbody tr:last-child th,tbody tr:last-child td{{border-bottom:none;}}
  td.num{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums;}}
  thead th:not(:first-child){{text-align:right;}}
  .muted{{color:var(--muted);}}
  p.total{{font-size:.9em;color:var(--muted);margin:8px 0 0 4px;}}
  ol.rank{{list-style:none;counter-reset:r;padding:0;margin:0;border:1px solid #e7ebf1;border-radius:12px;overflow:hidden;}}
  ol.rank li{{counter-increment:r;display:flex;justify-content:space-between;gap:12px;padding:10px 14px;border-bottom:1px solid #eee;}}
  ol.rank li:last-child{{border-bottom:none;}}
  ol.rank li::before{{content:counter(r);color:var(--cyan);font-weight:700;min-width:1.6em;}}
  ol.rank .name{{flex:1;font-weight:600;}}
  ol.rank .val{{white-space:nowrap;font-variant-numeric:tabular-nums;}}
  .card{{background:#f6f8fb;border:1px solid #e7ebf1;border-radius:14px;padding:18px 20px;margin-top:14px;}}
  .cta{{background:linear-gradient(135deg,var(--blue),var(--cyan));color:#fff;border-radius:16px;padding:24px 22px;margin-top:40px;text-align:center;}}
  .cta h2{{color:#fff;border:none;padding:0;margin:0 0 6px;font-size:1.15em;}}
  .cta p{{margin:0 0 16px;opacity:.95;}}
  .cta a.btn{{display:inline-block;background:#fff;color:var(--blue);text-decoration:none;font-weight:700;
       padding:12px 26px;border-radius:999px;box-shadow:0 6px 18px rgba(0,0,0,.18);}}
  .note ul{{padding-left:1.3em;margin:.4em 0;}}
  footer{{color:var(--muted);font-size:.85em;text-align:center;padding:28px 20px 60px;}}
  footer a{{margin:0 8px;}}
  code{{background:#eef1f5;padding:2px 6px;border-radius:4px;}}

  /* 狭い画面では横スクロールさせず、1サービス=1カードに積み替える。
     4列を 375px に収めると「年払いの割引」が画面外に出てしまい、
     このページで一番読ませたい列が読まれないため。表のマークアップは
     そのまま（読み上げ・検索エンジン向けの構造を壊さない）。 */
  @media (max-width:600px){{
    .tablewrap{{overflow:visible;border:none;border-radius:0;}}
    table{{min-width:0;display:block;}}
    thead{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;}}
    tbody,tr,th,td{{display:block;}}
    tbody tr{{border:1px solid #e7ebf1;border-radius:12px;padding:10px 14px;margin-bottom:10px;}}
    tbody th{{font-size:1.02em;padding:0 0 6px;border-bottom:1px solid #eee;white-space:normal;}}
    tbody td{{padding:6px 0 0;border:none;display:flex;justify-content:space-between;
        align-items:baseline;gap:12px;text-align:right;}}
    tbody td::before{{content:attr(data-label);color:var(--muted);font-size:.85em;
        text-align:left;flex:none;}}
    tbody td.num{{white-space:normal;}}
    tbody td.empty{{display:none;}}
    tbody tr:last-child th,tbody tr:last-child td{{border-bottom:none;}}
    p.total{{margin-top:0;}}
    ol.rank li{{padding:10px 12px;flex-wrap:wrap;row-gap:2px;}}
    ol.rank .name{{flex:1 1 auto;}}
    ol.rank .val{{flex:1 0 100%;white-space:normal;text-align:right;font-size:.95em;}}
  }}
</style>
</head>
<body>
  <div class="hero"><div class="in">
    <div class="brand"><img src="./icon.png" alt=""><a href="./">Subscope</a></div>
    <h1>サブスク料金一覧（{esc(label)}・税込）</h1>
    <p>主要{n}サービスの月額・年額と、年払いにしたときの割引額。毎月1日に価格を確認して更新しています。</p>
  </div></div>

  <main>
    <p>動画配信・音楽・AI アシスタント・仕事用ツールまで、日本で利用者の多いサブスクリプションの現行料金をまとめました。
    金額はすべて<strong>税込</strong>で、個人向けの標準プランを掲載しています。
    このデータは、サブスク管理アプリ <a href="./">Subscope</a> がサービス登録時に自動入力する料金プリセットと同じものです。</p>

    <p class="nav">{nav} ／ <a href="#yearly">年払いの割引ランキング</a></p>

    {''.join(sections)}

    {render_savings_ranking(presets, rate, rate_date)}

    <h2 id="about">このデータについて</h2>
    <div class="card note">
      <ul>
        <li>価格は <strong>{esc(label)}時点</strong>の公式サイトの表示にもとづく目安です。プラン改定やキャンペーンで変わることがあるため、契約前に必ず公式サイトでご確認ください。</li>
        <li>円建ての金額は税込表示です。US ドル建て（ChatGPT・Claude など）は公式の税抜価格に消費税 10% を加えた金額を載せています。実際の円での請求額は、支払い時点の為替レートとカード会社の手数料で変わります。</li>
        <li>複数プランがあるサービスは、個人向けの標準プラン（広告なし・1人用など）を代表値にしています。</li>
        <li>「年払いの割引」は「月額 × 12 − 年額」で計算しています。米ドル建てのサービスはドルのまま表示し、割引ランキングでのみ円に換算しています（換算レートは上記のとおり更新時点の値）。</li>
        <li>誤りに気づかれた場合は <a href="mailto:{SUPPORT_MAIL}">{SUPPORT_MAIL}</a> までお知らせください。</li>
      </ul>
      <p class="muted" style="margin:6px 0 0;font-size:.85em;">最終更新: {today.isoformat()}</p>
    </div>

    <div class="cta">
      <h2>契約中のサブスク、合計でいくら払っているか把握できていますか？</h2>
      <p>Subscope は、サブスクと固定費を登録するだけで月額・年額の合計と次の支払日をひと目で見通せる iPhone アプリです。上の料金は登録時に自動で入ります。</p>
      <a class="btn" href="{APP_STORE_URL}">App Store でダウンロード</a>
    </div>
  </main>

  <footer>
    <a href="./">Subscope トップ</a><a href="./privacy.html">プライバシーポリシー</a><br>© 2026 Subscope
  </footer>
</body>
</html>
"""


def render_sitemap(today: dt.date) -> str:
    urls = [
        ("", None),
        ("prices.html", today.isoformat()),
        ("privacy.html", None),
    ]
    body = ""
    for path, lastmod in urls:
        body += f"  <url><loc>{SITE_URL}{path}</loc>"
        if lastmod:
            body += f"<lastmod>{lastmod}</lastmod>"
        body += "</url>\n"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}</urlset>\n"
    )


def main() -> None:
    version, presets = load()
    today = dt.date.today()
    rate, rate_date = usd_jpy()
    OUT.write_text(render_page(version, presets, today, rate, rate_date),
                   encoding="utf-8", newline="\n")
    SITEMAP.write_text(render_sitemap(today), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.name} ({len(presets)} services, data {version}, "
          f"USD/JPY {rate:.2f}) and {SITEMAP.name}")


if __name__ == "__main__":
    main()
