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
    ['応募者情報の自動連携について', ''],
    ['', ''],
    ['最終更新', Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy年M月d日')],
    ['', ''],

    ['■ このシートでできること', ''],
    ['', ''],
    ['', '求人媒体（求人ボックス・Indeed）に応募が入ると、'],
    ['', '応募者の情報がこのシートに自動で追加されます。'],
    ['', ''],
    ['', '手作業での転記は必要ありません。'],
    ['', '条件に合う方だけが「応募まとめ」に並びますので、'],
    ['', 'そこから選考に進める方を選んでいただく形になります。'],
    ['', ''],

    ['■ 全体の流れ', ''],
    ['', ''],
    ['1', '応募者が求人に応募する'],
    ['2', 'Indeed経由の方に、ご経験を伺うアンケートを自動でメール送信（1〜2分以内）'],
    ['3', '応募内容がこのシートに自動で追加される（1時間以内）'],
    ['4', 'アンケートの回答が「Indeed」シートに自動で入る'],
    ['5', '条件に合う方が「応募まとめ」に自動でまとまる'],
    ['6', '選考に進める方に「有効」と入力すると「有効応募まとめ」へ移る'],
    ['', ''],

    ['■ シートの見方', ''],
    ['', ''],
    ['シート名', '内容'],
    ['メール送信履歴', 'アンケートをお送りした記録。二重送信を防ぐために使います'],
    ['応募情報（ATS）', 'Indeed経由の応募者。すべての応募が入ります'],
    ['応募情報（求人ボックス）', '求人ボックス経由の応募者。すべての応募が入ります'],
    ['Indeed', 'アンケートの回答。応募者が回答すると自動で入ります'],
    ['応募まとめ', '条件に合う方だけが並びます。ここをご覧ください'],
    ['有効応募まとめ', '選考に進める方。進捗の管理にお使いください'],
    ['', ''],

    ['■ 応募まとめに並ぶ方の条件', ''],
    ['', ''],
    ['', 'すべての条件を満たした方だけが並びます。'],
    ['', ''],
    ['共通', 'お名前に漢字が含まれる方'],
    ['', '男性は45歳まで／女性は50歳まで'],
    ['', '在学中の方は対象外（中途採用のため）'],
    ['', ''],
    ['Indeed経由', 'アンケートに回答された方'],
    ['', 'かつ、新規開拓の営業経験（アウトバウンド）をお持ちの方'],
    ['', ''],
    ['求人ボックス経由', '職務経歴に営業のご経験がある方'],
    ['', ''],

    ['■ ご入力いただく箇所', ''],
    ['', ''],
    ['', '「応募まとめ」のA列だけ、手でご入力ください。'],
    ['', ''],
    ['応募まとめ A列', '選考に進める方に「有効」とご入力ください'],
    ['', '「有効」と入力された方だけが「有効応募まとめ」に移ります'],
    ['', '「保留」など別の言葉を入れた場合は移りません'],
    ['', ''],
    ['有効応募まとめ', '選考ステータス以降の列をご入力ください'],
    ['', '年収・業種などの空欄も、必要に応じてご記入ください'],
    ['', ''],

    ['■ 応募者へお送りしているメール', ''],
    ['', ''],
    ['差出人', MAIL_SENDER_NAME],
    ['件名', MAIL_SUBJECT],
    ['本文', MAIL_BODY.replace('{name}', '（応募者のお名前）').replace('{form}', FORM_URL)],
    ['', ''],
    ['お送りする相手', 'Indeed経由でご応募いただいた方'],
    ['お送りする回数', 'お一人につき1回だけ'],
    ['お送りする時期', 'ご応募から1〜2分以内'],
    ['', ''],

    ['■ ご注意いただきたいこと', ''],
    ['', ''],
    ['', '「応募情報」の行を消すと、同じ方がもう一度追加されることがあります'],
    ['', '見出し（1行目）の文言を変更すると、自動追加が止まります'],
    ['', 'アンケートの回答は、ご応募時と同じメールアドレスでの照合が必要です'],
    ['', ''],

    ['■ お問い合わせ', ''],
    ['', ''],
    ['', '動作が止まっている、内容がおかしいなどありましたら'],
    ['', '株式会社BLAZE までご連絡ください。'],
  ];

  sheet.getRange(1, 1, lines.length, 2).setValues(lines);

  sheet.getRange('A1').setFontSize(14).setFontWeight('bold');
  sheet.setColumnWidth(1, 200);
  sheet.setColumnWidth(2, 720);
  sheet.getRange(1, 1, lines.length, 2).setVerticalAlignment('top').setWrap(true);

  lines.forEach(function (row, i) {
    if (String(row[0]).indexOf('■') === 0) {
      sheet.getRange(i + 1, 1, 1, 2).setFontWeight('bold').setBackground('#eef3f8');
    }
  });

  sheet.setFrozenRows(1);
  Logger.log(`シート '${name}' を作りました`);
}

// ============================================================
// 転記先だけで完結するテスト
//   RPAシートには一切書かない。
//   「RPAから転記された」「フォームに回答があった」状態を直接作り、
//   加工と集約だけを検証する。
// ============================================================

/** テスト行の目印 */
const TEST_COMPANY = 'テスト株式会社';

/**
 * 想定結果:
 *   通過 … 田中一郎 / 森大輔 / 山田太一 / 佐々木綾   （4件）
 *   除外 … 年齢3 / 氏名2 / 学生1 / 営業条件外2 / フォーム未回答1
 */
const TEST_ATS = [
  { memo: '通過（男44・アウトバウンド）', name: '田中 一郎', kana: 'たなか いちろう',
    gender: '男性', birth: '1982-03-15', tel: '09000000001', enrolled: 'false',
    company: '株式会社サンプル商事', job: '法人営業', school: '早稲田大学', degree: '学士',
    form: '新規営業（テレアポなどアウトバウンド営業）, 既存営業' },
  { memo: '通過（男41・アウトバウンド）', name: '森 大輔', kana: 'もり だいすけ',
    gender: '男性', birth: '1985-03-03', tel: '09000000002', enrolled: 'false',
    company: '株式会社テスト工業', job: '新規開拓営業', school: '東京大学', degree: '修士',
    form: '新規営業（テレアポなどアウトバウンド営業）' },
  { memo: '除外（女54・年齢超過）', name: '佐藤 花子', kana: 'さとう はなこ',
    gender: '女性', birth: '1972-06-20', tel: '09000000003', enrolled: 'false',
    company: '株式会社テスト物産', job: '法人営業', school: '青山学院大学', degree: '学士',
    form: '新規営業（テレアポなどアウトバウンド営業）' },
  { memo: '除外（男48・年齢超過）', name: '鈴木 次郎', kana: 'すずき じろう',
    gender: '男性', birth: '1978-01-10', tel: '09000000004', enrolled: 'false',
    company: '株式会社ダミー工業', job: '営業', school: '法政大学', degree: '学士',
    form: '新規営業（テレアポなどアウトバウンド営業）' },
  { memo: '除外（氏名がカタカナ）', name: 'グエン バン', kana: 'ぐえん ばん',
    gender: '男性', birth: '1995-05-05', tel: '09000000005', enrolled: 'false',
    company: '株式会社サンプル貿易', job: '営業', school: '東京国際大学', degree: '学士',
    form: '新規営業（テレアポなどアウトバウンド営業）' },
  { memo: '除外（在学中）', name: '高橋 美咲', kana: 'たかはし みさき',
    gender: '女性', birth: '2003-09-01', tel: '09000000006', enrolled: 'true',
    company: '株式会社サンプルカフェ', job: 'アルバイト', school: '明治大学', degree: '学士',
    form: '新規営業（テレアポなどアウトバウンド営業）' },
  { memo: '除外（インバウンドのみ）', name: '渡辺 健二', kana: 'わたなべ けんじ',
    gender: '男性', birth: '1990-01-01', tel: '09000000007', enrolled: 'false',
    company: '株式会社サンプル通信', job: '反響営業', school: '立教大学', degree: '学士',
    form: '新規営業（問い合わせ対応などインバウンド営業）, 既存営業' },
  { memo: '除外（フォーム未回答）', name: '岡田 真理', kana: 'おかだ まり',
    gender: '女性', birth: '1980-05-05', tel: '09000000008', enrolled: 'false',
    company: '株式会社テスト商会', job: '営業', school: '上智大学', degree: '学士',
    form: null },
];

const TEST_OBS = [
  { memo: '通過（男41・正社員・営業あり）', name: '山田 太一（やまだ たいち）',
    gender: '男性', birth: '1985年07月07日 (41歳)', status: '正社員', tel: '09000000011',
    school: '慶應義塾大学',
    career: '株式会社サンプル電機（2010年4月～2018年3月）／法人向けルート営業 → ' +
            '株式会社テスト建設（2018年4月～2026年6月）／新規開拓営業と既存顧客対応' },
  { memo: '通過（女44・セールス表記）', name: '佐々木 綾（ささき あや）',
    gender: '女性', birth: '1982年02月20日 (44歳)', status: '契約社員', tel: '09000000012',
    school: '立命館大学',
    career: '株式会社サンプル商会（2012年4月～2026年7月）／インサイドセールスとして新規開拓' },
  { memo: '除外（女52・年齢超過）', name: '中村 恵子（なかむら けいこ）',
    gender: '女性', birth: '1974年02月14日 (52歳)', status: '無職・その他', tel: '09000000013',
    school: '日本女子大学',
    career: '株式会社ダミー保険（2000年4月～2015年9月）／個人向け保険営業' },
  { memo: '除外（氏名がローマ字）', name: 'LEE MINHO',
    gender: '男性', birth: '1990年04月01日 (36歳)', status: '正社員', tel: '09000000014',
    school: 'ソウル大学',
    career: '株式会社サンプル貿易（2015年4月～2026年5月）／海外向け法人営業' },
  { memo: '除外（職歴に営業なし）', name: '伊藤 直美（いとう なおみ）',
    gender: '女性', birth: '1988年08月08日 (38歳)', status: '主婦・主夫', tel: '09000000015',
    school: '東京家政大学',
    career: '株式会社ダミー食品（2011年4月～2020年3月）／総務および経理事務を担当' },
];

function testMail(i) { return `nakatsuka-m+x${String(i + 1).padStart(2, '0')}@blaze-ltd.com`; }

/** テストデータを転記先に直接入れる */
function createTestData() {
  const book = SpreadsheetApp.openById(DST_ID);

  // --- 応募情報（ATS）: RPAから転記された状態を作る ---
  const atsRows = TEST_ATS.map(function (d, i) {
    return {
      'お仕事ID': `8800${String(i + 1).padStart(3, '0')}`,
      '拠点名・管理NO': TEST_COMPANY,
      '応募職種': '営業スタッフ（テスト）',
      'お名前': d.name,
      'フリガナ': d.kana,
      '生年月日': '0000-00-00',             // 実データと同じく未入力
      'ご住所': '',                          // 位置情報から補完されるかを見る
      'メールアドレス': testMail(i),
      '電話番号': d.tel,
      '選考状況': '未対応',
      '原稿パターン': 'A',
      '応募受付日時': testDateTime(i),
      '【名】': d.name.split(' ')[1] || '',
      '【姓】': d.name.split(' ')[0],
      '【email】': testMail(i),
      '【位置情報】': '応募者の居住国: JP\n応募者の居住する市区町村: 東京都新宿区\npostalcode: 160-0022',
      '【personalDetails】': `性別: ${d.gender}\n生年月日: ${d.birth}`,
      '【職歴】': [
        '就業を開始した月[1]: 04',
        '就業を開始した年度[1]: 2015',
        'この仕事がユーザーの現職か[1]: true',
        `職種名[1]: ${d.job}`,
        `会社名[1]: ${d.company}`,
        '_total: 1',
      ].join('\n'),
      '【学歴】': [
        `この教育機関で取得した学位[1]: ${d.degree}`,
        `教育機関の名称[1]: ${d.school}`,
        '卒業した年度[1]: 2008',
        `この教育機関に在学中[1]: ${d.enrolled}`,
        '_total: 1',
      ].join('\n'),
      '【スキル】': d.job,
    };
  });
  appendByHeader(book, '応募情報（ATS）', atsRows);

  // --- 応募情報（求人ボックス） ---
  const obsRows = TEST_OBS.map(function (d, i) {
    const career = d.career;
    return {
      '応募No': `A2-8800-${String(i + 1).padStart(4, '0')}`,
      '応募日時': testDateTime(i),
      '氏名': d.name,
      '性別': d.gender,
      '生年月日': d.birth,
      '現在の職業': d.status,
      '電話番号': d.tel,
      'メールアドレス': testMail(i + TEST_ATS.length),
      '住所': '東京都新宿区（テスト）',
      '学校名': d.school,
      '職歴': career,
      '備考・PR': 'テストデータです',
      '求人タイトル': '営業職（テスト）',
      '求人ID': '8800-0001-0001',
      '選考ステータス': '未対応',
      '拠点名': TEST_COMPANY,
      '職歴に営業を含む': /営業|セールス|Sales/.test(career) ? '○' : '',
    };
  });
  appendByHeader(book, '応募情報（求人ボックス）', obsRows);

  // --- Indeed: フォームに回答があった状態を作る ---
  // 「経験年数」という同名の列が3つあるため、位置で組み立てる
  const form = book.getSheetByName('Indeed');
  const formRows = [];
  TEST_ATS.forEach(function (d, i) {
    if (d.form === null) return;   // 未回答の人は作らない
    const row = new Array(form.getLastColumn()).fill('');
    row[0] = testDateTime(i);                 // タイムスタンプ
    row[1] = '同意します。';
    row[2] = d.name;
    row[3] = testMail(i);
    row[4] = d.tel;
    row[5] = '営業';
    row[6] = d.form;                          // 営業の種類
    row[7] = '3年以上';                        // 経験年数
    row[9] = '有';                             // 個人目標の有無
    row[10] = '新規獲得件数を月10件';           // 目標概要
    if (row.length > 14) row[14] = d.birth.replace(/-/g, '/');   // 生年月日
    formRows.push(row);
  });
  if (formRows.length) {
    form.getRange(form.getLastRow() + 1, 1, formRows.length, formRows[0].length)
      .setValues(formRows);
    Logger.log(`[Indeed] フォーム回答 ${formRows.length} 件を追加しました`);
  }

  Logger.log('');
  Logger.log(`テストデータを入れました。拠点名 '${TEST_COMPANY}' で判別できます`);
  Logger.log('次に aggregateAll を実行してください');
}

/** テストデータを消す。RPAシートには触らない */
function removeTestData() {
  const book = SpreadsheetApp.openById(DST_ID);
  deleteRowsWhere(book, '応募情報（ATS）', '拠点名・管理NO', TEST_COMPANY);
  deleteRowsWhere(book, '応募情報（求人ボックス）', '拠点名', TEST_COMPANY);

  // フォーム回答とまとめは、テスト用のメールアドレスで判別する
  deleteRowsMatching(book, 'Indeed', 'メールアドレス', /\+x\d+@blaze-ltd\.com$/);
  deleteRowsMatching(book, '応募まとめ', 'メールアドレス', /\+x\d+@blaze-ltd\.com$/);
  Logger.log('有効応募まとめに入った分は、必要なら手で消してください');
}

function deleteRowsMatching(book, sheetName, headerName, pattern) {
  const sheet = book.getSheetByName(sheetName);
  if (!sheet) { Logger.log(`[${sheetName}] 見つかりません`); return; }
  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  if (lastRow < 2) return;

  const header = sheet.getRange(1, 1, 1, lastCol).getDisplayValues()[0]
    .map(function (h) { return String(h).trim(); });
  const col = header.indexOf(headerName);
  if (col === -1) { Logger.log(`[${sheetName}] 列 '${headerName}' がありません`); return; }

  const values = sheet.getRange(2, col + 1, lastRow - 1, 1).getDisplayValues();
  var deleted = 0;
  for (var i = values.length - 1; i >= 0; i--) {
    if (pattern.test(String(values[i][0]).trim())) { sheet.deleteRow(i + 2); deleted++; }
  }
  Logger.log(`[${sheetName}] ${deleted} 行を削除しました`);
}

function testDateTime(i) {
  const d = new Date();
  d.setDate(d.getDate() - (i + 1));
  d.setHours(9 + i, 15, 0, 0);
  return Utilities.formatDate(d, 'Asia/Tokyo', 'yyyy/MM/dd HH:mm:ss');
}
