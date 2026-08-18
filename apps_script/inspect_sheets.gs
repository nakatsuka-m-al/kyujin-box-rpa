/**
 * 転記処理を組む前の下調べ。読み取り専用で、どこにも書き込まない。
 *
 * 使い方:
 *   1. 新しい Apps Script プロジェクトを作る（既存のものと分けてよい）
 *   2. この中身を貼り付けて保存
 *   3. 関数 inspectAll を実行してログを見る
 *
 * 確認すること:
 *   - 各シートのヘッダ（列名と列記号）
 *   - 氏名・生年月日・性別などの実際の書式
 *   - 判定に使う列（BP列・S列）に何が入っているか
 */

/** RPAが書き込んでいる側 */
const SRC_ID = '1H-AhBNG0mZcKdlEgeqHlHtKM_wvX53Hhlt0GJdkfdyo';

/** 転記先 */
const DST_ID = '108O_PWeXENQe1Lbz64q9lYzXsGHPBlOCb0poDVxc_-o';

/** 見出しだけ見たいシート／中身も見たいシート */
const SRC_SHEETS = ['ALL_ATSOBS', 'OBS'];
const DST_SHEETS = ['応募情報（ATS）', '応募情報（求人ボックス）', '応募まとめ', '有効応募まとめ', 'Indeed'];

/** 個人情報がログに出るため、値はこの長さで切る */
const MAX_LEN = 40;

function inspectAll() {
  inspectBook('転記元', SRC_ID, SRC_SHEETS);
  Logger.log('');
  inspectBook('転記先', DST_ID, DST_SHEETS);
}

function inspectBook(label, id, targets) {
  var book;
  try {
    book = SpreadsheetApp.openById(id);
  } catch (e) {
    Logger.log(`[${label}] 開けませんでした: ${e}`);
    Logger.log('  → このスクリプトを実行しているアカウントに編集権限があるか確認してください');
    return;
  }

  Logger.log(`========== ${label}: ${book.getName()} ==========`);
  const names = book.getSheets().map(function (s) { return s.getName(); });
  Logger.log(`タブ一覧: ${names.join(' / ')}`);

  targets.forEach(function (name) {
    Logger.log('');
    if (names.indexOf(name) === -1) {
      Logger.log(`--- ${name} : 見つかりません ---`);
      return;
    }
    dumpSheet(book.getSheetByName(name));
  });
}

function dumpSheet(sheet) {
  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  Logger.log(`--- ${sheet.getName()} : ${lastRow}行 x ${lastCol}列 ---`);

  if (lastRow === 0 || lastCol === 0) {
    Logger.log('  （空）');
    return;
  }

  const header = sheet.getRange(1, 1, 1, lastCol).getDisplayValues()[0];
  header.forEach(function (name, i) {
    if (name !== '') {
      Logger.log(`  ${colName(i + 1)}: ${name}`);
    }
  });

  // 書式を知りたいので数行だけ中身を見る
  const sampleCount = Math.min(2, lastRow - 1);
  if (sampleCount <= 0) {
    Logger.log('  （データ行なし）');
    return;
  }

  const rows = sheet.getRange(2, 1, sampleCount, lastCol).getDisplayValues();
  rows.forEach(function (row, r) {
    const filled = [];
    row.forEach(function (v, i) {
      if (v !== '') {
        const s = String(v).replace(/\n/g, '⏎');
        filled.push(`${colName(i + 1)}=${s.length > MAX_LEN ? s.slice(0, MAX_LEN) + '…' : s}`);
      }
    });
    Logger.log(`  ${r + 2}行目: ${filled.join('  ')}`);
  });
}

function colName(n) {
  var s = '';
  while (n > 0) {
    const m = (n - 1) % 26;
    s = String.fromCharCode(65 + m) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

/**
 * 絞り込みに使う列に、実際どんな値が入っているかを数える。
 * ALL_ATSOBS の BP列 と OBS の S列。
 */
function inspectFilterColumns() {
  const book = SpreadsheetApp.openById(SRC_ID);
  [['ALL_ATSOBS', 'BP'], ['OBS', 'S']].forEach(function (pair) {
    const sheet = book.getSheetByName(pair[0]);
    if (!sheet) {
      Logger.log(`${pair[0]} が見つかりません`);
      return;
    }
    const lastRow = sheet.getLastRow();
    if (lastRow < 2) {
      Logger.log(`${pair[0]} ${pair[1]}列: データ行なし`);
      return;
    }
    const values = sheet.getRange(`${pair[1]}2:${pair[1]}${lastRow}`).getDisplayValues();
    const count = {};
    values.forEach(function (r) {
      const v = String(r[0]).trim();
      count[v] = (count[v] || 0) + 1;
    });
    Logger.log(`--- ${pair[0]} ${pair[1]}列 の値の内訳 ---`);
    Object.keys(count).sort(function (a, b) { return count[b] - count[a]; })
      .slice(0, 20)
      .forEach(function (v) {
        Logger.log(`  ${v === '' ? '（空）' : v} : ${count[v]} 件`);
      });
  });
}
