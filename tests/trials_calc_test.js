// 解約期限の計算と .ics の組み立ての小テスト。 node tests/trials_calc_test.js
// trials_calc.js（trials.html に埋め込まれる正）をそのまま読む。依存なし。
const path = require('path');
const fs = require('fs');
const T = require(path.join(__dirname, '..', 'trials_calc.js'));

let n = 0, ng = 0;
function eq(got, want, name) {
  n++;
  if (got !== want) { ng++; console.log('NG ' + name + '\n   got : ' + got + '\n   want: ' + want); }
}
function ok(cond, name) { eq(!!cond, true, name); }
const iso = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
const calc = (s, k, store, custom) => { const r = T.compute(T.parse(s), k, custom, store); return [iso(r.last), iso(r.bill), iso(r.deadline)].join(' '); };

// ◯日間型（ページの例: 11/20・30日間 → 12/19 まで無料・12/20 に課金）
eq(calc('2026-11-20', 'd30', false), '2026-12-19 2026-12-20 2026-12-18', '30日間');
eq(calc('2026-12-24', 'd30', false), '2027-01-22 2027-01-23 2027-01-21', '30日間・年をまたぐ');
eq(calc('2027-01-01', 'd31', false), '2027-01-31 2027-02-01 2027-01-30', '31日間');
eq(calc('2027-01-03', 'd14', false), '2027-01-16 2027-01-17 2027-01-15', '14日間');
eq(calc('2026-12-30', 'd7', false), '2027-01-05 2027-01-06 2027-01-04', '7日間・年をまたぐ');
// ◯か月型と月末
eq(calc('2026-11-20', 'm1', false), '2026-12-19 2026-12-20 2026-12-18', '1か月');
eq(calc('2026-12-31', 'm1', false), '2027-01-30 2027-01-31 2027-01-29', '12/31 + 1か月');
eq(calc('2027-01-31', 'm1', false), '2027-02-27 2027-02-28 2027-02-26', '1/31 + 1か月（平年）');
eq(calc('2028-01-31', 'm1', false), '2028-02-28 2028-02-29 2028-02-27', '1/31 + 1か月（うるう年）');
eq(calc('2027-11-30', 'm3', false), '2028-02-28 2028-02-29 2028-02-27', '11/30 + 3か月（うるう年の 2 月）');
eq(calc('2026-12-28', 'm3', false), '2027-03-27 2027-03-28 2027-03-26', '12/28 + 3か月');
eq(calc('2026-12-31', 'm2', false), '2027-02-27 2027-02-28 2027-02-26', '12/31 + 2か月');
eq(calc('2028-02-29', 'm1', false), '2028-03-28 2028-03-29 2028-03-27', 'うるう日 + 1か月');
// ストア経由は 1 日早い
eq(calc('2026-11-20', 'd30', true), '2026-12-19 2026-12-20 2026-12-17', 'ストア経由');
eq(calc('2027-01-01', 'd31', true), '2027-01-31 2027-02-01 2027-01-29', 'ストア経由・月をまたぐ');
// 日数を入力（範囲の外は丸める）
eq(calc('2026-12-01', 'custom', false, '60'), '2027-01-29 2027-01-30 2027-01-28', '60日');
eq(calc('2026-12-01', 'custom', false, '0'), '2026-12-01 2026-12-02 2026-11-30', '0 は 1 日に');
eq(calc('2026-12-01', 'custom', false, 'abc'), '2026-12-01 2026-12-02 2026-11-30', '数字でなければ 1 日に');
eq(T.parse(''), null, '空の日付');
eq(T.parse('2026-13'), null, '欠けた日付');

// .ics
const r = T.compute(T.parse('2026-12-24'), 'd30', '', false);
const ics = T.buildIcs(r, 'U-NEXT, 動画; 見放題', { now: new Date(Date.UTC(2026, 10, 14, 1, 2, 3)), uid: 'test@subscope', url: 'https://example.com/?ct=x' });
const lines = ics.split('\r\n');
ok(ics.endsWith('\r\n'), '最後は CRLF');
ok(!/[^\r]\n/.test(ics), '改行は全部 CRLF');
eq(lines[0], 'BEGIN:VCALENDAR', '始まり');
eq(lines[lines.length - 2], 'END:VCALENDAR', '終わり');
ok(lines.includes('VERSION:2.0'), 'VERSION');
ok(lines.includes('UID:test@subscope'), 'UID');
ok(lines.includes('DTSTAMP:20261114T010203Z'), 'DTSTAMP は UTC');
ok(lines.includes('DTSTART;VALUE=DATE:20270121'), '予定の日＝解約の目安');
ok(lines.includes('DTEND;VALUE=DATE:20270122'), '終日の予定の終わりは翌日');
eq(lines.filter(l => l === 'BEGIN:VALARM').length, 2, '通知は 2 つ');
eq(lines.filter(l => l === 'END:VALARM').length, 2, '通知の閉じ');
ok(lines.includes('TRIGGER:-P1DT15H'), '2 日前の 9:00');
ok(lines.includes('TRIGGER:-PT15H'), '前日の 9:00');
const unfolded = ics.replace(/\r\n /g, '');
ok(unfolded.includes('SUMMARY:U-NEXT\\, 動画\\; 見放題の無料体験を解約する（期限）'), '題名のカンマとセミコロンを逃がす');
ok(unfolded.includes('課金が始まる日: 1月23日'), '説明に課金日');
ok(unfolded.includes('\\n\\n続けるサブスクの管理は Subscope で: https://example.com/?ct=x'), '説明の末尾のリンク');
ok(!/DESCRIPTION:[^\r]*\n[^ ]/.test(unfolded.split('\r\n').filter(l => l.startsWith('DESCRIPTION:')).join('')), '説明に生の改行が無い');
ok(lines.every(l => Buffer.byteLength(l, 'utf8') <= 75), '1 行は 75 オクテットまで');
ok(lines.filter(l => l.startsWith(' ')).length > 0, '長い行は折り返している');
// 月末の終日の予定（DTEND が翌月へ）
const r2 = T.compute(T.parse('2027-01-02'), 'd31', '', false);   // 目安 1/31
ok(T.buildIcs(r2, '', { uid: 'u' }).includes('DTSTART;VALUE=DATE:20270131\r\nDTEND;VALUE=DATE:20270201'), '月末の予定の終わり');
ok(T.buildIcs(r2, '   ', { uid: 'u' }).replace(/\r\n /g, '').includes('SUMMARY:無料体験を解約する（期限）'), '名前が空なら「無料体験」');
eq(T.icsFileName(r2), 'trial-cancel-20270131.ics', 'ファイル名');
const long = T.buildIcs(r2, 'あ'.repeat(80), { uid: 'u' }).replace(/\r\n /g, '');
ok(long.includes('SUMMARY:' + 'あ'.repeat(40) + 'の無料体験'), '名前は 40 字まで');
eq(T.fold('a'.repeat(76)), 'a'.repeat(75) + '\r\n a', '75 オクテットで折る');
eq(T.icsText('a\\b\nc'), 'a\\\\b\\nc', 'バックスラッシュと改行');

// 埋め込み先の trials.html が同じ JS を持っている（作り直し忘れの検査）
const html = fs.readFileSync(path.join(__dirname, '..', 'trials.html'), 'utf8').replace(/\r\n/g, '\n');
const js = fs.readFileSync(path.join(__dirname, '..', 'trials_calc.js'), 'utf8').replace(/\r\n/g, '\n');
ok(html.includes(js), 'trials.html に trials_calc.js が埋め込まれている（python build_trials.py を回す）');
ok(html.includes('id="c-ics"') && html.includes('ct=web-trials-ics'), 'ボタンとキャンペーンリンク');

console.log(ng ? `NG ${ng} / ${n}` : `ALL OK (${n})`);
process.exit(ng ? 1 : 0);
