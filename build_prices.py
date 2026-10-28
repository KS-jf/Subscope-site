#!/usr/bin/env python3
"""presets.json から prices.html（サブスク料金一覧ページ）と sitemap.xml を生成する。

    python build_prices.py

presets.json を更新したら（月次価格チェックのたびに）これを回して、
生成物ごと commit / push する。依存ライブラリなし。

- 「固定費」カテゴリ（家賃・電気代など）は料金ではなく入力の目安なので載せない。
- 金額は presets.json の方針どおり税込。USD 建ては公式の税抜価格 +10% が入っている。
- 年払いプランがあるサービスは「年払いにすると年いくら安いか」を算出する。
- 値上げの記録は PRICE_HIKES（presets.json の金額を上げた時に1行足す）。年ごとの表にして載せる。
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

# 値上げの記録（施行日の新しい順）。月次の価格チェックで presets.json の金額を上げたら、ここへ1行足す。
# - date: 新規加入者に新価格が適用される日（既存会員の切り替え日は note に）
# - monthly / yearly: (旧, 新)。旧は更新前の presets.json（git 履歴）か出典の旧価格。出典で確かめられた物だけ載せる
# - source: (表示名と記事の日付, URL)。公式発表か、それを伝えた報道
# - 税込に揃えただけの変更（ChatGPT / Claude の US$20→22・2026-09）は値上げではないので載せない
# 新価格が現在の presets.json と食い違うと build 時に警告する（載せ忘れ・直し忘れの検知）。
PRICE_HIKES = [
    {"name": "Hulu", "date": "2026-10-01", "monthly": (1026, 1320),
     "note": "既存会員は 10/1 以降の最初の請求日から",
     "source": ("Selectra（2026-10-19 更新）", "https://selectra.jp/streaming/news/hulu-price-increase-2026")},
    {"name": "Apple Music", "date": "2026-07-18", "monthly": (1080, 1180), "yearly": (10800, 11800),
     "note": "個人プラン",
     "source": ("gori.me 2026-07-18", "https://gori.me/?p=168213")},
    {"name": "Apple TV+", "date": "2026-07-18", "monthly": (900, 1200),
     "source": ("gori.me 2026-07-18", "https://gori.me/?p=168213")},
    {"name": "iCloud+", "date": "2026-07-18", "monthly": (150, 180),
     "note": "50GB プラン",
     "source": ("gori.me 2026-07-18", "https://gori.me/?p=168213")},
    {"name": "Disney+", "date": "2026-03-25", "monthly": (1140, 1250), "yearly": (11400, 12500),
     "note": "スタンダード。既存会員は 5/1 以降の請求分から",
     "source": ("AV Watch 2026-03-09", "https://av.watch.impress.co.jp/docs/news/2091781.html")},
    {"name": "Spotify", "date": "2025-08-04", "monthly": (980, 1080),
     "note": "Standard。既存会員は 9 月の請求日から",
     "source": ("アプリオ 2025-08-05", "https://appllio.com/news/2025-08-05-66296-spotify-premium-price-revision")},
    {"name": "Adobe Creative Cloud", "date": "2025-08-01", "monthly": (7780, 9080),
     "note": "年間プラン月々払い。コンプリートプランが Creative Cloud Pro に改称",
     "source": ("デジカメ Watch 2025-07-14", "https://dc.watch.impress.co.jp/docs/news/saleitem/2031006.html")},
    {"name": "Microsoft 365", "date": "2025-01-16", "monthly": (1490, 2130), "yearly": (14900, 21300),
     "note": "Personal。Copilot の追加に合わせた改定",
     "source": ("Impress Watch 2025-01-17", "https://www.watch.impress.co.jp/docs/news/1654780.html")},
]


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


def check_hikes(presets: list[dict]) -> None:
    """PRICE_HIKES の新価格が今の presets.json と一致するか。ずれていれば警告して続ける。"""
    by_name = {p["name"]: p for p in presets}
    for h in PRICE_HIKES:
        p = by_name.get(h["name"])
        if not p:
            print(f"  ! 値上げ一覧: {h['name']} が presets.json に無い")
            continue
        for cycle in ("monthly", "yearly"):
            if cycle not in h:
                continue
            plan = plan_of(p, cycle)
            if not plan or plan["amount"] != h[cycle][1]:
                print(f"  ! 値上げ一覧: {h['name']} の{CYCLE_LABEL[cycle]}額 {h[cycle][1]} が presets.json"
                      f"（{plan['amount'] if plan else '無し'}）と違う")


def render_hike_table(items: list[dict]) -> str:
    rows = []
    for h in items:
        om, nm = h["monthly"]
        up = nm - om
        monthly = f"{money(om, 'JPY')} → <strong>{money(nm, 'JPY')}</strong>"
        rise = f"+{money(up, 'JPY')}<br><small class=\"muted\">約{up / om * 100:.0f}%</small>"
        if "yearly" in h:
            oy, ny = h["yearly"]
            yearly = f"{money(oy, 'JPY')} → <strong>{money(ny, 'JPY')}</strong>"
        else:
            yearly = "—"
        y, m, d = h["date"].split("-")
        date = f"{int(m)}/{int(d)}"
        if h.get("note"):
            date += f"<br><small class=\"muted\">{esc(h['note'])}</small>"
        src_label, src_url = h["source"]
        src = f"<a href=\"{esc(src_url)}\" rel=\"noopener\" target=\"_blank\">{esc(src_label)}</a>"

        def cell(value: str, label: str, num: bool = True) -> str:
            cls = ("num " if num else "") + ("empty" if value == "—" else "")
            return f"<td class=\"{cls.strip()}\" data-label=\"{label}\">{value}</td>"

        rows.append(
            "<tr>"
            f"<th scope=\"row\">{esc(h['name'])}</th>"
            + cell(date, "施行日", num=False)
            + cell(monthly, "月額（旧 → 新）")
            + cell(rise, "上げ幅")
            + cell(yearly, "年額（旧 → 新）")
            + cell(src, "出典", num=False)
            + "</tr>"
        )
    return (
        "<div class=\"tablewrap\"><table class=\"hikes\">"
        "<thead><tr><th scope=\"col\">サービス</th><th scope=\"col\">施行日</th>"
        "<th scope=\"col\">月額（旧 → 新）</th><th scope=\"col\">上げ幅</th>"
        "<th scope=\"col\">年額（旧 → 新）</th><th scope=\"col\">出典</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_price_hikes(today: dt.date) -> str:
    """値上げの記録を年ごとの表にする。今年（記録が無ければ最新の年）を h2、それより前の年を h3 で続ける。"""
    if not PRICE_HIKES:
        return ""
    hikes = sorted(PRICE_HIKES, key=lambda h: h["date"], reverse=True)
    years = sorted({int(h["date"][:4]) for h in hikes}, reverse=True)
    head_year = today.year if today.year in years else years[0]
    parts = [
        f"<h2 id=\"hikes\">{head_year}年の値上げ一覧</h2>",
        "<p>このページに載せているサービスのうち、料金が上がったものを施行日の新しい順に並べています。"
        "「施行日」は新規加入者に新料金が適用される日で、すでに契約している人は次回以降の請求日から切り替わるのが一般的です"
        "（切り替え日が公表されているものは施行日の下に書いています）。"
        "月額は個人向けの標準プラン・税込です。</p>",
    ]
    for y in years:
        items = [h for h in hikes if int(h["date"][:4]) == y]
        if y != head_year:
            parts.append(f"<h3>{y}年の値上げ</h3>")
        parts.append(render_hike_table(items))
        total = sum(h["monthly"][1] - h["monthly"][0] for h in items)
        if len(items) >= 2:
            parts.append(
                f"<p class=\"total\">{len(items)}サービスをすべて契約していると、"
                f"{y}年の値上げで月 {total:,}円（年 {total * 12:,}円）の負担増</p>")
    parts.append(
        "<p class=\"muted\" style=\"font-size:.9em;\">"
        "旧価格は値上げ前にこのページ（アプリの料金プリセット）に載せていた金額、新価格は現在の表と同じです。"
        "施行日と価格は出典の記事で確認しています。契約中のサービスが値上げされると、Subscope は登録した金額との差を"
        "「値上げ検知」として知らせます。</p>")
    return "".join(parts)


def render_page(version: str, presets: list[dict], today: dt.date,
                rate: float, rate_date: str) -> str:
    label = version_label(version)
    groups = group_presets(presets)
    n = len(presets)

    nav = " ／ ".join(f"<a href=\"#g{i}\">{esc(g)}</a>" for i, (g, _) in enumerate(groups))
    hikes = render_price_hikes(today)

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
        "月額・年額・年払いにしたときの割引額、値上げしたサービスの新旧価格も掲載。毎月更新。"
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
  table.hikes{{min-width:700px;}}
  table.hikes td.num{{white-space:normal;}}
  h3{{font-size:1.05em;margin:1.6em 0 .5em;color:var(--muted);}}
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

    <p class="nav">{nav} ／ <a href="#yearly">年払いの割引ランキング</a>{' ／ <a href="#hikes">値上げ一覧</a>' if hikes else ''}</p>

    {''.join(sections)}

    {render_savings_ranking(presets, rate, rate_date)}

    {hikes}

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
    check_hikes(presets)
    rate, rate_date = usd_jpy()
    OUT.write_text(render_page(version, presets, today, rate, rate_date),
                   encoding="utf-8", newline="\n")
    SITEMAP.write_text(render_sitemap(today), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.name} ({len(presets)} services, data {version}, "
          f"USD/JPY {rate:.2f}) and {SITEMAP.name}")


if __name__ == "__main__":
    main()
