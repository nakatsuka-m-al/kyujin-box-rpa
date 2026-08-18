/**
 * 応募者データの転記（第1段階）
 *
 *   ALL_ATSOBS → 応募情報（ATS）
 *   OBS        → 応募情報（求人ボックス）
 *
 * 列は見出しの名前で対応させる。列を足したり動かしても追従する。
 * 既に転記済みの行は一意キーで判定して二重に入れない。
 *
 * RPAはSheets API経由で書き込むため onChange は発火しない。
 * そのため定期実行（10分おき）で未転記の行を探す方式にしている。
 *
 * トリガー設定:
 *   transferAll を「分ベースのタイマー」10分おき
 */

// ===== 設定 =====

/** RPAが書き込んでいる側 */
const SRC_ID = '1H-AhBNG0mZcKdlEgeqHlHtKM_wvX53Hhlt0GJdkfdyo';

/** 転記先 */
const DST_ID = '108O_PWeXENQe1Lbz64q9lYzXsGHPBlOCb0poDVxc_-o';

/**
 * 対象クライアントの絞り込み。
 * ALL_ATSOBS は BP列（暗号）、OBS は S列（暗号）で判定する。
 * 空にすると絞り込みなし（＝全社が転記先に入るので注意）。
 *
 *   '7A5EDD2B8C' … 株式会社バイク王＆カンパニー（動作確認用）
 *   '2F3146F147' … 本番の対象クライアント。データが入ったらこちらに変更する
 */
const FILTER_CODE = '7A5EDD2B8C';

/** true の間は書き込まず、何が起きるかをログに出すだけ */
const DRY_RUN = true;

// ===== 転記の定義 =====

/**
 * 転記先の見出し → 転記元の見出し。
 * 名前が同じものは書かなくてよい（自動で対応する）。
 */
const ATS_ALIAS = {
  '【名】': '[Indeed]応募者の名前',
  '【姓】': '[Indeed]応募者の姓',
  '【email】': '[Indeed]email',
  '【履歴書の見出し】': '[Indeed]応募者の履歴書の見出し',
  '【応募者の履歴書の概要】': '[Indeed]応募者の履歴書の概要',
  '【firstNameFurigana】': '[Indeed]firstNameFurigana',
  '【lastNameFurigana】': '[Indeed]lastNameFurigana',
  '【その他の追加情報】': '[Indeed]その他の追加情報',
  '【電話番号】': '[Indeed]ユーザーの電話番号',
  '【位置情報】': '[Indeed]ユーザーの位置情報',
  '【personalDetails】': '[Indeed]personalDetails',
  '【スキル】': '[Indeed]応募者のスキル',
  '【skillsList】': '[Indeed]skillsList',
  '【職歴】': '[Indeed]職務内容',
  '【学歴】': '[Indeed]学歴',
  '【リンク】': '[Indeed]リンク',
  '【功績】': '[Indeed]功績',
  '【資格】': '[Indeed]資格',
  '【assessments】': '[Indeed]assessments',
  '【関連団体】': '[Indeed]関連団体',
  '【languages】': '[Indeed]languages',   // 転記元にまだ列が無い。出現したら自動で入る
  '【特許】': '[Indeed]特許',
  '【出版物】': '[Indeed]出版物',
  '【兵役】': '[Indeed]兵役',
  '【relocationStatuses】': '[Indeed]relocationStatuses',
  '【url        ユーザーの Indeed 履歴書を閲覧するための URL】':
    '[Indeed]url        ユーザーの Indeed 履歴書を閲覧するための URL',
};

// ===== エントリポイント =====

function transferAll() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) {
    Logger.log('前回の処理が実行中のためスキップ');
    return;
  }
  try {
    transferAts();
    transferKyujinbox();
  } finally {
    lock.releaseLock();
  }
}

/** ALL_ATSOBS → 応募情報（ATS） */
function transferAts() {
  transfer({
    label: 'ATS',
    srcSheet: 'ALL_ATSOBS',
    dstSheet: '応募情報（ATS）',
    filterHeader: '暗号',
    alias: ATS_ALIAS,
    // 同じ人が別の求人・別の日に応募することがあるため3つ組で一意にする
    keyHeaders: ['お仕事ID', 'お名前', '応募受付日時'],
  });
}

/** OBS → 応募情報（求人ボックス） */
function transferKyujinbox() {
  transfer({
    label: '求人ボックス',
    srcSheet: 'OBS',
    dstSheet: '応募情報（求人ボックス）',
    filterHeader: '暗号',
    alias: {},
    keyHeaders: ['応募No'],
    // 転記元に無い列は、こちらで値を作る
    computed: {
      '職歴に営業を含む': function (get) {
        return String(get('職歴') || '').indexOf('営業') !== -1 ? '○' : '';
      },
    },
  });
}

// ===== 共通処理 =====

function transfer(config) {
  const src = readSheet(SpreadsheetApp.openById(SRC_ID), config.srcSheet);
  const dst = readSheet(SpreadsheetApp.openById(DST_ID), config.dstSheet);

  Logger.log(`[${config.label}] 転記元 ${src.rows.length} 行 / 転記先 ${dst.rows.length} 行`);

  // 転記先に既にあるキー
  const existing = {};
  dst.rows.forEach(function (row) {
    const key = buildKey(config.keyHeaders, function (name) {
      return valueOf(dst, row, name);
    });
    if (key) existing[key] = true;
  });

  // 絞り込みに使う列。転記元に無ければ絞り込まない。
  const filterIndex = config.filterHeader ? src.index[config.filterHeader] : undefined;
  if (FILTER_CODE && filterIndex === undefined) {
    throw new Error(
      `[${config.label}] 絞り込み列 '${config.filterHeader}' が ${config.srcSheet} にありません`
    );
  }

  var skippedByFilter = 0;
  var skippedByDuplicate = 0;
  const newRows = [];

  src.rows.forEach(function (row) {
    const get = function (name) { return valueOf(src, row, name); };

    if (FILTER_CODE) {
      if (String(row[filterIndex] || '').trim() !== FILTER_CODE) {
        skippedByFilter++;
        return;
      }
    }

    const key = buildKey(config.keyHeaders, get);
    if (!key) return;                    // キーが揃わない行は対象外
    if (existing[key]) { skippedByDuplicate++; return; }
    existing[key] = true;                // 転記元に重複があっても1件にする

    newRows.push(buildRow(config, dst, get));
  });

  Logger.log(
    `[${config.label}] 対象外(絞り込み) ${skippedByFilter} 件 / ` +
    `転記済み ${skippedByDuplicate} 件 / 新規 ${newRows.length} 件`
  );

  if (newRows.length === 0) return;

  if (DRY_RUN) {
    Logger.log(`[${config.label}] DRY_RUN のため書き込みません。先頭3件:`);
    newRows.slice(0, 3).forEach(function (r, i) {
      Logger.log(`  ${i + 1}: ${r.slice(0, 8).join(' | ')}`);
    });
    return;
  }

  dst.sheet
    .getRange(dst.sheet.getLastRow() + 1, 1, newRows.length, dst.header.length)
    .setValues(newRows);
  Logger.log(`[${config.label}] ${newRows.length} 行を転記しました`);
}

/** 転記先のヘッダ順に値を並べた1行を作る */
function buildRow(config, dst, get) {
  return dst.header.map(function (name) {
    if (name === '') return '';

    if (config.computed && config.computed[name]) {
      return config.computed[name](get);
    }
    const srcName = config.alias[name] || name;
    const v = get(srcName);
    return v === undefined ? '' : v;
  });
}

function readSheet(book, name) {
  const sheet = book.getSheetByName(name);
  if (!sheet) throw new Error(`シート '${name}' が見つかりません`);

  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  const header = sheet.getRange(1, 1, 1, lastCol).getDisplayValues()[0]
    .map(function (h) { return String(h).trim(); });

  const index = {};
  header.forEach(function (h, i) {
    if (h !== '' && index[h] === undefined) index[h] = i;
  });

  const rows = lastRow >= 2
    ? sheet.getRange(2, 1, lastRow - 1, lastCol).getValues()
    : [];

  return { sheet: sheet, header: header, index: index, rows: rows };
}

function valueOf(table, row, headerName) {
  const i = table.index[headerName];
  return i === undefined ? undefined : row[i];
}

/** 照合用のキー。値が1つでも空なら空文字を返す（＝対象外） */
function buildKey(headers, get) {
  const parts = [];
  for (var i = 0; i < headers.length; i++) {
    const v = normalizeKey(get(headers[i]));
    if (v === '') return '';
    parts.push(v);
  }
  return parts.join('__');
}

/**
 * 日付は表示形式によって見え方が変わるため、比較用に揃える。
 * 記号や空白の違いも吸収する。
 */
function normalizeKey(value) {
  if (value === undefined || value === null) return '';
  if (Object.prototype.toString.call(value) === '[object Date]') {
    return Utilities.formatDate(value, 'Asia/Tokyo', 'yyyyMMddHHmm');
  }
  const s = String(value).trim();
  if (s === '') return '';
  // 日時らしい文字列は年月日時分だけで比較する（秒や区切りの違いを無視）
  const nums = s.match(/\d+/g);
  if (nums && nums.length >= 5 && nums[0].length === 4) {
    return nums.slice(0, 5).map(function (n, i) {
      return i === 0 ? ('0000' + n).slice(-4) : ('00' + n).slice(-2);
    }).join('');
  }
  return s.replace(/[\s　\-\/:_.]/g, '');
}

// ===== 動作確認用 =====

/** 転記元・転記先の見出しが対応しているかを確認する（書き込まない） */
function checkMapping() {
  [
    { label: 'ATS', src: 'ALL_ATSOBS', dst: '応募情報（ATS）', alias: ATS_ALIAS, computed: {} },
    {
      label: '求人ボックス', src: 'OBS', dst: '応募情報（求人ボックス）', alias: {},
      computed: { '職歴に営業を含む': true },
    },
  ].forEach(function (c) {
    const src = readSheet(SpreadsheetApp.openById(SRC_ID), c.src);
    const dst = readSheet(SpreadsheetApp.openById(DST_ID), c.dst);

    Logger.log(`===== ${c.label} =====`);
    const missing = [];
    dst.header.forEach(function (name) {
      if (name === '') return;
      if (c.computed[name]) {
        Logger.log(`  ${name} ← （こちらで計算）`);
        return;
      }
      const srcName = c.alias[name] || name;
      if (src.index[srcName] === undefined) {
        missing.push(`${name} ← ${srcName}`);
      }
    });

    if (missing.length === 0) {
      Logger.log('  すべての列が対応しています');
    } else {
      Logger.log(`  転記元に見つからない列（空欄になります）: ${missing.length} 件`);
      missing.forEach(function (m) { Logger.log(`    ${m}`); });
    }
  });
}

/** 「有効応募まとめ」など、まだ確認していないシートの構成を見る（書き込まない） */
function inspectDestination() {
  const book = SpreadsheetApp.openById(DST_ID);
  Logger.log(`タブ一覧: ${book.getSheets().map(function (s) { return s.getName(); }).join(' / ')}`);

  ['有効応募まとめ', '応募まとめ', 'Indeed'].forEach(function (name) {
    const sheet = book.getSheetByName(name);
    Logger.log('');
    if (!sheet) {
      Logger.log(`--- ${name}: 見つかりません ---`);
      return;
    }
    const lastRow = sheet.getLastRow();
    const lastCol = sheet.getLastColumn();
    Logger.log(`--- ${name}: ${lastRow}行 x ${lastCol}列 ---`);
    if (lastRow === 0 || lastCol === 0) return;

    sheet.getRange(1, 1, 1, lastCol).getDisplayValues()[0].forEach(function (h, i) {
      if (h !== '') Logger.log(`  ${columnLetter(i + 1)}: ${h}`);
    });

    const n = Math.min(2, lastRow - 1);
    if (n <= 0) { Logger.log('  （データ行なし）'); return; }
    sheet.getRange(2, 1, n, lastCol).getDisplayValues().forEach(function (row, r) {
      const filled = [];
      row.forEach(function (v, i) {
        if (v !== '') {
          const s = String(v).replace(/\n/g, '⏎');
          filled.push(`${columnLetter(i + 1)}=${s.length > 40 ? s.slice(0, 40) + '…' : s}`);
        }
      });
      Logger.log(`  ${r + 2}行目: ${filled.join('  ')}`);
    });
  });
}

function columnLetter(n) {
  var s = '';
  while (n > 0) {
    const m = (n - 1) % 26;
    s = String.fromCharCode(65 + m) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

/**
 * ATS側の職歴・学歴の中身をそのまま出す（書き込まない）。
 * 会社名や学校名を取り出せる形式かどうかを判断するために使う。
 */
function dumpAtsCareerSample() {
  const src = readSheet(SpreadsheetApp.openById(SRC_ID), 'ALL_ATSOBS');
  const targets = ['[Indeed]職務内容', '[Indeed]学歴', '[Indeed]personalDetails',
                   '[Indeed]応募者の履歴書の概要'];

  var shown = 0;
  for (var i = 0; i < src.rows.length && shown < 3; i++) {
    const get = function (name) { return valueOf(src, src.rows[i], name); };
    const career = String(get('[Indeed]職務内容') || '');
    // 中身のある行だけ見たい（_total: 0 は空を意味する）
    if (career === '' || career.indexOf('_total: 0') === 0) continue;

    shown++;
    Logger.log(`========== ${shown}件目: ${get('お名前')} ==========`);
    targets.forEach(function (name) {
      const v = String(get(name) || '');
      Logger.log(`--- ${name} ---`);
      Logger.log(v === '' ? '（空）' : v.slice(0, 1500));
    });
    Logger.log('');
  }

  if (shown === 0) {
    Logger.log('職務内容に中身のある行が見つかりませんでした');
  }
}

/** 求人ボックス側の職歴サンプル（書き込まない） */
function dumpKyujinboxCareerSample() {
  const src = readSheet(SpreadsheetApp.openById(SRC_ID), 'OBS');
  var shown = 0;
  for (var i = 0; i < src.rows.length && shown < 3; i++) {
    const get = function (name) { return valueOf(src, src.rows[i], name); };
    const career = String(get('職歴') || '');
    if (career === '') continue;
    shown++;
    Logger.log(`===== ${shown}件目: ${get('氏名')} / 現在の職業=${get('現在の職業')} =====`);
    Logger.log(career.slice(0, 1200));
    Logger.log('');
  }
}

// ============================================================
// 第2段階: フォーム回答依頼メール
// ============================================================

/** 回答してもらうフォーム */
const FORM_URL =
  'https://docs.google.com/forms/d/e/1FAIpQLScu3tZJsVMcftXT61pYZlKF3R0l4ID3GRNIZbHXlFBf9Ab50g/viewform';

/**
 * 動作確認中はここに自分のアドレスを入れる。
 * 応募者には届かず、すべてこのアドレスに送られる。
 * 本番に切り替えるときは空文字にする。
 */
const MAIL_TEST_TO = 'nakatsuka-m@blaze-ltd.com';

/** 1回の実行で送る上限。まとめて大量に送ってしまう事故を防ぐ */
const MAX_MAILS_PER_RUN = 20;

/** 送信済みを記録する列。無ければ自動で作る */
const MAIL_SENT_HEADER = 'メール送信日時';

const MAIL_SUBJECT = 'ご応募ありがとうございます｜ご経験についてのアンケートのお願い';

/** {name} は応募者のお名前に置き換わる */
const MAIL_BODY = [
  '{name} 様',
  '',
  'この度はご応募いただき、誠にありがとうございます。',
  '',
  '選考を進めさせていただくにあたり、ご経験について',
  '簡単なアンケートへのご協力をお願いしております。',
  '',
  '▼回答フォーム（1〜2分で完了します）',
  '{form}',
  '',
  'お手数をおかけしますが、ご確認のほどよろしくお願いいたします。',
  '',
  '------------------------------',
  '株式会社BLAZE',
  '------------------------------',
].join('\n');

/**
 * 応募情報（ATS）の未送信の行にフォーム依頼メールを送る。
 *
 * 送信済みかどうかはシート上の列で管理する。
 * スクリプト内部で持つと、消えたときに二重送信するため。
 */
function sendFormRequests() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) {
    Logger.log('前回の処理が実行中のためスキップ');
    return;
  }

  try {
    const book = SpreadsheetApp.openById(DST_ID);
    const sheet = book.getSheetByName('応募情報（ATS）');
    if (!sheet) throw new Error('シート 応募情報（ATS）が見つかりません');

    const sentCol = ensureColumn(sheet, MAIL_SENT_HEADER);
    const table = readSheet(book, '応募情報（ATS）');

    const mailIndex = table.index['メールアドレス'];
    const nameIndex = table.index['お名前'];
    if (mailIndex === undefined) throw new Error('列 メールアドレス が見つかりません');

    var sent = 0;
    var skipped = 0;

    for (var i = 0; i < table.rows.length; i++) {
      if (sent >= MAX_MAILS_PER_RUN) {
        Logger.log(`上限 ${MAX_MAILS_PER_RUN} 件に達したため、残りは次回に回します`);
        break;
      }

      const row = table.rows[i];
      const rowNo = i + 2;

      const already = String(row[sentCol - 1] || '').trim();
      if (already !== '') { skipped++; continue; }

      const address = String(row[mailIndex] || '').trim();
      if (!isValidAddress(address)) continue;

      const name = String(row[nameIndex] || '').trim() || 'ご応募者';
      const to = MAIL_TEST_TO || address;

      const body = MAIL_BODY
        .replace('{name}', name)
        .replace('{form}', FORM_URL);

      MailApp.sendEmail({
        to: to,
        subject: MAIL_SUBJECT,
        body: MAIL_TEST_TO
          ? `※テスト送信です。本来の宛先: ${address}\n\n${body}`
          : body,
      });

      // 送信できたものだけ記録する。失敗した行は次回やり直せる。
      sheet.getRange(rowNo, sentCol).setValue(new Date());
      sent++;
      Logger.log(`送信: ${name} → ${to}${MAIL_TEST_TO ? `（本来は ${address}）` : ''}`);
    }

    Logger.log(`送信 ${sent} 件 / 送信済み ${skipped} 件`);
    if (MAIL_TEST_TO) {
      Logger.log(`テストモードです。すべて ${MAIL_TEST_TO} に送信しました`);
    }
  } finally {
    lock.releaseLock();
  }
}

/** 見出しが無ければ最終列の右に作り、その列番号を返す */
function ensureColumn(sheet, header) {
  const lastCol = sheet.getLastColumn();
  const names = sheet.getRange(1, 1, 1, lastCol).getDisplayValues()[0];
  for (var i = 0; i < names.length; i++) {
    if (String(names[i]).trim() === header) return i + 1;
  }
  const col = lastCol + 1;
  sheet.getRange(1, col).setValue(header);
  Logger.log(`列 '${header}' を ${columnLetter(col)} 列に作りました`);
  return col;
}

function isValidAddress(s) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);
}

/** 文面の確認用。1通だけ自分宛に送る（シートは更新しない） */
function sendTestMail() {
  const to = MAIL_TEST_TO;
  if (!to) throw new Error('MAIL_TEST_TO が空です。確認用の宛先を入れてください');
  MailApp.sendEmail({
    to: to,
    subject: MAIL_SUBJECT,
    body: MAIL_BODY.replace('{name}', '山田 太郎').replace('{form}', FORM_URL),
  });
  Logger.log(`${to} に確認用メールを送りました`);
}
