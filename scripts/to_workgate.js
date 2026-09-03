#!/usr/bin/env node
/**
 * AirWork等の求人 → WORKGATE（ワークゲート）取り込みCSV 変換
 *
 * 使い方:
 *   node scripts/to_workgate.js <AirWork.xlsx> [出力.csv]
 *
 * 仕様の出典: CSV対応表.xlsx（WG2025040001）の「基本情報」「完成例」および各対応表シート
 *
 * 【ターゲティングに関する重要な設計判断】
 * 「40代以下」「日本人」からの応募を増やしたいという要望に対し、以下の方針をとる。
 *
 * ・年齢: min_age / max_age は設定しない。
 *   これらは age_comp_cd（雇用対策法の例外事由）とセットで必須だが、
 *   TAKE FOURの求人は有期の派遣（temp_contract_period_type=2）であり、
 *   使える例外事由（1号・3号のイ・3号のロ）はいずれも「期間の定めのない労働契約」が要件。
 *   どの例外にも当てはまらないため、設定すると虚偽申告になる。
 *   代わりに「40代活躍中」「50代活躍中」「シニア・60代以上活躍中」「年齢不問」の
 *   アピールコードを付けないことで、その層への露出を避ける（販促タグの不選択なので適法）。
 *
 * ・国籍: 国籍による絞り込みは職業安定法3条で禁止されているため行わない。
 *   代わりに japanese_level_cd（日本語能力要件）を業務上の必要性に基づいて設定する。
 *   製造・軽作業は安全指示や作業手順書の理解が必要なため、N2〜N3相当を求めるのは正当な職務要件。
 *   ただし cd=9（ネイティブレベル限定・JLPT代替なし）は国籍による排除に近いため使わない。
 *   「留学生活躍中」「外国人活躍中」のアピールコードも付けない。
 */

const fs = require('fs')
const path = require('path')
const XLSX = require('xlsx')
const { loadBaseRows } = require('./airwork_to_kyujinbox')

const CONFIG = JSON.parse(fs.readFileSync(path.join(__dirname, 'config.json'), 'utf8'))
const WG = CONFIG.workgate ?? {}

// ---------------------------------------------------------------
// 出力カラム（CSV対応表「完成例」シートの順序）
// ---------------------------------------------------------------
const OUT = [
  'arrange_no', 'prepared_name', 'prepared_email', 'job_cd', 'emp_cd', 'sm_kwork', 'kwork',
  'pref_cd', 'city_cd', 'pref_nm', 'city_nm', 'place', 'line_cd', 'st_cd', 'st_nm', 'access',
  'hours', 'holiday', 'conditions', 'sal_cd', 'sal_etc', 'sal_min', 'sal_max',
  'japanese_level_cd', 'min_age', 'max_age', 'age_comp_cd', 'sex_cd', 'sex_comp_cd',
  'qualification1', 'qualification2', 'qualification3', 'apl_cd', 'other',
  'lm_num', 'lm_date', 'bid_price', 'image1_manage', 'image2_manage', 'concise_title',
  'referral_flag', 'referral_company', 'temp_company', 'store_name', 'of_zipcode',
  'fixed_overtime_pay', 'fixed_overtime_pay_detail', 'trial_period',
  'temp_contract_period_type', 'contract_period', 'insurance_cds', 'insurance',
  'preventsmoke', 'permit_edit_text', 'use_set_station',
]

// 文字数上限（基本情報シートより。全角制限を採用）
const 上限 = {
  arrange_no: 100, prepared_name: 20, prepared_email: 50, sm_kwork: 80, kwork: 1500,
  place: 50, st_nm: 40, access: 50, hours: 60, holiday: 50, conditions: 200, sal_etc: 30,
  qualification1: 40, qualification2: 40, qualification3: 40, other: 1500,
  concise_title: 20, referral_company: 40, temp_company: 40, store_name: 40,
  fixed_overtime_pay_detail: 200, trial_period: 200, contract_period: 200,
  insurance: 200, preventsmoke: 200,
}

// ---------------------------------------------------------------
// マスタ対応
// ---------------------------------------------------------------

// 雇用形態: 求人ボックス → emp_cd
const EMP = {
  '短期アルバイト': '0', 'アルバイト・パート': '1', '派遣社員': '2', '紹介予定派遣': '3',
  '正社員': '4', '契約社員': '5', '業務委託': '8', '新卒・インターン': '9',
}

// 給与タイプ → sal_cd
const SAL = { '時給': '1', '日給': '2', '月給': '3', '年収': '4', '固定報酬': '5' }

// 職種区分（求人ボックス26種）→ job_cd。実データに出る職種を優先して具体的なものを当てる
const JOB_BY_KEYWORD = [
  [/フォークリフト/, '130304'],                        // フォークリフト作業
  [/倉庫|ピッキング|仕分け|検品|梱包|入出庫|棚卸/, '130305'], // 物流・倉庫管理・検品・仕分け
  [/配送|ドライバー|宅配|運搬/, '130302'],              // ドライバー・宅配
  [/軽作業/, '130301'],                                // 軽作業
  [/警備/, '130501'],                                  // 警備員・警備関連
  [/施設管理|設備管理|ビル|清掃/, '130701'],            // ビル管理・ビル清掃・設備管理
  [/溶接|とび|鉄骨|解体/, '170101'],                    // とび職・鉄骨組立・溶接・解体関連
  [/検査|品質管理/, '061401'],                          // 機械・電気・電子の生産・品質管理・検査関連
  [/自動車/, '060401'],                                // 自動車業界（製造・部品組立・加工）
  [/製造|工場|組立|加工|オペレーター|鍛造|研磨|旋盤|フライス|成形/, '060402'], // 自動車業界以外（製造・部品組立・加工）
]
const JOB_BY_CATEGORY = {
  '工場・製造': '060402', '軽作業・倉庫作業': '130305', '配送・物流・交通': '130302',
  '警備・清掃・点検': '130501', '建築・土木・建設工事': '170101', '機械・電子エンジニア': '061401',
}

// 求人ボックスの「求人の特徴」→ WORKGATEのアピールコード
// ※ 502/503/506（40代・50代・60代活躍中）、312（年齢不問）、505/507（留学生・外国人活躍中）は
//    意図的に対応表から除外している（冒頭の設計判断を参照）
const APL = {
  '土日祝休みあり': '103', '深夜はたらく・夜勤': '107', 'シフト制': '109',
  'WワークOK': '115', '残業なし': '124', '短時間勤務OK（4時間以下）': '125',
  '土日のみOK': '127', '昼からはたらく': '128', '夕方・夜はたらく': '129',
  '学歴不問': '211', '大量募集': '214', '扶養内勤務OK': '215', '即日勤務OK': '217',
  '駅チカ・駅ナカ': '301', '交通費支給': '302', '車通勤OK': '303', '制服あり': '304',
  '髪型・髪色自由': '305', '服装自由': '305', '寮・社宅あり': '307', '託児所あり': '309',
  '週払いOK': '314', '研修あり': '317', 'まかない・食事補助あり': '318',
  '資格取得支援': '319', '社員登用あり': '321', '産休・育休取得実績あり': '324',
  'フルリモート': '326', '在宅勤務可': '326', '昇給あり': '328',
  '給与前払いOK': '329', '日払いOK': '330', '経験者歓迎': '331',
  '転勤なし': '413', '未経験歓迎': '501', '主婦・主夫歓迎': '504',
  '女性活躍': '510', '短期・単発': '126',
}

// 加入保険コード（1:健康保険 2:厚生年金 3:雇用保険 4:労災保険 と推定される並び）
const INSURANCE_ALL = '1/2/3/4'

// ---------------------------------------------------------------
// 対応表シートの読み込み（都道府県・市区町村）
// ---------------------------------------------------------------
function loadMasters(xlsxPath) {
  const wb = XLSX.readFile(xlsxPath)
  const rows = n => XLSX.utils.sheet_to_json(wb.Sheets[n], { header: 1, defval: '' }).slice(1)

  const pref = new Map()
  rows('都道府県対応表').forEach(r => { if (r[1]) pref.set(String(r[1]).trim(), String(r[0]).trim()) })

  // 市区町村は都道府県名とセットで引く（同名の市区町村があるため）
  const city = new Map()
  rows('市区町村対応表').forEach(r => {
    const [cd, nm, pn] = [String(r[0]).trim(), String(r[1]).trim(), String(r[2]).trim()]
    if (nm && pn) city.set(`${pn}|${nm}`, cd)
  })
  return { pref, city }
}

/**
 * 求人ボックスの「勤務地_詳細」（例: 日立市久慈町、那珂郡東海村舟石川）から
 * 市区町村マスタに一致する部分を切り出し、残りを番地(place)として返す。
 */
function splitCity(prefName, detail, cityMap) {
  const d = String(detail ?? '').trim()
  if (!d) return { cityNm: '', cityCd: '', place: '' }

  // 長い名前から順に前方一致を試す（「那珂郡東海村」が「那珂郡」より優先されるように）
  const candidates = [...cityMap.keys()]
    .filter(k => k.startsWith(prefName + '|'))
    .map(k => k.split('|')[1])
    .sort((a, b) => b.length - a.length)

  for (const nm of candidates) {
    if (d.startsWith(nm)) {
      return { cityNm: nm, cityCd: cityMap.get(`${prefName}|${nm}`), place: d.slice(nm.length).trim() }
    }
  }
  return { cityNm: '', cityCd: '', place: d }
}

// ---------------------------------------------------------------
// 変換
// ---------------------------------------------------------------
const clip = (v, max) => {
  const s = String(v ?? '').trim()
  if (!max || s.length <= max) return s
  const cut = s.slice(0, max)
  const br = Math.max(cut.lastIndexOf('\n'), cut.lastIndexOf('。'))
  return br > max * 0.6 ? cut.slice(0, br + 1) : cut
}

function pickJobCd(row) {
  const hay = [row['求人タイトル'], row['職種区分'], row['仕事内容']].join(' ')
  for (const [re, cd] of JOB_BY_KEYWORD) if (re.test(hay)) return cd
  return JOB_BY_CATEGORY[row['職種区分']] ?? ''
}

function convert(row, i, masters, warn) {
  const g = k => String(row[k] ?? '').trim()
  const o = {}
  OUT.forEach(c => { o[c] = '' })

  const prefNm = g('勤務地_県_1')
  const { cityNm, cityCd, place } = splitCity(prefNm, g('勤務地_詳細_1'), masters.city)
  if (prefNm && !masters.pref.get(prefNm)) warn.push(`行${i + 1}: 都道府県「${prefNm}」がマスタ外`)
  if (g('勤務地_詳細_1') && !cityCd) warn.push(`行${i + 1}: 市区町村を特定できず「${g('勤務地_詳細_1')}」`)

  const jobCd = pickJobCd(row)
  if (!jobCd) warn.push(`行${i + 1}: 職種コードを判定できず（職種区分「${g('職種区分')}」）`)

  const empCd = EMP[g('雇用形態').split(',')[0]] ?? ''
  const salCd = SAL[g('給与タイプ')] ?? ''
  const isHaken = empCd === '2' || empCd === '3'

  // アピールコード（40代以上・外国人向けのコードは APL に含めていない）
  const apl = [...new Set(
    g('求人の特徴').split(',').map(t => APL[t.trim()]).filter(Boolean)
  )]

  // 整理番号: 元求人IDを流用して一意にする
  const memo = g('メモ')
  o.arrange_no = clip(memo.replace(/[^0-9A-Za-z:_-]/g, '') || `JOB${i + 1}`, 上限.arrange_no)

  o.prepared_name = clip(WG.prepared_name ?? '', 上限.prepared_name)
  o.prepared_email = clip(WG.prepared_email ?? '', 上限.prepared_email)
  o.job_cd = jobCd
  o.emp_cd = empCd

  // キャッチコピー80字 / 仕事内容1500字
  o.sm_kwork = clip(g('この仕事のやりがい').split('\n').filter(Boolean).join(' ') || g('求人タイトル'), 上限.sm_kwork)
  o.kwork = clip(g('仕事内容'), 上限.kwork)

  o.pref_cd = masters.pref.get(prefNm) ?? ''
  o.city_cd = cityCd
  o.pref_nm = prefNm
  o.city_nm = cityNm
  o.place = clip(place, 上限.place)
  o.access = clip(g('交通手段・勤務地補足').split('\n').filter(Boolean).join(' '), 上限.access)

  // 勤務時間60字 / 休日50字 — 求人ボックスでは1つの欄なので分割する
  const sched = g('勤務時間・休日')
  const holidayIdx = sched.indexOf('【休日')
  o.hours = clip((holidayIdx > 0 ? sched.slice(0, holidayIdx) : sched).replace(/\n+/g, ' '), 上限.hours)
  o.holiday = clip((holidayIdx > 0 ? sched.slice(holidayIdx) : '').replace(/【休日・休暇】|\n+/g, ' ').trim()
    || g('求人の特徴').split(',').filter(t => /休/.test(t)).join('・'), 上限.holiday)

  o.conditions = clip(g('給与補足・福利厚生・受動喫煙防止措置など'), 上限.conditions)
  o.sal_cd = salCd
  o.sal_min = g('給与（下限）').replace(/[^0-9]/g, '')
  o.sal_max = g('給与（上限）').replace(/[^0-9]/g, '')

  // 日本語能力要件（業務上の必要性に基づく。国籍要件ではない）
  o.japanese_level_cd = String(WG.japanese_level_cd ?? '0')

  // 年齢・性別は設定しない（冒頭の設計判断を参照）
  o.min_age = ''
  o.max_age = ''
  o.age_comp_cd = ''
  o.sex_cd = ''
  o.sex_comp_cd = ''

  // 応募資格: 元原稿の「対象となる方」から要点を40字×3に振り分ける
  const quals = g('対象となる方').split('\n').map(s => s.trim())
    .filter(s => s && !/^[「」・]*$/.test(s) && s.length <= 40)
  o.qualification1 = clip(quals[0] ?? '', 上限.qualification1)
  o.qualification2 = clip(quals[1] ?? '', 上限.qualification2)
  o.qualification3 = clip(quals[2] ?? '', 上限.qualification3)

  o.apl_cd = apl.join('/')
  o.other = clip(g('選考について'), 上限.other)

  o.bid_price = String(WG.bid_price ?? '')
  o.concise_title = clip(g('職種区分') || g('求人タイトル'), 上限.concise_title)

  // 派遣なので referral_flag は不要（短期アルバイト/アルバイト/正社員/契約社員のみ必須）
  o.referral_flag = isHaken ? '' : '0'
  o.temp_company = isHaken ? clip(WG.temp_company ?? '', 上限.temp_company) : ''
  o.store_name = clip(WG.store_name ?? '', 上限.store_name)

  // 郵便番号はハイフンなし7桁。交通手段欄に〒付きで入っているので抜き出す
  const zip = (g('交通手段・勤務地補足').match(/〒\s*(\d{3})-?(\d{4})/) ?? [])
  o.of_zipcode = zip.length ? zip[1] + zip[2] : ''

  o.fixed_overtime_pay = '0'
  o.trial_period = clip(WG.trial_period ?? '', 上限.trial_period)

  // 派遣の雇用期間種別（1:無期 2:有期）
  o.temp_contract_period_type = isHaken ? String(WG.temp_contract_period_type ?? '2') : ''
  o.contract_period = clip(WG.contract_period ?? '', 上限.contract_period)

  const hasInsurance = /社会保険完備/.test(g('求人の特徴'))
  o.insurance_cds = hasInsurance ? INSURANCE_ALL : ''
  o.insurance = clip(hasInsurance ? (WG.insurance ?? '社会保険完備') : '', 上限.insurance)

  o.preventsmoke = clip(WG.preventsmoke ?? '', 上限.preventsmoke)
  o.permit_edit_text = String(WG.permit_edit_text ?? '0')
  o.use_set_station = String(WG.use_set_station ?? 'false')

  return o
}

// ---------------------------------------------------------------
// 検証
// ---------------------------------------------------------------
const REQUIRED = ['arrange_no', 'job_cd', 'emp_cd', 'sm_kwork', 'kwork', 'pref_cd', 'city_cd',
  'hours', 'holiday', 'sal_cd', 'sal_min', 'japanese_level_cd', 'image1_manage']

function validate(rows) {
  const errs = []
  const seen = new Set()
  rows.forEach((r, i) => {
    const at = m => errs.push(`行${i + 1}: ${m}`)
    REQUIRED.forEach(k => { if (!String(r[k] ?? '').trim()) at(`${k} が空（必須）`) })
    if (seen.has(r.arrange_no)) at(`arrange_no「${r.arrange_no}」が重複`)
    seen.add(r.arrange_no)
    Object.entries(上限).forEach(([k, max]) => {
      const v = String(r[k] ?? '')
      if (v.length > max) at(`${k} が${v.length}字（上限${max}字）`)
    })
    if (r.sal_cd === '5' && !r.sal_etc) at('sal_cd=5（その他）だが sal_etc が空')
    if ((r.min_age || r.max_age) && !r.age_comp_cd) at('年齢要件があるのに age_comp_cd が空')
    if (r.sex_cd && !r.sex_comp_cd) at('性別要件があるのに sex_comp_cd が空')
    if (r.of_zipcode && !/^\d{7}$/.test(r.of_zipcode)) at(`of_zipcode「${r.of_zipcode}」が7桁の数字でない`)
  })
  return errs
}

// ---------------------------------------------------------------
// CSV出力
// ---------------------------------------------------------------
function toCsv(rows) {
  const esc = v => {
    const s = String(v ?? '')
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return '﻿' + [OUT.join(','), ...rows.map(r => OUT.map(c => esc(r[c])).join(','))].join('\n') + '\n'
}

// ---------------------------------------------------------------
function main() {
  const input = process.argv[2]
  if (!input) {
    console.error('使い方: node scripts/to_workgate.js <AirWork.xlsx> [出力.csv]')
    process.exit(1)
  }
  const output = process.argv[3] || 'workgate.csv'
  const masterPath = WG.master_xlsx ?? '/Users/masakatsu/Downloads/CSV対応表.xlsx'

  const masters = loadMasters(masterPath)
  const { rows: base, warnings } = loadBaseRows(input)

  const warn = []
  const out = base.map((r, i) => convert(r, i, masters, warn))

  fs.writeFileSync(output, toCsv(out), 'utf8')

  console.log('✅ WORKGATE形式へ変換')
  console.log(`   元原稿: ${base.length}件 → 出力 ${out.length}件 / ${OUT.length}列`)
  console.log(`   出力  : ${output}`)
  console.log(`\n🔒 ターゲティング設定`)
  console.log(`   日本語能力要件 japanese_level_cd = ${out[0]?.japanese_level_cd}` +
    ` （0:設定なし / 1:N1以上 / 2:N2以上 / 3:N3以上 / 9:ネイティブ限定）`)
  console.log(`   年齢要件 min_age/max_age = 未設定（有期派遣は雇対法の例外事由に該当しないため）`)
  console.log(`   40代・50代・60代活躍中／年齢不問／留学生・外国人活躍中 のアピールコードは付与しない`)

  const errs = validate(out)
  if (warn.length) {
    console.log(`\n⚠️  マッピング要確認 ${warn.length}件:`)
    warn.slice(0, 15).forEach(w => console.log('   - ' + w))
    if (warn.length > 15) console.log(`   …ほか${warn.length - 15}件`)
  }
  if (errs.length) {
    console.log(`\n❌ 仕様違反 ${errs.length}件:`)
    const g = {}
    errs.forEach(e => { const k = e.replace(/^行\d+: /, ''); g[k] = (g[k] || 0) + 1 })
    Object.entries(g).sort((a, b) => b[1] - a[1]).forEach(([k, v]) => console.log(`   ${String(v).padStart(3)}件  ${k}`))
    process.exitCode = 1
  } else {
    console.log(`\n✅ 必須項目・文字数・コード整合性をすべてクリア`)
  }
  if (warnings.length) console.log(`\n（元原稿側の注意 ${warnings.length}件は求人ボックス変換と同じ）`)
}

if (require.main === module) main()
module.exports = { convert, loadMasters, OUT }
