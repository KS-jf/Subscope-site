#!/usr/bin/env python3
"""「同じ作者のほかの作品」のカードが 5 ページに正しく載っているかの検査。

    python tests/other_apps_check.py                 # ページの中身だけ（通信なし）
    python tests/other_apps_check.py --check-links   # App Store のリンクが生きているかも見る

見る物:
- 5 ページ（index / prices / trials / cancel / diagnosis）に、site_parts.py が作るカードがそのまま入っている
  （＝OTHER_APPS を直した後に作り直し忘れたページが無い）
- どのリンクにも pt（プロバイダ ID）と ct=cross-subscope-site が付いている
- アイコンのファイルがある
- 生成するページから支出診断へのリンクが消えていない（手で足した物が作り直しで消えた事があった）
"""
from __future__ import annotations

import html
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import site_parts as sp  # noqa: E402

ng = 0
n = 0


def ok(cond: bool, name: str) -> None:
    global ng, n
    n += 1
    if not cond:
        ng += 1
        print("NG " + name)


card = sp.other_apps_html()
for page in sp.ALL_PAGES:
    text = (ROOT / page).read_text(encoding="utf-8")
    ok(text.count('<section class="oapps"') == 1, f"{page}: カードが 1 つ")
    ok(card in text, f"{page}: カードが site_parts.py の今の中身と同じ（作り直し忘れ）")
    ok(sp.OTHER_APPS_CSS in text, f"{page}: カードのスタイルが入っている")
    ok(text.find('<section class="oapps"') < text.find("<footer"), f"{page}: カードはフッタの前")
    links = [html.unescape(u) for u in re.findall(r'href="(https://apps\.apple\.com/[^"]+ct=cross[^"]*)"', text)]
    ok(len(links) == len(sp.OTHER_APPS), f"{page}: カードのリンクが {len(sp.OTHER_APPS)} 本")
    for u in links:
        ok(f"pt={sp.CAMPAIGN_PT}&" in u and f"ct={sp.OTHER_APPS_CT}&" in u and u.endswith("mt=8"),
           f"{page}: pt・ct・mt が付いている {u}")

for page in ["prices.html", "trials.html", "cancel.html"]:
    text = (ROOT / page).read_text(encoding="utf-8")
    ok('href="./diagnosis.html"' in text, f"{page}: 支出診断へのリンクが残っている")
ok("diagnosis.html" in (ROOT / "sitemap.xml").read_text(encoding="utf-8"), "sitemap.xml: diagnosis.html の行が残っている")

for a in sp.OTHER_APPS:
    p = ROOT / a["icon"]
    ok(p.exists() and p.stat().st_size > 1000, f"アイコンがある {a['icon']}")
    ok(len(a["line"]) <= 30, f"一言が 30 字以内 {a['name']}")

if "--check-links" in sys.argv[1:]:
    for a in sp.OTHER_APPS:
        url = sp.app_url(a["id"])
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (link check)"})
            with urllib.request.urlopen(req, timeout=20) as r:
                ok(r.status == 200, f"リンクが開く {url}")
        except (urllib.error.URLError, TimeoutError) as e:
            ok(False, f"リンクが開く {url}（{e}）")

print(f"{n - ng}/{n} OK" + ("" if ng == 0 else f"・{ng} NG"))
sys.exit(1 if ng else 0)
