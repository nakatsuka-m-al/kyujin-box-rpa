#!/usr/bin/env node
/**
 * AirWork求人リスト(xlsx) → 求人ボックス採用ボード 取り込みCSV 変換
 *
 * 使い方:
 *   node scripts/airwork_to_kyujinbox.js <input.xlsx> [output.csv]
 */
const XLSX = require('xlsx')
const fs = require('fs')
const path = require('path')
const { expand } = require('./personas')
const { validateAll, advise } = require('./validate')

// 企業ID・勤務先名・求人ステータスなどの共通設定
const CONFIG = JSON.parse(fs.readFileSync(path.join(__dirname, 'config.json'), 'utf8'))

// ---------------------------------------------------------------
// 求人ボックス採用ボード（直接投稿）の出力カラム
// 出典: 管理画面からダウンロードした実CSV
//       P-145-049_saiyoboard_kyujin_202608251412.csv のヘッダー行（56列）
// ※マニュアル記入例p.42の「特徴」、仕様表p.30の「求人作成日」はいずれも誤り。
//   実際に受け付けられるのは「求人の特徴」「求人作成日時」。
// ---------------------------------------------------------------
const 勤務地カラム = []
for (let i = 1; i <= 10; i++) 勤務地カラム.push(`勤務地_県_${i}`, `勤務地_詳細_${i}`)

const OUT_COLUMNS = [
  '企業ID',
  '求人ID',
  '求人ステータス',
  '勤務先名',
  '求人タイトル',
  '職種区分',
  '雇用形態',
  '仕事内容',
  'この仕事のやりがい',
  '対象となる方',
  '求人の特徴',
  ...勤務地カラム,
  '交通手段・勤務地補足',
  '給与タイプ',
  '給与（下限）',
  '給与（上限）',
  '給与補足・福利厚生・受動喫煙防止措置など',
  '勤務時間・休日',
  '応募・選考についての必要項目',
  '応募時の電話番号を必須入力にする',
  '応募受付の電話番号',
  '選考について',
  '職場の雰囲気',
  '仕事のスタイル',
  '活かせる持ち味',
  'PR・職場情報_見出し_1',
  'PR・職場情報_内容_1',
  'PR・職場情報_見出し_2',
  'PR・職場情報_内容_2',
  'PR・職場情報_見出し_3',
  'PR・職場情報_内容_3',
  'PR・職場情報_見出し_4',
  'PR・職場情報_内容_4',
  '写真ID',
  '求人作成日時',
  '求人ラベル',
  'メモ',
]

// 文字数上限（求人ボックス仕様）
const MAX_CHARS = {
  '仕事内容': 10000,
  'この仕事のやりがい': 140,
  '対象となる方': 1000,
  '給与補足・福利厚生・受動喫煙防止措置など': 500,
  '勤務時間・休日': 500,
  '選考について': 500,
  'PR・職場情報_見出し_1': 100,
  'PR・職場情報_内容_1': 1000,
  'PR・職場情報_見出し_2': 100,
  'PR・職場情報_内容_2': 1000,
  'PR・職場情報_見出し_3': 100,
  'PR・職場情報_内容_3': 1000,
  'PR・職場情報_見出し_4': 100,
  'PR・職場情報_内容_4': 1000,
  'メモ': 30,
}

// 雇用形態: AirWork → 求人ボックス
const EMPLOYMENT_MAP = {
  '正社員': '正社員',
  'アルバイト・パート': 'アルバイト・パート',
  'アルバイト': 'アルバイト・パート',
  'パート': 'アルバイト・パート',
  '契約社員': '契約社員',
  '業務委託': '業務委託',
  '派遣社員': '派遣社員',
  '紹介予定派遣': '派遣社員',
  '新卒': '新卒・インターン',
  'インターン': '新卒・インターン',
}

// 給与形態: AirWork → 求人ボックス
const SALARY_FORM_MAP = {
  '時給': '時給',
  '日給': '日給',
  '月給': '月給',
  '年収': '年収',
  '年俸': '年収',
  '固定報酬': '固定報酬',
  '完全歩合': '固定報酬',
}

/**
 * 職種区分: AirWorkの職種名 → 求人ボックスの職種区分マスタ（26種・完全一致必須）。
 * 上から順に評価し、最初に当たったものを採用する（具体的なものを先に置く）。
 */
const OCCUPATION_RULES = [
  // 製造系を最優先（「清掃」「農業」など付随語での誤判定を防ぐ）
  [/製造|工場|オペレーター|加工|溶接|旋盤|フライス|マシニング|鍛造|研磨|成形|組立|検査|生産管理|工程管理|ライン/, '工場・製造'],
  [/フォークリフト|倉庫|ピッキング|梱包|仕分け|入出庫|軽作業|棚卸|荷役|荷物/, '軽作業・倉庫作業'],
  [/配送|ドライバー|運転手|輸配送|物流|トラック|宅配/, '配送・物流・交通'],
  [/警備|清掃員|ビルメンテナンス|施設管理|設備管理/, '警備・清掃・点検'],
  [/建築|土木|建設|施工|大工|とび/, '建築・土木・建設工事'],
  [/介護|福祉|ヘルパー|看護助手/, '介護・福祉'],
  [/保育|教員|講師|指導員/, '保育士・教員・講師'],
  [/看護師|医師|薬剤師|コメディカル|医療事務/, '医師・コメディカル'],
  [/美容|理容|エステ|ネイル/, '美容・理容・エステ'],
  [/農作業|農園|林業|漁業|畜産|動物病院/, '農林水産・動物関連'],
  [/飲食|調理|ホール|キッチン|フード/, '飲食店・フード'],
  [/販売|接客|レジ|店舗スタッフ/, '販売・接客・サービス'],
  [/営業|コールセンター|テレアポ|インサイドセールス/, '営業・コールセンター'],
  [/事務|受付|アシスタント|データ入力/, '事務・受付'],
  [/電気\/電子|電子部品|回路|機械設計|電子製造/, '機械・電子エンジニア'],
  [/化学|素材|医薬品|分析/, '医薬品・素材・化学エンジニア'],
]

/**
 * 職種区分を判定する。
 * AirWorkの「職種1」が最も信頼できるため、職種名 → 求人タイトル → 仕事内容 の順に
 * 段階的に評価する。仕事内容には「機械周辺の清掃」のような付随作業が混ざるため、
 * 一括で突き合わせると誤判定する。
 */
function mapOccupation(airworkOccupation, jobTitle, description) {
  for (const source of [airworkOccupation, jobTitle, description]) {
    const hay = String(source ?? '')
    if (!hay) continue
    for (const [re, category] of OCCUPATION_RULES) {
      if (re.test(hay)) return category
    }
  }
  return ''
}

// 応募時入力情報: AirWork → 求人ボックス「応募・選考についての必要項目」
const ENTRY_FORM_MAP = {
  '氏名、連絡先を取得': '氏名・連絡先のみ',
  '氏名、生年月日、連絡先を取得': '基本情報',
  '氏名、生年月日、連絡先、職務経歴を取得': '基本情報＋職務経歴',
}

// 特徴タグ: AirWork → 求人ボックス「求人の特徴」の許可値
const TAG_MAP = {
  // 経験・応募条件
  '未経験者歓迎': '未経験歓迎', '業界未経験歓迎': '未経験歓迎', '経験不問': '未経験歓迎',
  '経験不要': '未経験歓迎', '知識不要': '未経験歓迎',
  '経験者歓迎': '経験者歓迎', '有資格者歓迎': '経験者歓迎', '要経験': '経験者歓迎', '要知識': '経験者歓迎',
  '学歴不問': '学歴不問',
  'ブランクOK': 'ブランクOK',
  'フリーター歓迎': 'フリーター歓迎',
  '主婦・主夫歓迎': '主婦・主夫歓迎',
  '学生歓迎': '学生歓迎', '高校生歓迎': '高校生歓迎',
  '女性が活躍中': '女性活躍', '男性が活躍中': '男性活躍',
  '50代が多い': 'シニア歓迎', '60代も応募可': 'シニア歓迎', 'シニア歓迎': 'シニア歓迎',
  // 待遇・福利厚生
  '交通費支給': '交通費支給',
  '寮あり': '寮・社宅あり', '社宅あり': '寮・社宅あり', '寮・社宅あり': '寮・社宅あり',
  '資格取得支援': '資格取得支援', '資格取得支援あり': '資格取得支援',
  '託児所あり': '託児所あり', '送迎あり': '送迎あり',
  '研修あり': '研修あり', '研修制度あり': '研修あり',
  '社割あり': '社割あり',
  'まかないあり': 'まかない・食事補助あり', '昼食補助あり': 'まかない・食事補助あり',
  '食事補助あり': 'まかない・食事補助あり', '食費補助あり': 'まかない・食事補助あり',
  '賞与あり': '賞与あり', '昇給あり': '昇給あり',
  '産休・育休取得実績あり': '産休・育休取得実績あり',
  '転勤なし': '転勤なし',
  '日払いOK': '日払いOK', '週払いOK': '週払いOK', '給与前払いOK': '給与前払いOK',
  '社員登用あり': '社員登用あり',
  // 勤務条件
  '短時間勤務OK': '短時間勤務OK（4時間以下）',
  'シフト自由': 'シフト自由', 'シフト制': 'シフト制',
  '土日のみOK': '土日のみOK', '平日のみOK': '平日のみOK',
  '週3日以内OK': '週3日以内OK', '週1日～OK': '週1日～OK',
  '早朝': '早朝はたらく',
  '午前': '朝・午前中はたらく',
  '昼勤/日勤': '昼からはたらく',
  '夕方': '夕方・夜はたらく',
  '深夜': '深夜はたらく・夜勤', '夜勤': '深夜はたらく・夜勤', '夜間': '深夜はたらく・夜勤',
  '短期': '短期・単発', '単発': '短期・単発',
  '土日祝休み': '土日祝休みあり',
  '完全週休2日制': '週休2日制', '週休2日制': '週休2日制',
  '残業なし': '残業なし',
  '扶養内勤務OK': '扶養内勤務OK',
  'Wワ―クOK': 'Wワ―クOK', 'WワークOK': 'Wワ―クOK',
  '即日勤務OK': '即日勤務OK',
  // 環境
  '駅チカ': '駅チカ・駅ナカ', '駅ナカ': '駅チカ・駅ナカ',
  '髪型・髪色自由': '髪型・髪色自由',
  '服装自由': '服装自由',
  'ネイル・ピアスOK': 'ネイル・ピアスOK',
  '制服あり': '制服あり',
  '車通勤OK': '車通勤OK', 'バイク通勤OK': 'バイク通勤OK',
  'オープニングスタッフ': 'オープニングスタッフ',
  '大量募集': '大量募集', '急募': '急募',
  'フルリモート': 'フルリモート', '在宅勤務可': '在宅勤務可',
}

// ---------------------------------------------------------------
// ヘルパー
// ---------------------------------------------------------------
const norm = v => String(v ?? '').trim()

/**
 * AirWork原稿に含まれる、求人ボックスでは意味をなさない定型文を除去する。
 *
 * - QRコードの案内: AirWorkは募集画像にQRを載せる運用だが、求人ボックスには表示されないため
 *   「画像のQRコードを長押しして…」が宙に浮く。商標表記もセットで不要になる。
 * - 記号だけの区切り線: 中身が伴わず余白だけが残るため削除する。
 *
 * ※「労働者派遣業(派)08-300957」は労働者派遣法上の表示事項なので必ず残す。
 */
const 区切り線だけ = /^[＝=ー－\-─━☆★‐—~〜\s]+$/
const QR定型文 = /QRコード|デンソーウェーブ/
// 労働者派遣法の表示事項。これを含む行は絶対に消さない
const 法定表示 = /労働者派遣業|派遣事業|許可番号|[(（]派[)）]|有料職業紹介/

function cleanBoilerplate(text) {
  const dropLines = b =>
    b.split('\n')
      .filter(l => !区切り線だけ.test(l))
      .filter(l => !QR定型文.test(l))
      .join('\n')
      .trim()

  return String(text ?? '')
    .split(/\n\s*\n/)
    .map(b => b.trim())
    .filter(Boolean)
    .map(b => {
      // 許可番号などの法定表示を含むブロックは、行単位で不要行だけを取り除いて残す
      if (法定表示.test(b)) return dropLines(b)
      // QR案内は複数行にまたがる定型文なのでブロックごと落とす
      if (QR定型文.test(b)) return ''
      if (区切り線だけ.test(b)) return ''
      return dropLines(b)
    })
    .filter(Boolean)
    .join('\n\n')
}

/** AirWorkヘッダの英語フィールド名 → 列インデックス の索引を作る */
function buildIndex(header) {
  const idx = {}
  header.forEach((h, i) => {
    const m = String(h).match(/\(([a-zA-Z0-9_]+)\)\s*$/)
    if (m) idx[m[1]] = i
    idx[String(h)] = i
  })
  return idx
}

/** 全角/半角問わず文字数カウントし、上限で切る（文の途中で切らないよう努力） */
function clip(text, max) {
  const t = norm(text)
  if (!max || t.length <= max) return t
  const cut = t.slice(0, max)
  const lastBreak = Math.max(cut.lastIndexOf('\n'), cut.lastIndexOf('。'))
  return lastBreak > max * 0.6 ? cut.slice(0, lastBreak + 1) : cut
}

/** カンマ区切りタグ群を求人ボックスの許可値へ写像し、重複除去 */
function mapTags(rawList) {
  const out = []
  rawList.forEach(raw => {
    norm(raw).split(',').forEach(t => {
      const key = t.trim()
      if (!key) return
      const mapped = TAG_MAP[key]
      if (mapped && !out.includes(mapped)) out.push(mapped)
    })
  })
  return out
}

// ---------------------------------------------------------------
// 1行変換
// ---------------------------------------------------------------
function convertRow(row, idx, warnings, rowNo) {
  const raw = key => norm(row[idx[key]])
  // 自由記述はAirWork固有の定型文（QR案内・区切り線）を除去してから使う
  const 自由記述 = new Set([
    'description', 'personal', 'selection_flow', 'welfare', 'salary_supplement',
    'salary_example', 'working_time_supplement', 'holiday', 'work_environment',
    'smoking_section_supplement',
  ])
  const g = key => (自由記述.has(key) ? cleanBoilerplate(raw(key)) : raw(key))

  // --- 特徴タグ ---
  const tags = mapTags([
    g('job_features_cs_dialogue_id_name'),
    g('job_features_job_style_id_name'),
    g('job_features_work_env_id_name'),
    g('job_features_work_location_id_name'),
    g('job_features_work_style_id_name'),
    g('job_features_physical_labor_id_name'),
    g('job_features_work_content_id_name'),
    g('working_location_features_id_name'),
    g('work_environment_id_name'),
    g('salary_allowance_id_name'),
    g('working_hours_id_name'),
    g('holiday_id_name'),
    g('welfare_id_name'),
    g('selection_flow_id_name'),
  ])
  // 社会保険がすべて「有」なら 社会保険完備 を付与
  const ins = ['social_insurance_health_jp', 'social_insurance_wp_jp', 'social_insurance_ei_jp', 'social_insurance_wc_jp']
  if (ins.every(k => g(k) === '有') && !tags.includes('社会保険完備')) tags.push('社会保険完備')

  // --- 勤務時間・休日（結合して500字以内） ---
  const workTime = g('working_time_supplement')
  const holiday = g('holiday')
  let schedule = [workTime, holiday].filter(Boolean).join('\n\n【休日・休暇】\n')
  if (schedule.length > 500) {
    warnings.push(`行${rowNo}: 「勤務時間・休日」が${schedule.length}字→500字に切り詰め`)
    schedule = clip(schedule, 500)
  }

  // --- 給与補足・福利厚生・受動喫煙（結合して500字以内） ---
  const smokingParts = [g('smoking_section_type_jp'), g('smoking_section_supplement')].filter(Boolean)
  const benefitsRaw = [
    g('salary_supplement'),
    g('salary_example'),
    g('welfare'),
    smokingParts.length ? `【受動喫煙防止措置】${smokingParts.join(' / ')}` : '',
  ].filter(Boolean).join('\n\n')
  let benefits = benefitsRaw
  if (benefits.length > 500) {
    warnings.push(`行${rowNo}: 「給与補足・福利厚生」が${benefits.length}字→500字に切り詰め`)
    benefits = clip(benefits, 500)
  }

  // --- 選考について ---
  let selection = [g('selection_flow_id_name'), g('selection_flow')].filter(Boolean).join('\n')
  if (selection.length > 500) {
    warnings.push(`行${rowNo}: 「選考について」が${selection.length}字→500字に切り詰め`)
    selection = clip(selection, 500)
  }

  // --- この仕事のやりがい（140字）: キャッチコピー優先、無ければ仕事内容の冒頭 ---
  const subtitle = g('subtitle')
  let appeal = subtitle
  if (!appeal) {
    appeal = norm(g('description')).split('\n').filter(Boolean).slice(0, 2).join(' ')
    warnings.push(`行${rowNo}: 「この仕事のやりがい」をキャッチコピー不在のため仕事内容から自動生成（要確認）`)
  }
  appeal = clip(appeal, 140)

  // --- 雇用形態 / 給与形態 ---
  const empRaw = g('job_type_jp')
  const employment = EMPLOYMENT_MAP[empRaw] ?? ''
  if (empRaw && !employment) warnings.push(`行${rowNo}: 雇用形態「${empRaw}」が未対応`)

  const salFormRaw = g('salary_form_jp')
  const salaryType = SALARY_FORM_MAP[salFormRaw] ?? ''
  if (salFormRaw && !salaryType) warnings.push(`行${rowNo}: 給与形態「${salFormRaw}」が未対応`)

  // --- 交通手段・勤務地補足 ---
  // 郵便番号は7桁で入っているので 〒319-1222 の形に整える
  const zip = g('working_location_postcode').replace(/[^0-9]/g, '')
  const zipText = zip.length === 7 ? `〒${zip.slice(0, 3)}-${zip.slice(3)}` : (zip ? `〒${zip}` : '')

  // AirWork側は「TAKE FOUR」「ＴＡＫＥＦＯＵＲ」「ＴＡＫＥ　ＦＯＵＲ」と表記が割れているため、
  // 全角英数・全角スペースを半角に寄せてから空白を詰めて比較・統一する。
  const normalizeCompany = name => {
    const half = String(name)
      .replace(/[Ａ-Ｚａ-ｚ０-９]/g, ch => String.fromCharCode(ch.charCodeAt(0) - 0xfee0))
      .replace(/　/g, ' ')
    return half.replace(/\s+/g, '').toUpperCase() === '株式会社TAKEFOUR'
      ? (CONFIG['勤務先名'] || half)
      : half
  }

  const access = [
    g('working_location_id_jp') ? `【勤務先】${normalizeCompany(g('working_location_id_jp'))}` : '',
    zipText,
    g('working_location_features_id_name'),
  ].filter(Boolean).join('\n')

  // --- 出力行を組み立て ---
  const out = {}
  OUT_COLUMNS.forEach(c => { out[c] = '' })

  out['企業ID'] = CONFIG['企業ID'] ?? ''
  out['求人ID'] = '' // 新規投稿のため空。更新時は既存の求人IDを入れる
  out['求人ステータス'] = CONFIG['求人ステータス'] ?? '下書き'
  out['勤務先名'] = clip(CONFIG['勤務先名'] || g('working_location_id_jp'), 100)
  out['求人タイトル'] = clip(g('title'), 75)

  const occ = mapOccupation(g('occupation_id_jp1'), g('title'), g('description'))
  if (!occ) warnings.push(`行${rowNo}: 職種区分を判定できず空欄（元:「${g('occupation_id_jp1')}」）— 手動設定が必要`)
  out['職種区分'] = occ
  out['雇用形態'] = employment
  out['仕事内容'] = clip(g('description'), MAX_CHARS['仕事内容'])
  out['この仕事のやりがい'] = appeal
  out['対象となる方'] = clip(g('personal'), MAX_CHARS['対象となる方'])
  out['求人の特徴'] = tags.join(',')
  out['勤務地_県_1'] = g('working_location_prefecture')
  out['勤務地_詳細_1'] = clip(g('working_location_city_area'), 100)
  if (access.length > 200) warnings.push(`行${rowNo}: 「交通手段・勤務地補足」が${access.length}字→200字に切り詰め`)
  out['交通手段・勤務地補足'] = clip(access, 200)
  out['給与タイプ'] = salaryType
  out['給与（下限）'] = g('minimum_salary')
  out['給与（上限）'] = g('maximum_salary')
  out['給与補足・福利厚生・受動喫煙防止措置など'] = benefits
  out['勤務時間・休日'] = schedule
  const tel = g('contact_phone')
  out['応募・選考についての必要項目'] = ENTRY_FORM_MAP[g('entry_form_type_jp')] ?? '基本情報'
  out['応募時の電話番号を必須入力にする'] = tel ? 'する' : 'しない'
  out['応募受付の電話番号'] = formatTel(tel)
  out['選考について'] = selection
  out['メモ'] = clip(g('job_offer_id') ? `AW:${g('job_offer_id')}` : '', MAX_CHARS['メモ'])

  return out
}

/**
 * 電話番号を数字とハイフンのみに整形。
 * 固定電話の市外局番は桁数が可変（03 / 029 / 0794 …）で機械的に判別できないため、
 * 区切りが確実な携帯・フリーダイヤルのみハイフンを入れ、それ以外は数字のまま返す。
 * （求人ボックスの仕様は「数字とハイフンのみ」なので数字のみでも適合する）
 */
function formatTel(raw) {
  const d = norm(raw).replace(/[^0-9]/g, '')
  if (!d) return ''
  if (d.length === 11 && /^0[789]0/.test(d)) return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}`
  if (d.length === 10 && /^(0120|0800)/.test(d)) return `${d.slice(0, 4)}-${d.slice(4, 7)}-${d.slice(7)}`
  return d
}

// ---------------------------------------------------------------
// 重複チェック（求人ボックスの重複判定対策）
// ---------------------------------------------------------------

/** 2文字組の Jaccard 係数で文章の類似度を測る */
function similarity(a, b) {
  const bigrams = s => {
    const set = new Set()
    const x = String(s).replace(/\s/g, '')
    for (let i = 0; i < x.length - 1; i++) set.add(x.slice(i, i + 2))
    return set
  }
  const A = bigrams(a), B = bigrams(b)
  if (!A.size || !B.size) return 0
  let inter = 0
  A.forEach(v => { if (B.has(v)) inter++ })
  return inter / (A.size + B.size - inter)
}

/** 元原稿どうしの重複を検出する（AirWork側にすでに重複がある場合の警告） */
function findSourceDuplicates(rows) {
  const dups = []
  for (let i = 0; i < rows.length; i++) {
    for (let j = i + 1; j < rows.length; j++) {
      const t = similarity(rows[i]['求人タイトル'], rows[j]['求人タイトル'])
      const b = similarity(rows[i]['仕事内容'], rows[j]['仕事内容'])
      // タイトル・本文のどちらかがほぼ一致していれば重複候補として拾う
      if (t > 0.9 || b > 0.9) {
        const which = t > 0.9 && b > 0.9 ? 'タイトル・本文とも' : (t > 0.9 ? 'タイトルが' : '本文が')
        dups.push(`元原稿${i + 1}「${rows[i]['求人タイトル']}」 ↔ 元原稿${j + 1}「${rows[j]['求人タイトル']}」: ` +
          `${which}ほぼ一致（タイトル${(t * 100).toFixed(0)}% / 本文${(b * 100).toFixed(0)}%）`)
      }
    }
  }
  return dups
}

/** 同一求人から作った変種どうしの類似度をレポートする */
function reportVariantSimilarity(rows) {
  const groups = {}
  rows.forEach(r => {
    const k = String(r['メモ'] || '').split('/')[0]
    ;(groups[k] = groups[k] || []).push(r)
  })
  let tSum = 0, bSum = 0, n = 0, tMax = 0, bMax = 0
  Object.values(groups).forEach(v => {
    for (let i = 0; i < v.length; i++) {
      for (let j = i + 1; j < v.length; j++) {
        const t = similarity(v[i]['求人タイトル'], v[j]['求人タイトル'])
        const b = similarity(v[i]['仕事内容'], v[j]['仕事内容'])
        tSum += t; bSum += b; n++
        tMax = Math.max(tMax, t); bMax = Math.max(bMax, b)
      }
    }
  })
  const uniqT = new Set(rows.map(r => r['求人タイトル'])).size
  const uniqB = new Set(rows.map(r => r['仕事内容'])).size
  return { n, tAvg: tSum / n, bAvg: bSum / n, tMax, bMax, uniqT, uniqB, total: rows.length }
}

// ---------------------------------------------------------------
// 既存求人の更新（求人IDの引き当て）
// ---------------------------------------------------------------

/** CSVテキストを行オブジェクトの配列にする */
function readCsv(filePath) {
  const text = fs.readFileSync(filePath, 'utf8').replace(/^﻿/, '')
  const wb = XLSX.read(text, { type: 'string', raw: true, FS: ',' })
  return XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { defval: '' })
}

/**
 * 管理画面からダウンロードしたCSVを読み、メモ欄をキーに 求人ID を引き当てる。
 * メモには "AW:12485617/経験者" のように 元求人ID＋ペルソナ が入っており、
 * 変種ごとに一意になるため突合キーとして使える。
 */
function buildIdMap(filePath) {
  const rows = readCsv(filePath)
  const map = new Map()
  const dupes = []
  rows.forEach(r => {
    const key = String(r['メモ'] ?? '').trim()
    const id = String(r['求人ID'] ?? '').trim()
    if (!key || !id) return
    if (map.has(key)) dupes.push(key)
    else map.set(key, id)
  })
  return { map, dupes, total: rows.length }
}

// ---------------------------------------------------------------
// 出力カラムの選定
// ---------------------------------------------------------------

/**
 * 新規投稿時に必ず送る必要があるカラム。
 * 出典: マニュアル p.28-30「新規必須」★印 ＋ 給与3点セット
 * 求人IDは「空欄にすることで新規扱い」になるため、空でも列自体は残す。
 */
const REQUIRED_COLUMNS = [
  '企業ID', '求人ID', '求人ステータス', '勤務先名', '求人タイトル', '雇用形態', '仕事内容',
  '勤務地_県_1', '給与タイプ', '給与（下限）', '給与（上限）',
  '応募・選考についての必要項目', '応募時の電話番号を必須入力にする',
]

/**
 * このツールが値を作らない列。出力から常に除外する。
 * 元データに対応する情報がないか、システム管理項目のため。
 */
const NEVER_FILLED = new Set([
  // 勤務地は _1 のみ使う（1求人1拠点）。_2〜_10 は拠点展開する場合に使う
  ...Array.from({ length: 9 }, (_, i) => [`勤務地_県_${i + 2}`, `勤務地_詳細_${i + 2}`]).flat(),
  // 5値カンマ形式の設問。元データに該当する情報がない
  '職場の雰囲気', '仕事のスタイル', '活かせる持ち味',
  // PR欄はペルソナ別に2枠までしか使わない
  'PR・職場情報_見出し_3', 'PR・職場情報_内容_3',
  'PR・職場情報_見出し_4', 'PR・職場情報_内容_4',
  // アカウントに紐づく写真IDは元データにない
  '写真ID',
  // システム管理項目。値を更新できない
  '求人作成日時',
  // 運用側で付けるラベル。ツールでは触らない
  '求人ラベル',
])

/**
 * 出力する列を決める。
 *
 * マニュアル p.11「変更したいカラムに絞ってアップロードすることが可能」に従い、
 * このツールが値を作らない列は送らない（更新時に既存値を空で消さないため）。
 *
 * ただし「その回のデータに値があるか」で判定してはいけない。
 * 例えば「選考について」はAirWork求人には値があるが、PDF起点の求人にはない。
 * 中身の有無で切り替えると出力のたびに列数が変わり、
 * 前回のファイルと並べたときに列がズレる。
 * そのため、値の有無ではなく「ツールが扱う列かどうか」で固定する。
 */
function selectColumns() {
  return OUT_COLUMNS.filter(c => REQUIRED_COLUMNS.includes(c) || !NEVER_FILLED.has(c))
}

// ---------------------------------------------------------------
// CSV出力（RFC4180 / BOM付きUTF-8）
// ---------------------------------------------------------------
function toCsv(rows, columns) {
  const esc = v => {
    const s = String(v ?? '')
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  // マニュアル本文は「求人の特徴」、記入例(p.42)は「特徴」と表記が割れているため
  // config.json の headerAliases で実際に通る名前に差し替えられるようにしている。
  const alias = CONFIG.headerAliases ?? {}
  const header = columns.map(c => esc(alias[c] ?? c)).join(',')
  const lines = [header]
  rows.forEach(r => lines.push(columns.map(c => esc(r[c])).join(',')))
  // 公式ダウンロードCSVに合わせ、BOM付きUTF-8 / 改行LF で出力する
  return '﻿' + lines.join('\n') + '\n'
}

// ---------------------------------------------------------------
// main
// ---------------------------------------------------------------
function main() {
  const input = process.argv[2]
  if (!input) {
    console.error('使い方: node scripts/airwork_to_kyujinbox.js <input.xlsx> [output.csv]')
    process.exit(1)
  }
  const output = process.argv[3] || input.replace(/\.xlsx?$/i, '') + '_求人ボックス.csv'

  const wb = XLSX.readFile(input)
  const ws = wb.Sheets[wb.SheetNames[0]]
  const raw = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' })
  const header = raw[0]
  const data = raw.slice(1).filter(r => r.some(c => norm(c)))
  const idx = buildIndex(header)

  const warnings = []
  const converted = data.map((r, i) => convertRow(r, idx, warnings, i + 2))

  // PDF等から手動でデータ化した求人を合流させる
  const extraPath = path.join(__dirname, 'extra_jobs.json')
  let extras = []
  if (fs.existsSync(extraPath)) {
    extras = JSON.parse(fs.readFileSync(extraPath, 'utf8')).map(e => {
      const row = {}
      OUT_COLUMNS.forEach(c => { row[c] = e[c] ?? '' })
      // 求人固有のPR指定はペルソナ複製側で使うので引き継ぐ
      if (e._pr) row._pr = e._pr
      // 共通設定は extra_jobs.json 側に書かせず、config.json から一律で入れる
      row['企業ID'] = CONFIG['企業ID'] ?? ''
      row['求人ステータス'] = CONFIG['求人ステータス'] ?? '下書き'
      if (!row['勤務先名']) row['勤務先名'] = CONFIG['勤務先名'] ?? ''
      return row
    })
  }

  const baseRows = [...converted, ...extras]

  // ペルソナ別に複製（1原稿 → 最大3原稿）
  let finalRows = baseRows.flatMap((r, i) => expand(r, warnings, i + 1))

  // --update に管理画面からダウンロードしたCSVを渡すと、
  // メモ欄で突合して 求人ID を埋め、新規投稿ではなく既存求人の更新として出力する。
  const updIdx = process.argv.indexOf('--update')
  let isUpdate = false
  let updatePath = null
  if (updIdx !== -1 && process.argv[updIdx + 1]) {
    isUpdate = true
    updatePath = process.argv[updIdx + 1]
    const { map, dupes, total } = buildIdMap(process.argv[updIdx + 1])
    let matched = 0
    const unmatched = []
    finalRows.forEach(r => {
      const id = map.get(String(r['メモ'] ?? '').trim())
      if (id) { r['求人ID'] = id; matched++ }
      else unmatched.push(r['メモ'] || r['求人タイトル'])
    })
    console.log(`🔄 更新モード: 既存${total}件と突合 → ${matched}/${finalRows.length}件に求人IDを引き当て`)
    if (dupes.length) console.log(`   ⚠️ メモが重複している既存求人: ${[...new Set(dupes)].join(', ')}`)
    if (unmatched.length) {
      console.log(`   ⚠️ 既存求人が見つからず新規投稿になる ${unmatched.length}件:`)
      unmatched.slice(0, 10).forEach(m => console.log(`      - ${m}`))
      if (unmatched.length > 10) console.log(`      …ほか${unmatched.length - 10}件`)
    }
    // 既存求人に手動で入れた値を空カラムで消さないよう、値のある列だけ送る
    const orphan = [...map.keys()].filter(k => !finalRows.some(r => String(r['メモ']).trim() === k))
    if (orphan.length) {
      console.log(`   ℹ️ 今回の出力に含まれない既存求人 ${orphan.length}件（そのまま残ります）:`)
      orphan.slice(0, 10).forEach(m => console.log(`      - ${m}`))
    }
  }

  // --new-only: 求人IDが引き当たらなかった行（＝新規投稿になる行）だけを出力する。
  // 既存求人に触れたくない場合に使う。
  const newOnly = process.argv.includes('--new-only')
  if (newOnly) {
    const before = finalRows.length
    finalRows = finalRows.filter(r => !String(r['求人ID'] ?? '').trim())
    console.log(`🆕 新規分のみ出力: ${before}件 → ${finalRows.length}件（既存求人は含めない）`)
    if (!finalRows.length) {
      console.log('   新規の行がありません。--update の突合で全件が既存求人に一致しています。')
      return
    }
  }

  // 出力カラムを決める。
  // --ref に管理画面からダウンロードしたCSVを渡すと、そのヘッダー行に完全に合わせる。
  const refIdx = process.argv.indexOf('--ref')
  const refPath = refIdx !== -1 && process.argv[refIdx + 1] ? process.argv[refIdx + 1] : null
  void updatePath

  let columns
  if (refPath) {
    const refText = fs.readFileSync(refPath, 'utf8').replace(/^﻿/, '')
    columns = (refText.split(/\r?\n/)[0] || '').split(',').map(c => c.replace(/^"|"$/g, '').trim()).filter(Boolean)
    const unknown = columns.filter(c => !OUT_COLUMNS.includes(c))
    const missing = REQUIRED_COLUMNS.filter(c => !columns.includes(c))
    console.log(`📎 参照CSVのヘッダーに合わせます (${columns.length}列)`)
    if (unknown.length) console.log(`   このツールが値を持たない列（空で出力）: ${unknown.join(', ')}`)
    if (missing.length) console.log(`   ⚠️ 参照CSVに必須列が見当たりません: ${missing.join(', ')}`)
    if (isUpdate && !newOnly && unknown.length) {
      console.log(`   ⚠️ 更新モードで空の列を送ると既存の値が消えます（マニュアルp.12）。`)
      console.log(`      手動で設定した項目がある場合は --ref を外して実行してください。`)
    }
  } else {
    columns = selectColumns()
    if (isUpdate) console.log(`   値のある列のみ送信します（既存値を空で上書きしないため）`)
  }

  fs.writeFileSync(output, toCsv(finalRows, columns), 'utf8')

  const dropped = OUT_COLUMNS.filter(c => !columns.includes(c))

  console.log(`✅ 変換完了`)
  console.log(`   入力  : ${path.basename(input)} (${header.length}列) ${converted.length}件`)
  if (extras.length) console.log(`   追加  : extra_jobs.json ${extras.length}件`)
  console.log(`   元原稿: ${baseRows.length}件 → ペルソナ複製後 ${finalRows.length}件`)
  console.log(`   出力  : ${output} (${columns.length}列)`)
  if (dropped.length) console.log(`   ※値が無いため出力しなかった列: ${dropped.join(', ')}`)

  // --- 重複対策レポート ---
  const s = reportVariantSimilarity(finalRows)
  console.log(`\n📊 重複判定リスク`)
  console.log(`   同一求人の変種間 タイトル類似度: 平均${(s.tAvg * 100).toFixed(1)}% / 最悪${(s.tMax * 100).toFixed(1)}%`)
  console.log(`   同一求人の変種間 本文類似度    : 平均${(s.bAvg * 100).toFixed(1)}% / 最悪${(s.bMax * 100).toFixed(1)}%`)
  console.log(`   ユニーク率 タイトル ${s.uniqT}/${s.total} ・ 本文 ${s.uniqB}/${s.total}`)

  const srcDups = findSourceDuplicates(baseRows)
  if (srcDups.length) {
    console.log(`\n🔁 元データ側にすでに重複があります（${srcDups.length}件）— 掲載前に統廃合を推奨:`)
    srcDups.forEach(d => console.log('   - ' + d))
  }

  if (warnings.length) {
    console.log(`\n⚠️  要確認 ${warnings.length}件:`)
    warnings.forEach(w => console.log('   - ' + w))
  }

  // --- 公式マニュアルのエラー条件で事前検証 ---
  const errors = validateAll(finalRows)
  if (errors.length) {
    console.log(`\n❌ アップロードするとエラーになる箇所 ${errors.length}件:`)
    const shown = errors.slice(0, 30)
    shown.forEach(e => console.log('   - ' + e))
    if (errors.length > shown.length) console.log(`   …ほか${errors.length - shown.length}件`)
    process.exitCode = 1
  } else {
    console.log(`\n✅ 公式マニュアル(ver.1.3)のエラー条件をすべてクリア`)
  }

  // 公式ガイドの推奨からの逸脱（エラーではない）
  const tips = advise(finalRows)
  if (tips.length) {
    const grouped = {}
    tips.forEach(t => { const k = t.replace(/^行\d+: /, '').replace(/\d+字/, 'N字'); grouped[k] = (grouped[k] || 0) + 1 })
    console.log(`\n💡 公式ガイドの推奨から外れている点:`)
    Object.entries(grouped).sort((a,b)=>b[1]-a[1]).forEach(([k,v]) => console.log(`   ${String(v).padStart(3)}件  ${k}`))
  }
}

/**
 * AirWorkのxlsxとextra_jobs.jsonから、求人ボックス形式の「元原稿」を作る。
 * ペルソナ複製はしない。他媒体向けの変換スクリプトから共通の入力として使う。
 */
function loadBaseRows(inputPath) {
  const wb = XLSX.readFile(inputPath)
  const raw = XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { header: 1, defval: '' })
  const idx = buildIndex(raw[0])
  const warnings = []
  const converted = raw.slice(1)
    .filter(r => r.some(c => norm(c)))
    .map((r, i) => convertRow(r, idx, warnings, i + 2))

  const extraPath = path.join(__dirname, 'extra_jobs.json')
  let extras = []
  if (fs.existsSync(extraPath)) {
    extras = JSON.parse(fs.readFileSync(extraPath, 'utf8')).map(e => {
      const row = {}
      OUT_COLUMNS.forEach(c => { row[c] = e[c] ?? '' })
      // 求人固有のPR指定はペルソナ複製側で使うので引き継ぐ
      if (e._pr) row._pr = e._pr
      row['企業ID'] = CONFIG['企業ID'] ?? ''
      row['求人ステータス'] = CONFIG['求人ステータス'] ?? '下書き'
      if (!row['勤務先名']) row['勤務先名'] = CONFIG['勤務先名'] ?? ''
      return row
    })
  }
  return { rows: [...converted, ...extras], warnings }
}

// 他の変換スクリプト（例: WORKGATE向け）から部品として読み込めるようにする
if (require.main === module) main()

module.exports = {
  OUT_COLUMNS, CONFIG,
  buildIndex, convertRow, cleanBoilerplate, readCsv, clip, norm,
  loadBaseRows,
}
