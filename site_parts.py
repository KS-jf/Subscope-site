#!/usr/bin/env python3
"""全ページ共通の部品（いまは「同じ作者のほかの作品」のカードだけ）。

- 生成するページ（prices / trials / cancel）は、各 build_*.py がここの
  OTHER_APPS_CSS と other_apps_html() をテンプレートに差し込む。
- 手書きのページ（index.html / diagnosis.html）は、目印のコメントの間を
  このファイルが書き換える:  python site_parts.py
    スタイル:  /* other-apps-css:start */ 〜 /* other-apps-css:end */
    本体:      <!-- other-apps:start --> 〜 <!-- other-apps:end -->
  目印が無いページには何もしない（エラーにする）。

作品を足す・一言を直す時は OTHER_APPS だけを直し、次の 4 つを回す:
    python site_parts.py
    python build_prices.py
    python build_trials.py
    python build_cancel.py
    python tests/other_apps_check.py        （--check-links でリンク切れも見る）

リンクは App Store のキャンペーンリンク（pt＝プロバイダ ID・ct＝入口の名前）。
ASC のアナリティクスで「このサイトのカードから来た」を見分ける（inbox ss-261112-1・x-261110-1）。
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

CAMPAIGN_PT = "129017883"
OTHER_APPS_CT = "cross-subscope-site"

# icon は 192px の PNG（apps/ に置く。元は各アプリの AppIcon 1024px）。
# ともしび島は配信後にここへ 1 行足す。
OTHER_APPS = [
    {
        "id": "6778652330",
        "name": "大農場ワールド",
        "name_en": "Harvest World: Idle Farm",
        "line": "歩いて集める、放置で育つ農場ゲーム。",
        "line_en": "A cozy idle farm that grows while you are away.",
        "icon": "apps/harvest-world.png",
    },
    {
        "id": "6813067839",
        "name": "祭りノックダウン",
        "name_en": "Matsuri Knockdown",
        "line": "縁日の射的で、景品をぜんぶ倒す物理パズル。",
        "line_en": "Knock every prize off the shelf at a Japanese festival stall.",
        "icon": "apps/matsuri-knockdown.png",
    },
]

# 手書きのページ（目印の間を書き換える）
HAND_PAGES = ["index.html", "diagnosis.html"]
# カードが載っているはずのページ（検査用）
ALL_PAGES = ["index.html", "prices.html", "trials.html", "cancel.html", "diagnosis.html"]

CSS_START, CSS_END = "/* other-apps-css:start */", "/* other-apps-css:end */"
HTML_START, HTML_END = "<!-- other-apps:start -->", "<!-- other-apps:end -->"

# ページごとの色の変数に頼らない（どのページでも同じ見た目になるよう値を直に書く）。
OTHER_APPS_CSS = """  .oapps{max-width:760px;margin:0 auto;padding:8px 20px 12px;}
  .oapps h2{font-size:1em;margin:0 0 10px;color:#6a6c75;font-weight:700;border:0;padding:0;}
  .oapps ul{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:12px;}
  .oapps a{display:flex;gap:12px;align-items:center;padding:12px 14px;border:1px solid #e3e8ef;border-radius:14px;
    background:#fff;color:#1c1c22;text-decoration:none;height:100%;box-sizing:border-box;margin:0;}
  .oapps a:hover{border-color:#0d47c9;}
  .oapps img{width:56px;height:56px;border-radius:13px;flex:none;}
  .oapps b{display:block;font-size:.98em;line-height:1.4;}
  .oapps span{display:block;font-size:.84em;line-height:1.5;color:#6a6c75;}
  .oapps span.en{font-size:.78em;}
  @media (max-width:600px){ .oapps ul{grid-template-columns:1fr;} }"""


def app_url(app_id: str) -> str:
    return f"https://apps.apple.com/jp/app/id{app_id}?pt={CAMPAIGN_PT}&ct={OTHER_APPS_CT}&mt=8"


def other_apps_html() -> str:
    e = lambda s: html.escape(s, quote=True)
    items = ""
    for a in OTHER_APPS:
        items += (
            f'      <li><a href="{e(app_url(a["id"]))}">'
            f'<img src="./{e(a["icon"])}" alt="" width="56" height="56" loading="lazy">'
            f'<div><b>{e(a["name"])}</b><span>{e(a["line"])}</span>'
            f'<span class="en" lang="en">{e(a["name_en"])} — {e(a["line_en"])}</span></div></a></li>\n'
        )
    return (
        '  <section class="oapps" aria-label="同じ作者のほかの作品">\n'
        "    <h2>同じ作者のほかの作品（iPhone）</h2>\n"
        "    <ul>\n"
        f"{items}"
        "    </ul>\n"
        "  </section>"
    )


def _between(text: str, start: str, end: str, body: str, name: str) -> str:
    i, j = text.find(start), text.find(end)
    if i < 0 or j < 0 or j < i or text.count(start) != 1 or text.count(end) != 1:
        raise SystemExit(f"{name}: 目印 {start} 〜 {end} が 1 組ありません")
    return text[: i + len(start)] + "\n" + body + "\n  " + text[j:]


def inject(path: Path) -> bool:
    """手書きのページの目印の間を書き換える。変わったら True。"""
    old = path.read_text(encoding="utf-8")
    new = _between(old, CSS_START, CSS_END, OTHER_APPS_CSS, path.name)
    new = _between(new, HTML_START, HTML_END, other_apps_html(), path.name)
    if new != old:
        path.write_text(new, encoding="utf-8", newline="\n")
    return new != old


def main() -> None:
    for name in HAND_PAGES:
        changed = inject(ROOT / name)
        print(f"{name}: {'書き換えた' if changed else '変わりなし'}")


if __name__ == "__main__":
    sys.exit(main())
