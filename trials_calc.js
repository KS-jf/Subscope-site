// 解約期限の計算機（trials.html に build_trials.py がそのまま埋め込む）。
// 入力はこの端末の中だけで使い、どこにも送らない・保存しない。
// 計算と .ics の組み立ては DOM に触らない関数にしてあり、tests/trials_calc_test.js が node で確かめる。
var TrialCalc = (function () {
  function addDays(d, n) { var r = new Date(d.getTime()); r.setDate(r.getDate() + n); return r; }
  function addMonths(d, n) {
    // 翌月に同じ日付が無いときは、その月の末日に寄せる（1/31 + 1か月 → 2/28 か 2/29）
    var y = d.getFullYear(), m = d.getMonth() + n, day = d.getDate();
    var last = new Date(y, m + 1, 0).getDate();
    return new Date(y, m, Math.min(day, last));
  }
  function parse(v) {
    var p = (v || '').split('-');
    if (p.length !== 3) return null;
    var d = new Date(+p[0], +p[1] - 1, +p[2]);
    return isNaN(d.getTime()) ? null : d;
  }
  // kind: 'd30'（日数）・'m1'（月数）・'custom'（customDays を使う）。store: アプリストア経由か
  function compute(d0, kind, customDays, store) {
    var bill, how;
    if (kind === 'custom') { var n = Math.max(1, Math.min(400, parseInt(customDays, 10) || 1)); bill = addDays(d0, n); how = n + '日間'; }
    else if (kind.charAt(0) === 'd') { var nd = parseInt(kind.slice(1), 10); bill = addDays(d0, nd); how = nd + '日間'; }
    else { var nm = parseInt(kind.slice(1), 10); bill = addMonths(d0, nm); how = nm + 'か月'; }
    var last = addDays(bill, -1);
    var safe = addDays(last, store ? -1 : 0);   // ストア経由は「終了の24時間以上前」= 最終日の前日より前に
    var deadline = addDays(safe, -1);            // 時刻の差で課金されないよう、さらに前日を目安に
    return { start: d0, how: how, bill: bill, last: last, deadline: deadline, store: !!store };
  }

  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function ymd(d) { return d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()); }
  function md(d) { return (d.getMonth() + 1) + '月' + d.getDate() + '日'; }
  // RFC 5545 の TEXT: バックスラッシュ・セミコロン・カンマ・改行を逃がす
  function icsText(s) {
    return String(s).replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n');
  }
  // 1 行は 75 オクテットまで（UTF-8）。文字の途中で切らずに、次の行の頭に空白を置いて続ける
  function fold(line) {
    var out = [], cur = '', bytes = 0, limit = 75;
    for (var i = 0; i < line.length; i++) {
      var cp = line.codePointAt(i), ch = String.fromCodePoint(cp);
      if (cp > 0xFFFF) i++;
      var b = cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4;
      if (bytes + b > limit) { out.push(cur); cur = ' '; bytes = 1; }
      cur += ch; bytes += b;
    }
    out.push(cur);
    return out.join('\r\n');
  }
  // 解約の目安の日（終日の予定）に、2 日前と前日の朝 9 時の通知を付けた .ics を返す。
  // r: compute() の結果／name: サービス名（空でもよい）／opt.now: DTSTAMP 用の時刻／opt.uid／opt.url: 説明の末尾に付けるリンク
  function buildIcs(r, name, opt) {
    opt = opt || {};
    var now = opt.now || new Date();
    var label = (name || '').replace(/^\s+|\s+$/g, '').slice(0, 40);
    var what = label ? label + 'の無料体験' : '無料体験';
    var stamp = now.getUTCFullYear() + pad(now.getUTCMonth() + 1) + pad(now.getUTCDate()) + 'T' +
                pad(now.getUTCHours()) + pad(now.getUTCMinutes()) + pad(now.getUTCSeconds()) + 'Z';
    var uid = opt.uid || ('trial-' + ymd(r.deadline) + '-' + now.getTime() + '-' + Math.floor(Math.random() * 1e9) + '@subscope');
    var desc = what + 'を続けないなら、今日までに解約する。\n' +
               '登録日: ' + md(r.start) + '（' + r.how + '）\n' +
               '無料で使える最終日: ' + md(r.last) + '\n' +
               '課金が始まる日: ' + md(r.bill) + '\n' +
               (r.store ? 'App Store / Google Play 経由は終了の24時間以上前に解約が要るため、1日早めています。\n' : '') +
               '一般的な数え方による目安です。登録画面や確認メールの日付を優先してください。' +
               (opt.url ? '\n\n続けるサブスクの管理は Subscope で: ' + opt.url : '');
    function alarm(trigger, text) {
      return ['BEGIN:VALARM', 'ACTION:DISPLAY', 'DESCRIPTION:' + icsText(text), 'TRIGGER:' + trigger, 'END:VALARM'];
    }
    var lines = [
      'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Subscope//Trial Deadline//JA', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
      'BEGIN:VEVENT',
      'UID:' + uid,
      'DTSTAMP:' + stamp,
      'DTSTART;VALUE=DATE:' + ymd(r.deadline),
      'DTEND;VALUE=DATE:' + ymd(addDays(r.deadline, 1)),
      'SUMMARY:' + icsText(what + 'を解約する（期限）'),
      'DESCRIPTION:' + icsText(desc),
      'TRANSP:TRANSPARENT'
    ]
      // 終日の予定は 0:00 始まり。-P1DT15H = 2 日前の 9:00、-PT15H = 前日の 9:00
      .concat(alarm('-P1DT15H', what + 'の解約期限は 2 日後（' + md(r.deadline) + '）'))
      .concat(alarm('-PT15H', what + 'の解約期限は明日（' + md(r.deadline) + '）'))
      .concat(['END:VEVENT', 'END:VCALENDAR']);
    return lines.map(fold).join('\r\n') + '\r\n';
  }
  function icsFileName(r) { return 'trial-cancel-' + ymd(r.deadline) + '.ics'; }

  return { addDays: addDays, addMonths: addMonths, parse: parse, compute: compute, buildIcs: buildIcs, icsFileName: icsFileName, fold: fold, icsText: icsText };
})();

if (typeof module !== 'undefined' && module.exports) { module.exports = TrialCalc; }

if (typeof document !== 'undefined') (function () {
  var $ = function (id) { return document.getElementById(id); };
  var dateEl = $('c-date'), kindEl = $('c-kind'), customWrap = $('c-custom-wrap'), customEl = $('c-custom'), storeEl = $('c-store'), out = $('c-out');
  var icsWrap = $('c-ics-wrap'), icsBtn = $('c-ics'), nameEl = $('c-name'), icsMsg = $('c-ics-msg');
  if (!dateEl || !kindEl || !out) return;
  var W = ['日', '月', '火', '水', '木', '金', '土'];
  var cur = null;
  function fmt(d) { return d.getFullYear() + '年' + (d.getMonth() + 1) + '月' + d.getDate() + '日（' + W[d.getDay()] + '）'; }
  function update() {
    customWrap.style.display = kindEl.value === 'custom' ? '' : 'none';
    var d0 = TrialCalc.parse(dateEl.value);
    if (!d0) {
      cur = null;
      if (icsWrap) icsWrap.style.display = 'none';
      out.textContent = '登録した日を選ぶと、無料の最終日・課金が始まる日・解約の目安を出します（この計算は端末内だけで行い、どこにも送りません）。';
      return;
    }
    var r = cur = TrialCalc.compute(d0, kindEl.value, customEl.value, storeEl.checked);
    out.innerHTML =
      '登録日 <b>' + fmt(d0) + '</b>・' + r.how + 'の場合<br>' +
      '無料で使える最終日: <b>' + fmt(r.last) + '</b><br>' +
      '課金が始まる日: <b>' + fmt(r.bill) + '</b><br>' +
      '解約の目安（この日までに）: <b>' + fmt(r.deadline) + '</b>' +
      (r.store ? '<br><small>App Store / Google Play 経由は終了の24時間以上前に解約が要るため、1日早めています。</small>' : '') +
      '<br><small>月末に登録した場合や、登録時刻から数えるサービスでは前後することがあります。登録画面の日付を優先してください。</small>';
    if (icsWrap) icsWrap.style.display = '';
    if (icsMsg) icsMsg.textContent = '';
  }
  function saveIcs() {
    if (!cur) return;
    var text = TrialCalc.buildIcs(cur, nameEl ? nameEl.value : '', { url: (icsBtn && icsBtn.getAttribute('data-app-url')) || '' });
    var file = TrialCalc.icsFileName(cur);
    try {
      var ua = navigator.userAgent || '';
      var ios = /iPad|iPhone|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
      if (ios) {
        // iOS の Safari は text/calendar をそのまま開くと「カレンダーに追加」の画面を出す
        window.location.href = 'data:text/calendar;charset=utf-8,' + encodeURIComponent(text);
      } else {
        var url = URL.createObjectURL(new Blob([text], { type: 'text/calendar;charset=utf-8' }));
        var a = document.createElement('a');
        a.href = url; a.download = file; a.style.display = 'none';
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
      }
      if (icsMsg) icsMsg.textContent = '予定のファイル（' + file + '）を作りました。開くとカレンダーに追加できます。2 日前と前日の朝 9 時に通知が出ます。';
    } catch (e) {
      if (icsMsg) icsMsg.textContent = 'このブラウザでは予定のファイルを作れませんでした。上の日付をカレンダーに手で入れてください。';
    }
  }
  [dateEl, kindEl, customEl, storeEl].forEach(function (el) { if (el) { el.addEventListener('change', update); el.addEventListener('input', update); } });
  if (icsBtn) icsBtn.addEventListener('click', saveIcs);
  // 既定値: 今日
  try { var t = new Date(); dateEl.value = t.getFullYear() + '-' + String(t.getMonth() + 1).padStart(2, '0') + '-' + String(t.getDate()).padStart(2, '0'); } catch (e) {}
  update();
})();
