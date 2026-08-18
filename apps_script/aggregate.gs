/**
 * 応募まとめ／有効応募まとめへの集約（第3・4段階）
 *
 *   応募情報（ATS）＋Indeed(フォーム回答) → 応募まとめ
 *   応募情報（求人ボックス）              → 応募まとめ
 *   応募まとめ（A列「有効」に入力あり）    → 有効応募まとめ
 *
 * transfer.gs と同じプロジェクトに追加する。
 * 定数（SRC_ID / DST_ID）と readSheet などは transfer.gs のものを使う。
 *
 * トリガー設定:
 *   aggregateAll を「分ベースのタイマー」10分おき
 */

// ===== 絞り込み条件 =====

/** 年齢の上限 */
const AGE_LIMIT = { '男性': 45, '女性': 50 };

/** 求人ボックス側で営業経験とみなす語 */
const SALES_WORDS = ['営業', 'セールス', 'Sales'];

/**
 * ATS側で有効とみなす営業の種類。
 * 議事録の「インバウンドではなく自ら新規顧客をとりにいくこと」に合わせ、
 * アウトバウンドを含む回答だけを対象にする。
 */
const REQUIRED_SALES_TYPE = 'アウトバウンド';

/** 学位の言い換え。左が Indeed の表記、右がシートの表記 */
const DEGREE_MAP = {
  '博士': '院卒', '修士': '院卒', '大学院': '院卒',
  '学士': '大卒', '大学': '大卒',
  '短期大学士': '短大卒', '短大': '短大卒',
  '専門学校': '専門卒', '専修学校': '専門卒',
  '高等学校': '高卒', '高校': '高卒',
  '中学校': '中卒',
};

// ===== エントリポイント =====

function aggregateAll() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) {
    Logger.log('前回の処理が実行中のためスキップ');
    return;
  }
  try {
    aggregateToSummary();
    promoteToValidSummary();
  } finally {
    lock.releaseLock();
  }
}

// ===== 第3段階: 応募まとめ =====

function aggregateToSummary() {
  const book = SpreadsheetApp.openById(DST_ID);
  const summary = readSheet(book, '応募まとめ');
  const form = readSheet(book, 'Indeed');
  const ats = readSheet(book, '応募情報（ATS）');
  const kb = readSheet(book, '応募情報（求人ボックス）');

  // 既に載っている人（メール／電話で判定）
  const existing = {};
  summary.rows.forEach(function (row) {
    contactKeys(valueOf(summary, row, 'メールアドレス'), valueOf(summary, row, '電話番号'))
      .forEach(function (k) { existing[k] = true; });
  });

  // フォーム回答をメール／電話で引けるようにする。
  // 「経験年数」という同名の列が3つあるため、名前では引けない。
  // 「営業の種類」以降を位置で切り出し、応募まとめの同じ並びに写す。
  const formAnchor = form.header.indexOf('営業の種類');
  if (formAnchor === -1) throw new Error('Indeedシートに 営業の種類 列がありません');

  const answers = {};
  form.rows.forEach(function (row) {
    const rec = {
      mail: valueOf(form, row, 'メールアドレス'),
      tel: valueOf(form, row, '電話番号'),
      birth: valueOf(form, row, '生年月日'),
      salesType: row[formAnchor],
      block: row.slice(formAnchor),   // 営業の種類 以降をまとめて持つ
    };
    contactKeys(rec.mail, rec.tel).forEach(function (k) {
      answers[k] = rec;   // 同じ人が複数回答した場合は後の回答で上書き
    });
  });

  const rows = [];
  const reasons = { 回答なし: 0, 営業種別: 0, 氏名: 0, 年齢: 0, 学生: 0, 既出: 0 };

  ats.rows.forEach(function (row) {
    const get = function (n) { return valueOf(ats, row, n); };
    const keys = contactKeys(get('メールアドレス'), get('電話番号'));
    if (keys.some(function (k) { return existing[k]; })) { reasons.既出++; return; }

    const answer = firstMatch(answers, keys);
    if (!answer) { reasons.回答なし++; return; }

    if (String(answer.salesType || '').indexOf(REQUIRED_SALES_TYPE) === -1) {
      reasons.営業種別++; return;
    }

    const person = atsPerson(get, answer);
    const judged = judge(person);
    if (judged !== 'ok') { reasons[judged]++; return; }

    rows.push(summaryRow(summary, person));
    keys.forEach(function (k) { existing[k] = true; });
  });

  kb.rows.forEach(function (row) {
    const get = function (n) { return valueOf(kb, row, n); };
    const keys = contactKeys(get('メールアドレス'), get('電話番号'));
    if (keys.some(function (k) { return existing[k]; })) { reasons.既出++; return; }

    const career = String(get('職歴') || '');
    const sales = salesEntries(career);
    if (sales.length === 0) { reasons.営業種別++; return; }

    const person = kbPerson(get, sales);
    const judged = judge(person);
    if (judged !== 'ok') { reasons[judged]++; return; }

    rows.push(summaryRow(summary, person));
    keys.forEach(function (k) { existing[k] = true; });
  });

  Logger.log(
    `[応募まとめ] 新規 ${rows.length} 件 / ` +
    `既出 ${reasons.既出} / フォーム未回答 ${reasons.回答なし} / ` +
    `営業条件外 ${reasons.営業種別} / 氏名 ${reasons.氏名} / ` +
    `年齢 ${reasons.年齢} / 学生 ${reasons.学生}`
  );

  if (rows.length === 0) return;
  if (DRY_RUN) {
    Logger.log('DRY_RUN のため書き込みません:');
    rows.forEach(function (r) { Logger.log(`  ${r.slice(1, 8).join(' | ')}`); });
    return;
  }

  summary.sheet
    .getRange(summary.sheet.getLastRow() + 1, 1, rows.length, summary.header.length)
    .setValues(rows);
  Logger.log(`[応募まとめ] ${rows.length} 行を追加しました`);
}

/**
 * 応募まとめの1行を組み立てる。A列「有効」は手動なので空のまま。
 * M列以降はフォーム回答をそのままの並びで写す。
 */
function summaryRow(summary, p) {
  const map = {
    '応募日時': formatDateTime(p.appliedAt),
    'お名前': p.name,
    'フリガナ': p.kana,
    '性別': p.gender,
    '生年月日': formatDate(p.birth),
    '年齢': p.age,
    'ご住所': p.address,
    'メールアドレス': p.mail,
    '電話番号': p.tel,
    '学歴': p.education,
    '職歴': p.career,
  };

  const anchor = summary.header.indexOf('（Indeed）営業の種類／（求人ボックス）経歴');

  return summary.header.map(function (name, i) {
    if (anchor !== -1 && i >= anchor) {
      if (p.formBlock) {
        const v = p.formBlock[i - anchor];
        return v === undefined ? '' : v;
      }
      // 求人ボックスはフォームが無い。M列に営業に該当する職歴を入れる
      return i === anchor ? p.salesDetail : '';
    }
    return map[name] === undefined ? '' : map[name];
  });
}

/** ATS側の1人分を整える */
function atsPerson(get, answer) {
  const details = parseKeyValue(String(get('【personalDetails】') || ''));
  const jobs = parseIndexed(String(get('【職歴】') || ''));
  const schools = parseIndexed(String(get('【学歴】') || ''));

  // 生年月日はフォームの回答を最優先。応募データ側は 0000-00-00 が多い
  const birth = firstNonEmpty([
    answer.birth, details['生年月日'], get('生年月日'),
  ]);

  return {
    source: 'ATS',
    appliedAt: get('応募受付日時'),
    name: String(get('お名前') || '').trim(),
    kana: get('フリガナ'),
    gender: firstNonEmpty([details['性別'], get('性別')]),
    birth: birth,
    age: ageOf(birth),
    // 応募データに住所が無い場合は Indeed の位置情報から補う
    address: firstNonEmpty([get('ご住所'), locationOf(get('【位置情報】'))]),
    mail: get('メールアドレス'),
    tel: get('電話番号'),
    education: schoolOf(get('【学歴】')),      // 学校名だけにする
    career: careerText(get('【職歴】')),       // 読める形に整える
    salesDetail: answer.salesType,
    formBlock: answer.block,
    jobs: jobs,
    schools: schools,
  };
}

/** 求人ボックス側の1人分を整える */
function kbPerson(get, salesList) {
  const rawName = String(get('氏名') || '').trim();
  const birthCell = String(get('生年月日') || '');

  return {
    source: '求人ボックス',
    appliedAt: get('応募日時'),
    name: stripKana(rawName),
    kana: extractKana(rawName),
    gender: get('性別'),
    birth: birthCell,
    age: ageOf(birthCell),
    address: get('住所'),
    mail: get('メールアドレス'),
    tel: get('電話番号'),
    education: get('学校名'),
    career: get('職歴'),
    // 営業に該当する職歴だけを並べる
    salesDetail: salesList.join('／'),
    currentJob: get('現在の職業'),
    careerEntries: careerEntries(String(get('職歴') || '')),
  };
}

/** 絞り込み。通れば 'ok'、外れたら理由を返す */
function judge(p) {
  if (!hasKanji(p.name)) return '氏名';
  const limit = AGE_LIMIT[String(p.gender || '').trim()];
  if (limit !== undefined && p.age !== '' && p.age > limit) return '年齢';
  if (isStudent(p)) return '学生';   // 中途採用のため在学中は対象外
  return 'ok';
}

/**
 * 在学中かどうか。
 * 求人ボックスは「現在の職業」、ATSは学歴の「在学中」で判定する。
 */
function isStudent(p) {
  const job = String(p.currentJob || '');
  if (/大学生|大学院生|専門学校生|学生/.test(job)) return true;
  return (p.schools || []).some(function (s) {
    return isTrue(s['この教育機関に在学中']);
  });
}

// ===== 第4段階: 有効応募まとめ =====

function promoteToValidSummary() {
  const book = SpreadsheetApp.openById(DST_ID);
  const summary = readSheet(book, '応募まとめ');
  const valid = readSheet(book, '有効応募まとめ');

  // 応募まとめの学歴・職歴は読みやすく整形済みで、
  // 学位や在学中の情報が残っていない。判定には元の応募情報を引き直す。
  const origin = buildOriginIndex(book);

  const existing = {};
  valid.rows.forEach(function (row) {
    const k = validKey(valueOf(valid, row, '応募日'), valueOf(valid, row, '氏名'));
    if (k) existing[k] = true;
  });

  const rows = [];
  summary.rows.forEach(function (row) {
    const get = function (n) { return valueOf(summary, row, n); };
    if (String(get('有効') || '').trim() === '') return;   // 手動で有効にしたものだけ

    const k = validKey(get('応募日時'), get('お名前'));
    if (!k || existing[k]) return;
    existing[k] = true;

    const src = firstMatch(origin, contactKeys(get('メールアドレス'), get('電話番号'))) || {};
    rows.push(validRow(valid, get, src));
  });

  Logger.log(`[有効応募まとめ] 新規 ${rows.length} 件`);
  if (rows.length === 0) return;
  if (DRY_RUN) {
    Logger.log('DRY_RUN のため書き込みません:');
    rows.forEach(function (r) { Logger.log(`  ${r.slice(0, 10).join(' | ')}`); });
    return;
  }

  valid.sheet
    .getRange(valid.sheet.getLastRow() + 1, 1, rows.length, valid.header.length)
    .setValues(rows);
  Logger.log(`[有効応募まとめ] ${rows.length} 行を追加しました`);
}

function validRow(valid, get, src) {
  const map = {
    '応募日': dateOnly(get('応募日時')),
    '応募経路': '求人媒体',
    '媒体名': 'Oubo Pay',
    '氏名': get('お名前'),
    '年齢': get('年齢'),
    '性別': get('性別'),
    '現職／離職中': employmentStatus(src),
    '現職（前職）社名': latestCompany(src.career || get('職歴')),
    '最終学歴': degreeOf(src.education || ''),
    '大学名／学校名': get('学歴'),          // 応募まとめの時点で学校名だけになっている
  };
  return valid.header.map(function (name) {
    return map[name] === undefined ? '' : map[name];
  });
}

/**
 * メール／電話 → 元の応募情報。
 * 現職か・在学中か・学位は、整形前のテキストにしか残っていない。
 */
function buildOriginIndex(book) {
  const index = {};

  const ats = readSheet(book, '応募情報（ATS）');
  ats.rows.forEach(function (row) {
    const rec = {
      education: valueOf(ats, row, '【学歴】'),
      career: valueOf(ats, row, '【職歴】'),
      currentJob: '',
    };
    contactKeys(valueOf(ats, row, 'メールアドレス'), valueOf(ats, row, '電話番号'))
      .forEach(function (k) { index[k] = rec; });
  });

  const kb = readSheet(book, '応募情報（求人ボックス）');
  kb.rows.forEach(function (row) {
    const rec = {
      education: '',                                  // 求人ボックスは学校名のみで学位が無い
      career: valueOf(kb, row, '職歴'),
      currentJob: valueOf(kb, row, '現在の職業'),
    };
    contactKeys(valueOf(kb, row, 'メールアドレス'), valueOf(kb, row, '電話番号'))
      .forEach(function (k) { index[k] = rec; });
  });

  return index;
}

// ===== 判定・抽出 =====

/**
 * 現職／離職中／学生。
 * 求人ボックスは「現在の職業」、ATSはIndeedの「現職か」「在学中」で判定する。
 */
function employmentStatus(src) {
  const job = String((src && src.currentJob) || '');
  if (job) {
    if (/大学生|大学院生|専門学校生|学生/.test(job)) return '学生';
    if (/無職|主婦|主夫/.test(job)) return '離職中';
    return '現職中';
  }

  const schools = parseIndexed(String((src && src.education) || ''));
  if (schools.some(function (s) { return isTrue(s['この教育機関に在学中']); })) return '学生';

  const jobs = parseIndexed(String((src && src.career) || ''));
  if (jobs.length > 0) {
    return jobs.some(function (j) { return isTrue(j['この仕事がユーザーの現職か']); })
      ? '現職中' : '離職中';
  }
  return '';
}

/** 直近の会社名。現職があればそれ、無ければ終了年月が最も新しいもの */
function latestCompany(career) {
  const jobs = parseIndexed(career);
  if (jobs.length > 0) {
    const current = jobs.filter(function (j) {
      return isTrue(j['この仕事がユーザーの現職か']);
    });
    const target = current.length ? current : jobs.slice().sort(function (a, b) {
      return Number(b['就業を開始した年度'] || 0) - Number(a['就業を開始した年度'] || 0);
    });
    return target[0]['会社名'] || '';
  }

  // 求人ボックス形式。並び順が時系列でないため終了年月で比べる
  const entries = careerEntries(career);
  if (entries.length === 0) return '';
  const sorted = entries.slice().sort(function (a, b) { return b.endValue - a.endValue; });
  return sorted[0].company;
}

/** 最終学歴。Indeed の学位表記をシートの言い方に直す */
function degreeOf(education) {
  const schools = parseIndexed(education);
  if (schools.length === 0) return '';   // 求人ボックスは学校名しか無いため空
  const raw = String(schools[0]['この教育機関で取得した学位'] || '').trim();
  if (!raw) return '';
  const hit = Object.keys(DEGREE_MAP).filter(function (k) { return raw.indexOf(k) !== -1; });
  return hit.length ? DEGREE_MAP[hit[0]] : raw;
}

function schoolOf(education) {
  const schools = parseIndexed(education);
  if (schools.length > 0) return schools[0]['教育機関の名称'] || '';
  return String(education || '').trim();   // 求人ボックスは学校名がそのまま入っている
}

/** 職歴を ' → ' で区切り、営業に該当するものだけ返す */
function salesEntries(career) {
  return String(career || '').split('→')
    .map(function (s) { return s.trim(); })
    .filter(function (s) {
      return s !== '' && SALES_WORDS.some(function (w) { return s.indexOf(w) !== -1; });
    });
}

/** 「会社名（2012年10月～2026年3月）／内容」を分解する */
function careerEntries(career) {
  return String(career || '').split('→').map(function (s) {
    const text = s.trim();
    const m = text.match(/^(.+?)[（(]([^）)]*)[）)]/);
    const company = m ? m[1].trim() : text.split('／')[0].trim();
    const period = m ? m[2] : '';
    const dates = period.match(/(\d{4})\D+(\d{1,2})/g) || [];
    const last = dates.length ? dates[dates.length - 1].match(/(\d{4})\D+(\d{1,2})/) : null;
    return {
      text: text,
      company: company,
      endValue: last ? Number(last[1]) * 100 + Number(last[2]) : 0,
    };
  }).filter(function (e) { return e.text !== ''; });
}

// ===== 文字列の道具 =====

/** 「キー[1]: 値」形式を [{キー:値}, ...] に変換する */
function parseIndexed(text) {
  const out = [];
  String(text || '').split('\n').forEach(function (line) {
    const m = line.match(/^(.+?)\[(\d+)\]\s*:\s*(.*)$/);
    if (!m) return;
    const i = Number(m[2]) - 1;
    if (!out[i]) out[i] = {};
    out[i][m[1].trim()] = m[3].trim();
  });
  return out.filter(function (o) { return o; });
}

/** 「キー: 値」を1つのオブジェクトにする */
function parseKeyValue(text) {
  const out = {};
  String(text || '').split('\n').forEach(function (line) {
    const m = line.match(/^([^:]+?)\s*:\s*(.*)$/);
    if (m) out[m[1].trim()] = m[2].trim();
  });
  return out;
}

function isTrue(v) {
  return String(v || '').trim().toLowerCase() === 'true';
}

function hasKanji(name) {
  return /[一-鿿]/.test(String(name || ''));
}

/** 「佐光 収（さみつ おさむ）」→「佐光 収」 */
function stripKana(name) {
  return String(name || '').replace(/[（(][^）)]*[）)]\s*$/, '').trim();
}

/** 「佐光 収（さみつ おさむ）」→「さみつ おさむ」 */
function extractKana(name) {
  const m = String(name || '').match(/[（(]([^）)]*)[）)]\s*$/);
  return m ? m[1].trim() : '';
}

/** 生年月日から年齢。「1990年04月28日 (36歳)」のような括弧書きがあればそれを使う */
function ageOf(birth) {
  const s = String(birth || '');
  const paren = s.match(/[(（]\s*(\d{1,3})\s*歳/);
  if (paren) return Number(paren[1]);

  const m = s.match(/(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
  if (!m) return '';
  const y = Number(m[1]), mo = Number(m[2]), d = Number(m[3]);
  if (!y || !mo || !d) return '';        // 0000-00-00 のような未入力
  const now = new Date();
  var age = now.getFullYear() - y;
  if (now.getMonth() + 1 < mo || (now.getMonth() + 1 === mo && now.getDate() < d)) age--;
  return age;
}

/**
 * 応募日時の表記を揃える。
 * 元データは「2026-07-09 16:03:16」「2026年8月17日10時30分」など
 * ばらばらのため、まとめて yyyy/MM/dd HH:mm にする。
 */
function formatDateTime(v) {
  if (Object.prototype.toString.call(v) === '[object Date]') {
    return Utilities.formatDate(v, 'Asia/Tokyo', 'yyyy/MM/dd HH:mm');
  }
  const n = String(v || '').match(/\d+/g);
  if (!n || n.length < 3 || n[0].length !== 4) return String(v || '');
  const p = function (i) { return ('0' + (n[i] || '0')).slice(-2); };
  return `${n[0]}/${p(1)}/${p(2)} ${p(3)}:${p(4)}`;
}

/** 生年月日は日付だけ。yyyy/MM/dd に揃える */
function formatDate(v) {
  if (Object.prototype.toString.call(v) === '[object Date]') {
    return Utilities.formatDate(v, 'Asia/Tokyo', 'yyyy/MM/dd');
  }
  const n = String(v || '').match(/\d+/g);
  if (!n || n.length < 3 || n[0].length !== 4) return String(v || '');
  if (Number(n[1]) === 0 || Number(n[2]) === 0) return '';   // 0000-00-00 など
  return `${n[0]}/${('0' + n[1]).slice(-2)}/${('0' + n[2]).slice(-2)}`;
}

/** Indeed の位置情報から住所を組み立てる */
function locationOf(text) {
  const kv = parseKeyValue(String(text || ''));
  const city = kv['応募者の居住する市区町村'] || '';
  const post = kv['postalcode'] || '';
  if (!city && !post) return '';
  return (post ? `〒${post} ` : '') + city;
}

/**
 * Indeed の職歴を読める形にする。
 * 「就業を開始した年度[1]: 2022」のような羅列のままでは読みづらいため、
 * 「会社名（2022年5月～現在）／職種名」に組み直す。
 */
function careerText(text) {
  const jobs = parseIndexed(String(text || ''));
  if (jobs.length === 0) return String(text || '');
  return jobs.map(function (j) {
    const from = j['就業を開始した年度']
      ? `${j['就業を開始した年度']}年${Number(j['就業を開始した月'] || 0) || ''}月`.replace('年月', '年')
      : '';
    const to = isTrue(j['この仕事がユーザーの現職か']) ? '現在'
      : (j['就業を終了した年度'] ? `${j['就業を終了した年度']}年` : '');
    const period = from || to ? `（${from}～${to}）` : '';
    const role = j['職種名'] || '';
    return `${j['会社名'] || ''}${period}${role ? '／' + role : ''}`;
  }).filter(function (t) { return t.replace(/[（）／～]/g, '').trim() !== ''; }).join(' → ');
}

function dateOnly(v) {
  if (Object.prototype.toString.call(v) === '[object Date]') {
    return Utilities.formatDate(v, 'Asia/Tokyo', 'yyyy/MM/dd');
  }
  const m = String(v || '').match(/(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
  return m ? `${m[1]}/${('0' + m[2]).slice(-2)}/${('0' + m[3]).slice(-2)}` : String(v || '');
}

/** メールと電話。どちらでも突き合わせられるようにする */
function contactKeys(mail, tel) {
  const keys = [];
  const m = String(mail || '').trim().toLowerCase();
  if (m) keys.push('m:' + m);
  const t = String(tel || '').replace(/[^\d]/g, '');
  if (t) keys.push('t:' + t);
  return keys;
}

function firstMatch(table, keys) {
  for (var i = 0; i < keys.length; i++) {
    if (table[keys[i]]) return table[keys[i]];
  }
  return null;
}

function firstNonEmpty(list) {
  for (var i = 0; i < list.length; i++) {
    const v = list[i];
    if (v !== undefined && v !== null && String(v).trim() !== '' &&
        String(v).indexOf('0000-00-00') === -1) {
      return v;
    }
  }
  return '';
}

function validKey(date, name) {
  const d = dateOnly(date).replace(/\D/g, '');
  const n = String(name || '').replace(/[\s　]/g, '');
  return d && n ? `${d}__${n}` : '';
}
