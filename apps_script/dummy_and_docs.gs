/**
 * 検証用ダミーデータの投入・削除と、説明シートの生成。
 *
 * transfer.gs と同じプロジェクトに 2つ目のファイルとして追加する。
 * 定数（SRC_ID / DST_ID など）は transfer.gs のものを使う。
 *
 * 使い方:
 *   createDummyData()  … ダミー10件を転記元に入れる
 *   removeDummyData()  … 入れたダミーを消す（本物には触らない）
 *   createReadmeSheet() … 転記先に説明シートを作る
 */

/** ダミー行の目印。この拠点名の行だけを対象にする */
const DUMMY_COMPANY = 'ダミー人材株式会社';

/**
 * 検証用の応募者。
 * 絞り込み条件のどれに当たるかが分かるように、通過・除外を混ぜてある。
 *
 * メールアドレスは自分宛のエイリアスにしてある。
 * 万一テストモードを切ったまま送信しても、応募者には届かない。
 */
const DUMMY_ATS = [
  {
    memo: '通過（男性44歳・現職・営業）',
    name: '田中 一郎', address: '〒160-0022 東京都新宿区新宿', kana: 'たなか いちろう', gender: '男性',
    birth: '1982-03-15', mail: 'nakatsuka-m+t01@blaze-ltd.com', tel: '09000000001',
    job: '営業', company: '株式会社サンプル商事', current: 'true',
    school: '早稲田大学', degree: '学士', enrolled: 'false',
  },
  {
    memo: '通過（女性54歳・現職・営業）',
    name: '佐藤 花子', address: '〒150-0043 東京都渋谷区道玄坂', kana: 'さとう はなこ', gender: '女性',
    birth: '1972-06-20', mail: 'nakatsuka-m+t02@blaze-ltd.com', tel: '09000000002',
    job: '法人営業', company: '株式会社テスト物産', current: 'true',
    school: '青山学院大学', degree: '学士', enrolled: 'false',
  },
  {
    memo: '除外（男性48歳・上限45歳を超過）',
    name: '鈴木 次郎', address: '〒231-0023 神奈川県横浜市中区山下町', kana: 'すずき じろう', gender: '男性',
    birth: '1978-01-10', mail: 'nakatsuka-m+t03@blaze-ltd.com', tel: '09000000003',
    job: '営業', company: '株式会社ダミー工業', current: 'true',
    school: '法政大学', degree: '学士', enrolled: 'false',
  },
  {
    memo: '除外（氏名がカタカナのみ）',
    name: 'グエン バン', address: '〒220-0011 神奈川県横浜市西区高島', kana: 'ぐえん ばん', gender: '男性',
    birth: '1995-05-05', mail: 'nakatsuka-m+t04@blaze-ltd.com', tel: '09000000004',
    job: '営業', company: '株式会社サンプル貿易', current: 'true',
    school: '東京国際大学', degree: '学士', enrolled: 'false',
  },
  {
    memo: '学生（在学中）',
    name: '高橋 美咲', address: '〒101-0021 東京都千代田区外神田', kana: 'たかはし みさき', gender: '女性',
    birth: '2003-09-01', mail: 'nakatsuka-m+t05@blaze-ltd.com', tel: '09000000005',
    job: 'アルバイト', company: '株式会社サンプルカフェ', current: 'true',
    school: '明治大学', degree: '学士', enrolled: 'true',
  },
];

const DUMMY_OBS = [
  {
    memo: '通過（男性41歳・正社員・営業あり）',
    name: '山田 太一（やまだ たいち）', gender: '男性', birth: '1985年07月07日 (41歳)',
    status: '正社員', mail: 'nakatsuka-m+t06@blaze-ltd.com', tel: '09000000006',
    school: '慶應義塾大学',
    career: '株式会社サンプル電機（2010年4月～2018年3月）／法人向けルート営業 → ' +
            '株式会社テスト建設（2018年4月～2026年6月）／新規開拓営業と既存顧客対応',
  },
  {
    memo: '通過（女性52歳・離職中・営業あり）',
    name: '中村 恵子（なかむら けいこ）', gender: '女性', birth: '1974年02月14日 (52歳)',
    status: '無職・その他', mail: 'nakatsuka-m+t07@blaze-ltd.com', tel: '09000000007',
    school: '日本女子大学',
    career: '株式会社ダミー保険（2000年4月～2015年9月）／個人向け保険営業 → ' +
            '有限会社サンプル商会（2016年1月～2025年12月）／店舗運営と接客販売',
  },
  {
    memo: '除外（男性48歳・上限45歳を超過）',
    name: '小林 健太（こばやし けんた）', gender: '男性', birth: '1977年11月30日 (48歳)',
    status: '正社員', mail: 'nakatsuka-m+t08@blaze-ltd.com', tel: '09000000008',
    school: '中央大学',
    career: '株式会社テスト運輸（2005年4月～2026年3月）／営業所長として営業組織を統括',
  },
  {
    memo: '除外（氏名がローマ字）',
    name: 'LEE MINHO', gender: '男性', birth: '1990年04月01日 (36歳)',
    status: '正社員', mail: 'nakatsuka-m+t09@blaze-ltd.com', tel: '09000000009',
    school: 'ソウル大学',
    career: '株式会社サンプル貿易（2015年4月～2026年5月）／海外向け法人営業',
  },
  {
    memo: '除外（職歴に営業を含まない）',
    name: '伊藤 直美（いとう なおみ）', gender: '女性', birth: '1988年08月08日 (38歳)',
    status: '主婦・主夫', mail: 'nakatsuka-m+t10@blaze-ltd.com', tel: '09000000010',
    school: '東京家政大学',
    career: '株式会社ダミー食品（2011年4月～2020年3月）／総務および経理事務を担当',
  },
];

// ===== ダミー投入 =====

function createDummyData() {
  const book = SpreadsheetApp.openById(SRC_ID);

  const atsRows = DUMMY_ATS.map(function (d, i) {
    return {
      '応募経路': 'Indeed (ATS連携)',
      'お仕事ID': `9900${String(i + 1).padStart(3, '0')}`,
      '拠点名・管理NO': DUMMY_COMPANY,
      '応募職種': '営業スタッフ（検証用）',
      'お名前': d.name,
      'フリガナ': d.kana,
      '性別': d.gender,
      'メールアドレス': d.mail,
      '電話番号': d.tel,
      'ご住所': d.address,
      '選考状況': '未対応',
      '原稿パターン': 'A',
      '応募受付日時': dummyDateTime(i),
      '[Indeed]応募者の名前': d.name.split(' ')[1] || '',
      '[Indeed]応募者の姓': d.name.split(' ')[0],
      '[Indeed]email': d.mail,
      '[Indeed]personalDetails': `性別: ${d.gender}\n生年月日: ${d.birth}`,
      '[Indeed]職務内容': [
        '就業を開始した月[1]: 04',
        '就業を開始した年度[1]: 2015',
        `この仕事がユーザーの現職か[1]: ${d.current}`,
        `職種名[1]: ${d.job}`,
        `会社名[1]: ${d.company}`,
        '勤務地[1]: ',
        '職務内容[1]: ',
        '_total: 1',
      ].join('\n'),
      '[Indeed]学歴': [
        `この教育機関で取得した学位[1]: ${d.degree}`,
        'この教育機関で選考した分野[1]: ',
        `教育機関の名称[1]: ${d.school}`,
        '卒業した年度[1]: 2010',
        `この教育機関に在学中[1]: ${d.enrolled}`,
        '_total: 1',
      ].join('\n'),
      '[Indeed]応募者のスキル': d.job,
    };
  });

  const obsRows = DUMMY_OBS.map(function (d, i) {
    return {
      '応募No': `A2-9900-${String(i + 1).padStart(4, '0')}`,
      '応募日時': dummyDateTime(i),
      '氏名': d.name,
      '性別': d.gender,
      '生年月日': d.birth,
      '現在の職業': d.status,
      '電話番号': d.tel,
      'メールアドレス': d.mail,
      '住所': '東京都新宿区（検証用）',
      '学校名': d.school,
      '職歴': d.career,
      '備考・PR': '検証用のダミーデータです',
      '求人タイトル': '営業職（検証用）',
      '求人ID': '9900-0001-0001',
      '選考ステータス': '未対応',
      '拠点名': DUMMY_COMPANY,
    };
  });

  appendByHeader(book, 'ALL_ATSOBS', atsRows);
  appendByHeader(book, 'OBS', obsRows);

  Logger.log('');
  Logger.log(`ダミーを入れました。拠点名 '${DUMMY_COMPANY}' で判別できます`);
  Logger.log('確認が終わったら removeDummyData で消せます');
}

/** 見出しの名前で対応させて末尾に追記する */
function appendByHeader(book, sheetName, records) {
  if (records.length === 0) return;
  const sheet = book.getSheetByName(sheetName);
  if (!sheet) throw new Error(`シート '${sheetName}' が見つかりません`);

  const lastCol = sheet.getLastColumn();
  const header = sheet.getRange(1, 1, 1, lastCol).getDisplayValues()[0]
    .map(function (h) { return String(h).trim(); });

  const unknown = [];
  Object.keys(records[0]).forEach(function (k) {
    if (header.indexOf(k) === -1) unknown.push(k);
  });
  if (unknown.length) {
    Logger.log(`[${sheetName}] 見出しに無いため入れられない項目: ${unknown.join(', ')}`);
  }

  const rows = records.map(function (rec) {
    return header.map(function (name) {
      return rec[name] === undefined ? '' : rec[name];
    });
  });

  sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, header.length).setValues(rows);
  Logger.log(`[${sheetName}] ダミー ${rows.length} 件を追加しました`);
}

function dummyDateTime(i) {
  const d = new Date();
  d.setDate(d.getDate() - (i + 1));
  d.setHours(10 + i, 30, 0, 0);
  return Utilities.formatDate(d, 'Asia/Tokyo', 'yyyy-MM-dd HH:mm:ss');
}

// ===== ダミー削除 =====

/**
 * 拠点名がダミーの行だけを消す。本物のデータには触らない。
 * 転記先に入った分も消す。
 */
function removeDummyData() {
  deleteRowsWhere(SpreadsheetApp.openById(SRC_ID), 'ALL_ATSOBS', '拠点名・管理NO', DUMMY_COMPANY);
  deleteRowsWhere(SpreadsheetApp.openById(SRC_ID), 'OBS', '拠点名', DUMMY_COMPANY);
  deleteRowsWhere(SpreadsheetApp.openById(DST_ID), '応募情報（ATS）', '拠点名・管理NO', DUMMY_COMPANY);
  deleteRowsWhere(SpreadsheetApp.openById(DST_ID), '応募情報（求人ボックス）', '拠点名', DUMMY_COMPANY);
  Logger.log('');
  Logger.log('応募まとめ・有効応募まとめに入った分は、必要なら手で消してください');
}

function deleteRowsWhere(book, sheetName, headerName, value) {
  const sheet = book.getSheetByName(sheetName);
  if (!sheet) { Logger.log(`[${sheetName}] 見つかりません`); return; }

  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  if (lastRow < 2) { Logger.log(`[${sheetName}] データ行なし`); return; }

  const header = sheet.getRange(1, 1, 1, lastCol).getDisplayValues()[0]
    .map(function (h) { return String(h).trim(); });
  const col = header.indexOf(headerName);
  if (col === -1) { Logger.log(`[${sheetName}] 列 '${headerName}' がありません`); return; }

  const values = sheet.getRange(2, col + 1, lastRow - 1, 1).getDisplayValues();

  // 下から消す。上から消すと行番号がずれる。
  var deleted = 0;
  for (var i = values.length - 1; i >= 0; i--) {
    if (String(values[i][0]).trim() === value) {
      sheet.deleteRow(i + 2);
      deleted++;
    }
  }
  Logger.log(`[${sheetName}] ${deleted} 行を削除しました`);
}

// ===== 説明シート =====

/** 転記先に「▶説明」シートを作る（既にあれば作り直す） */
function createReadmeSheet() {
  const book = SpreadsheetApp.openById(DST_ID);
  const name = '▶説明';

  const old = book.getSheetByName(name);
  if (old) book.deleteSheet(old);
  const sheet = book.insertSheet(name, 0);

  const lines = [
    ['応募者データの自動連携について', ''],
    ['', ''],
    ['最終更新', Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy/MM/dd HH:mm')],
    ['', ''],

    ['■ 全体の流れ', ''],
    ['', ''],
    ['1', '求人ボックス／ATS(求人部) に応募が入る'],
    ['2', 'RPAが応募者データを「応募者取得RPA」シートに取り込む（自動）'],
    ['3', 'このシートの「応募情報（ATS）」「応募情報（求人ボックス）」に転記（自動・10分おき）'],
    ['4', 'ATSの応募者にアンケートフォームをメール送信（自動）'],
    ['5', 'フォーム回答が「Indeed」シートに入る（自動）'],
    ['6', '条件に合う人を「応募まとめ」に集約（自動）'],
    ['7', '「応募まとめ」のA列で有効と判断 → 「有効応募まとめ」へ（手動判断）'],
    ['', ''],

    ['■ 各シートの役割', ''],
    ['', ''],
    ['シート名', '内容'],
    ['応募情報（ATS）', 'ATS(求人部)経由の応募者。自動で追加される。手で編集しないこと'],
    ['応募情報（求人ボックス）', '求人ボックス経由の応募者。自動で追加される。同上'],
    ['Indeed', 'アンケートフォームの回答。フォームが自動で書き込む'],
    ['応募まとめ', '条件に合う応募者。A列「有効」だけ手動で入力する'],
    ['有効応募まとめ', '有効と判断した応募者。選考の進捗を管理する'],
    ['', ''],

    ['■ 自動で入る列 / 手動の列', ''],
    ['', ''],
    ['応募情報（ATS）', 'すべて自動。末尾の「メール送信日時」も自動'],
    ['応募情報（求人ボックス）', 'すべて自動。「職歴に営業を含む」は自動判定（○）'],
    ['応募まとめ', 'A列「有効」のみ手動。ほかは自動'],
    ['有効応募まとめ', '氏名・年齢などは自動。選考ステータス以降は手動'],
    ['', ''],

    ['■ 応募まとめに載る条件', ''],
    ['', ''],
    ['ATS経由', 'アンケートフォームに回答した方のみ'],
    ['求人ボックス経由', '職歴に「営業」を含む方のみ'],
    ['共通', '氏名に漢字を含む／男性は45歳まで／女性は55歳まで'],
    ['', ''],

    ['■ 応募者へ送るメール', ''],
    ['', ''],
    ['差出人', MAIL_SENDER_NAME],
    ['件名', MAIL_SUBJECT],
    ['本文', MAIL_BODY.replace('{name}', '（応募者のお名前）').replace('{form}', FORM_URL)],
    ['', ''],

    ['■ 現在の設定', ''],
    ['', ''],
    ['対象クライアント', FILTER_CODE || '（絞り込みなし＝全社が対象）'],
    ['メール送信先', MAIL_TEST_TO
      ? `${MAIL_TEST_TO} のみ（検証中。応募者には届きません）`
      : '応募者本人'],
    ['1回の送信上限', `${MAX_MAILS_PER_RUN} 件`],
    ['', ''],

    ['■ 注意', ''],
    ['', ''],
    ['', '「応募情報」シートの行を手で消すと、同じ人が再度取り込まれます'],
    ['', 'メール送信日時の列を消すと、同じ人に再送されます'],
    ['', '列の見出しを変えると転記が止まります（名前で対応させているため）'],
  ];

  sheet.getRange(1, 1, lines.length, 2).setValues(lines);

  sheet.getRange('A1').setFontSize(14).setFontWeight('bold');
  sheet.setColumnWidth(1, 220);
  sheet.setColumnWidth(2, 700);
  sheet.getRange(1, 1, lines.length, 2).setVerticalAlignment('top').setWrap(true);

  // 見出し行を太字にする
  lines.forEach(function (row, i) {
    if (String(row[0]).indexOf('■') === 0) {
      sheet.getRange(i + 1, 1, 1, 2).setFontWeight('bold').setBackground('#eef3f8');
    }
  });

  Logger.log(`シート '${name}' を作りました`);
}
