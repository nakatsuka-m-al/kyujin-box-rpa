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
