/**
 * 1原稿 → 3原稿（ターゲットペルソナ別）に複製する。
 *
 * 【重要な設計方針】
 *
 * 1. 年齢・性別による絞り込みは一切書かない
 *    - 雇用対策法10条: 募集・採用時の年齢制限は原則禁止
 *    - 男女雇用機会均等法5条: 募集・採用時の性別限定は原則禁止
 *    若年層からの応募は「制限」ではなく「訴求内容」で寄せる。
 *
 * 2. 原稿に無い事実は足さない
 *    装飾文言・訴求文はすべて元原稿から抽出した fact に紐づく場合のみ出力する。
 *
 * 3. 重複判定を避けるため、変種間で文面を実質的に変える
 *    - タイトル: 構文テンプレート・バッジ・末尾修飾をすべて変える
 *    - 仕事内容: リード文／ポイント列挙／締めをペルソナ別に差し替え、
 *                元原稿の装飾ヘッダーは1変種にのみ残す
 *    - PR・職場情報欄: ペルソナごとに異なる既存情報を配置
 *    ※ 事実は変えず「どの事実をどの順で見せるか」で差を作る。
 */

const PERSONAS = [
  {
    key: '未経験',
    label: '未経験・キャリアチェンジ層',
    requires: f => f.inexperienced,
    lead: '未経験からスタートできるお仕事です。',
    aboutLead: '経験がなくても応募いただけます。\nこれから新しい仕事を覚えていきたい方を歓迎します。',
    bodyHeading: '未経験の方へ',
    bodyLead: '経験は問いません。\nはじめての方でも取り組んでいただけるお仕事です。',
    pointsHeading: 'この求人のポイント',
    closing: '「まずは話を聞いてみたい」という段階でも構いません。\nお気軽にご応募ください。',
    badgePriority: ['未経験歓迎', '資格取得支援あり', '制服あり', '社会保険完備', '社員登用あり', '髪型・髪色自由', '日勤のみ'],
    prSlots: [
      { title: 'はじめての方へ', from: '対象となる方' },
      { title: '勤務時間・休日について', from: '勤務時間・休日' },
    ],
    keepOriginalHeader: false,
    extraTags: ['未経験歓迎'],
  },
  {
    key: '経験者',
    label: '経験者・スキル活用層',
    requires: f => f.experienced,
    lead: 'これまでの経験を活かせるお仕事です。',
    aboutLead: 'これまでのご経験を活かして働きたい方を歓迎します。',
    bodyHeading: '経験を活かせる環境です',
    bodyLead: 'これまでに培った経験やスキルを活かして働いていただけます。',
    pointsHeading: '就業条件',
    closing: 'ご経験の内容については、面接時に詳しくお伺いします。',
    badgePriority: ['経験者優遇', '資格取得支援あり', '残業代別途支給', '転勤なし', '長期休暇あり', '社会保険完備'],
    prSlots: [
      { title: '活かせる経験', from: '対象となる方' },
      { title: '待遇・福利厚生', from: '給与補足・福利厚生・受動喫煙防止措置など' },
    ],
    keepOriginalHeader: false,
    extraTags: ['経験者歓迎'],
  },
  {
    key: '収入重視',
    label: '収入・待遇重視層',
    requires: () => true,
    lead: '収入と働きやすさを両立できるお仕事です。',
    aboutLead: 'しっかり稼ぎたい方、腰を据えて長く働きたい方を歓迎します。',
    bodyHeading: '給与・待遇について',
    bodyLead: '収入面と働きやすさについてまとめました。',
    pointsHeading: '給与・待遇のポイント',
    closing: '収入面のご相談も承ります。まずはお問い合わせください。',
    badgePriority: ['週払いOK', '残業代別途支給', '社会保険完備', '車通勤OK'],
    prSlots: [
      { title: '給与・手当について', from: '給与補足・福利厚生・受動喫煙防止措置など' },
      { title: 'お仕事の時間', from: '勤務時間・休日' },
    ],
    keepOriginalHeader: true, // 元原稿の給与訴求ヘッダーはこの変種にのみ残す
    extraTags: [],
  },
  {
    key: '働き方重視',
    label: '働き方・プライベート重視層',
    requires: f => f.weekendOff || f.dayShift || f.longHoliday,
    lead: 'プライベートと両立しやすい働き方ができます。',
    aboutLead: '仕事とプライベートを両立しながら働きたい方を歓迎します。',
    bodyHeading: '働き方について',
    bodyLead: '勤務時間と休日についてご案内します。',
    pointsHeading: '働き方のポイント',
    closing: 'シフトや勤務条件については、面接時にご相談ください。',
    badgePriority: ['土日祝休み', '日勤のみ', '長期休暇あり', '車通勤OK', '転勤なし'],
    prSlots: [
      { title: '休日・勤務時間', from: '勤務時間・休日' },
      { title: '通勤・アクセス', from: '交通手段・勤務地補足' },
    ],
    keepOriginalHeader: false,
    extraTags: [],
  },
]

// 求人タイトルは桁区切りカンマも使えないため、数字はそのまま出す
const yen = n => String(n ?? '').replace(/[^0-9]/g, '')

/**
 * 求人タイトルで使用できる記号は「・」「／」「「」」のみ。
 * それ以外の記号は変換するか取り除く。
 * ※この制限はタイトルのみ。仕事内容やPR欄では「！」なども使える。
 */
function sanitizeTitle(text) {
  return String(text ?? '')
    // 括弧類は鉤括弧に寄せる
    .replace(/[(（【〔［[]/g, '「')
    .replace(/[)）】〕］\]]/g, '」')
    // 区切り記号はスラッシュ・中黒に寄せる
    .replace(/[/｜|]/g, '／')
    .replace(/[･、,，]/g, '・')
    .replace(/[＆&]/g, '・')
    // 上記以外で許可されていない文字を除去（かな・漢字・英数・長音・許可記号のみ残す）
    .replace(/[^一-鿿぀-ゟ゠-ヿA-Za-z0-9ーｰ・／「」]/g, '')
    // 記号の重複・端の記号を整理
    .replace(/・{2,}/g, '・')
    .replace(/／{2,}/g, '／')
    .replace(/^[・／]+|[・／]+$/g, '')
    .replace(/「\s*」/g, '')
}

/** 元原稿から装飾文言の材料になる fact を抽出する（すべて実データ裏付けあり） */
function extractFacts(row) {
  const tags = String(row['求人の特徴'] || '').split(',').map(s => s.trim()).filter(Boolean)
  const has = t => tags.includes(t)
  const body = [row['勤務時間・休日'], row['給与補足・福利厚生・受動喫煙防止措置など'], row['仕事内容']].join('\n')

  return {
    inexperienced: has('未経験歓迎'),
    experienced: has('経験者歓迎'),
    weekendOff: has('土日祝休みあり') || has('週休2日制'),
    carOk: has('車通勤OK'),
    insurance: has('社会保険完備'),
    weeklyPay: has('週払いOK'),
    uniform: has('制服あり'),
    hairFree: has('髪型・髪色自由'),
    noTransfer: has('転勤なし'),
    socialPromo: has('社員登用あり'),
    qualSupport: has('資格取得支援'),
    dayShift: !has('深夜はたらく・夜勤'),
    longHoliday: /長期休暇|GW|夏季|年末年始/.test(body),
    overtimePremium: /割増|％増|%増|残業代/.test(body),
    salaryType: row['給与タイプ'] || '',
    salaryMin: row['給与（下限）'] || '',
    city: row['勤務地_詳細_1'] || '',
    pref: row['勤務地_県_1'] || '',
    tags,
  }
}

const salaryBadge = f => {
  const a = yen(f.salaryMin)
  return f.salaryType && a ? `${f.salaryType}${a}円` : ''
}

/** fact に裏付けのあるバッジを全部集める */
function badgePool(f) {
  const p = {}
  if (f.inexperienced) p['未経験歓迎'] = true
  if (f.experienced) p['経験者優遇'] = true
  if (f.weekendOff) p['土日祝休み'] = true
  if (f.dayShift) p['日勤のみ'] = true
  if (f.weeklyPay) p['週払いOK'] = true
  if (f.carOk) p['車通勤OK'] = true
  if (f.longHoliday) p['長期休暇あり'] = true
  if (f.insurance) p['社会保険完備'] = true
  if (f.uniform) p['制服あり'] = true
  if (f.hairFree) p['髪型・髪色自由'] = true
  if (f.noTransfer) p['転勤なし'] = true
  if (f.socialPromo) p['社員登用あり'] = true
  if (f.qualSupport) p['資格取得支援あり'] = true
  if (f.overtimePremium) p['残業代別途支給'] = true
  return p
}

/**
 * 変種ごとにバッジを排他的に割り当てる。
 * 同じバッジが複数の変種に出ると重複判定を受けやすくなるため、使い回さない。
 * 給与バッジだけは訴求力が高いので「収入重視」に優先的に渡す。
 */
function allocateBadges(personas, f) {
  const pool = badgePool(f)
  const used = new Set()
  const sal = salaryBadge(f)
  const salOwner = personas.find(p => p.key === '収入重視') ?? personas[0]
  const result = new Map()

  personas.forEach(p => {
    const picked = []
    if (p === salOwner && sal) picked.push(sal)
    p.badgePriority.forEach(b => {
      if (picked.length >= 2) return
      if (pool[b] && !used.has(b)) { picked.push(b); used.add(b) }
    })
    // 足りなければプールの残りから補う
    if (picked.length < 2) {
      Object.keys(pool).forEach(b => {
        if (picked.length >= 2) return
        if (!used.has(b)) { picked.push(b); used.add(b) }
      })
    }
    // それでも空なら給与バッジで埋める
    if (!picked.length && sal) picked.push(sal)
    result.set(p.key, picked)
  })
  return result
}

/**
 * 変種ごとに異なる構文でタイトルを組む。
 * 使用できる記号は「・」「／」「「」」のみのため、この3パターンで構造差を作る。
 *   0: 「バッジ」職種名
 *   1: 職種名「勤務地」／バッジ
 *   2: バッジ／職種名
 */
const TITLE_TEMPLATES = [
  (stem, b) => `「${b.join('・')}」${stem}`,
  (stem, b) => `${stem}／${b.join('・')}`,
  (stem, b) => `${b.join('・')}／${stem}`,
]

/**
 * 求人タイトルの目標文字数。
 * CSVの上限は75文字だが、公式ガイド（虎の巻）では
 * 「30文字以内。長すぎると検索結果画面で見切れる」とされているため30を目標にする。
 * ただしこれは推奨であって必須ではない。
 */
const TITLE_TARGET_LEN = 30
// 差別化を確保するために許容する上限。ここまではバッジを残すことを優先する
const TITLE_SOFT_LIMIT = 38

/**
 * 職種名が長くバッジが入らない場合に、職種名側を圧縮する。
 * 「工場内作業スタッフ「フォークリフトオペレーター」」のように
 * 総称＋具体の二段構えになっている場合、具体的な方を残す。
 */
function compactStem(stem) {
  const m = String(stem).match(/^(.*?)「(.+?)」$/)
  if (!m) return stem
  const [, prefix, inner] = m
  if (!prefix || !inner) return stem
  return inner.length > prefix.length ? inner : prefix
}

function buildTitle(base, badges, variantIndex, f, maxLen = TITLE_TARGET_LEN) {
  const cleanBase = sanitizeTitle(base)
  const cleanBadges = badges.map(sanitizeTitle).filter(Boolean)

  // 変種1だけ勤務地を添えて、基幹部分そのものにも差をつける。
  // 元タイトルが既に鉤括弧で終わる場合は「」が連続して読みにくいので、
  // 勤務地は括弧で括らずバッジ側の先頭に回す。
  // 勤務地に番地まで入っている原稿があるため、タイトルでは町名までに留める。
  const cityName = String(f.city ?? '').replace(/[0-9０-９][0-9０-９\-－‐ー番地号の]*$/, '').trim()
  const city = cityName ? sanitizeTitle(cityName) : ''
  const baseEndsWithBracket = /」$/.test(cleanBase)
  let stem = cleanBase
  let finalBadges = cleanBadges
  if (variantIndex === 1 && city) {
    if (baseEndsWithBracket) finalBadges = [city, ...cleanBadges]
    else stem = `${cleanBase}「${city}」`
  }

  const tpl = TITLE_TEMPLATES[variantIndex % TITLE_TEMPLATES.length]
  const title = finalBadges.length ? tpl(stem, finalBadges) : stem
  if (title.length <= maxLen) return title

  // 目標超過時はバッジを1つに減らす
  const short = finalBadges.length ? tpl(stem, [finalBadges[0]]) : stem
  if (short.length <= maxLen) return short

  // 30字は推奨であって必須ではない。
  // 一方でバッジが1つも入らないと変種間のタイトルが同一になり、
  // 重複判定という実害につながる。よって差別化を優先し、多少の超過は許容する。
  if (finalBadges.length && short.length <= TITLE_SOFT_LIMIT) return short

  // それでも長い場合だけ職種名を圧縮する
  const compact = compactStem(stem)
  if (compact !== stem && finalBadges.length) {
    const retry = tpl(compact, [finalBadges[0]])
    if (retry.length <= TITLE_SOFT_LIMIT) return retry
  }

  // 職種名だけで超える場合は職種名を優先する。
  // 途中で切ると意味が壊れるため、CSVの上限75文字までは許容する。
  return stem.length <= 75 ? stem : stem.slice(0, 75)
}

/** ペルソナ別の「この仕事のやりがい」（140字以内） */
function buildAppeal(persona, f, badges, fallback) {
  const pts = [...badges]
  const add = (cond, label) => { if (cond && !pts.includes(label)) pts.push(label) }

  // 「未経験歓迎」がバッジに入っていれば「経験不問」は重複なので足さない
  if (persona.key === '未経験' && !badges.includes('未経験歓迎')) add(f.inexperienced, '経験不問')
  if (persona.key === '経験者' && !badges.includes('経験者優遇')) add(f.experienced, '経験を活かせます')
  add(f.weekendOff, '土日祝休み')
  add(f.dayShift, '日勤のみ')
  add(f.insurance, '社会保険完備')

  const uniq = [...new Set(pts)]
  const text = uniq.length ? `${persona.lead}\n${uniq.join('／')}` : fallback
  return text.length <= 140 ? text : text.slice(0, 140)
}

/** ペルソナ別の「対象となる方」（元本文は保持したまま前置きを差し替え） */
function buildAbout(original, persona, maxLen = 1000) {
  const body = String(original || '').trim()
  const text = body ? `${persona.aboutLead}\n\n${body}` : persona.aboutLead
  return text.length <= maxLen ? text : text.slice(0, maxLen)
}

/**
 * 装飾ヘッダーのブロックかどうか。
 * すべての行が《…》や＼＼…／／の飾り行である場合だけ true を返す。
 *
 * 「《株式会社TAKE FOUR》/ 2024年7月設立 / ※労働者派遣業(派)08-300957」のように
 * 飾り行で始まっていても中身が実質的なブロックは残す。
 * とくに労働者派遣業の許可番号は労働者派遣法上の表示事項なので絶対に削除しない。
 */
const 法定表示 = /労働者派遣業|派遣事業|許可番号|[(（]派[)）]|有料職業紹介/
const isDecorLine = l => /^《.*》/.test(l) || /^＼＼.*／／$/.test(l)

const isDecorHeader = b => {
  const t = String(b).trim()
  if (法定表示.test(t)) return false
  const lines = t.split('\n').map(s => s.trim()).filter(Boolean)
  return lines.length > 0 && lines.every(isDecorLine)
}

/**
 * 仕事内容をペルソナ別に組み替える。
 * 事実は一切変えず、リード文・ポイント列挙・締め・ブロック順で差を作る。
 */
function buildBody(original, persona, f, badges, maxLen = 10000) {
  const blocks = String(original || '').split(/\n\s*\n/).map(b => b.trim()).filter(Boolean)
  const core = blocks.filter(b => persona.keepOriginalHeader || !isDecorHeader(b))

  // ペルソナ別リード
  const lead = [`【${persona.bodyHeading}】`, persona.bodyLead].filter(Boolean).join('\n')

  // ペルソナ別ポイント（並び順がペルソナごとに変わる）
  const pts = []
  const push = (cond, label) => { if (cond) pts.push(`・${label}`) }
  if (persona.key === '収入重視') {
    const s = salaryBadge(f)
    if (s) pts.push(`・${s}`)
    push(f.overtimePremium, '残業代は別途支給')
    push(f.weeklyPay, '週払いOK')
    push(f.insurance, '社会保険完備')
  } else if (persona.key === '働き方重視') {
    push(f.weekendOff, '土日祝休み')
    push(f.dayShift, '日勤のみ')
    push(f.longHoliday, '長期休暇あり')
    push(f.carOk, '車通勤OK')
  } else if (persona.key === '未経験') {
    push(f.inexperienced, '経験不問')
    push(f.qualSupport, '資格取得を支援します')
    push(f.uniform, '制服の貸与あり')
    push(f.socialPromo, '社員登用の実績あり')
    push(f.insurance, '社会保険完備')
  } else {
    push(f.experienced, '経験を活かせる業務です')
    push(f.qualSupport, '資格取得を支援します')
    push(f.overtimePremium, '残業代は別途支給')
    push(f.noTransfer, '転勤なし')
    push(f.longHoliday, '長期休暇あり')
  }
  const points = pts.length ? [`【${persona.pointsHeading}】`, ...pts].join('\n') : ''

  const text = [lead, points, ...core, persona.closing].filter(Boolean).join('\n\n')
  return text.length <= maxLen ? text : text.slice(0, maxLen)
}

/**
 * PR・職場情報欄を埋める。
 *
 * extra_jobs.json に `_pr` が指定されていれば、それを先頭スロットに置く。
 * その求人固有の強い訴求（資格取得支援など）を、ペルソナ共通で前面に出すため。
 * 残りのスロットをペルソナ別の既存フィールドで埋める。
 *
 * 出力するのはスロット1・2のみ（3・4は列自体を出力しない）。
 */
const PR_SLOT_COUNT = 2

function fillPr(target, source, persona) {
  const fixed = Array.isArray(source._pr) ? source._pr : []
  const entries = []

  fixed.forEach(p => {
    const title = String(p['見出し'] ?? '').trim()
    const content = String(p['内容'] ?? '').trim()
    if (title && content) entries.push({ title, content })
  })

  persona.prSlots.forEach(slot => {
    const content = String(source[slot.from] || '').trim()
    if (content) entries.push({ title: slot.title, content })
  })

  entries.slice(0, PR_SLOT_COUNT).forEach((e, i) => {
    target[`PR・職場情報_見出し_${i + 1}`] = e.title.slice(0, 100)
    target[`PR・職場情報_内容_${i + 1}`] = e.content.slice(0, 1000)
  })
}

/** 1レコード → ペルソナ別に3レコードへ展開 */
function expand(row, warnings, rowNo) {
  const f = extractFacts(row)
  const baseTitle = row['求人タイトル'] || ''

  const chosen = PERSONAS.filter(p => p.requires(f)).slice(0, 3)
  if (chosen.length < 3) {
    warnings.push(`行${rowNo}「${baseTitle}」: ペルソナが${chosen.length}件しか成立せず（${chosen.map(p => p.key).join('・')}）`)
  }

  const badgeMap = allocateBadges(chosen, f)

  return chosen.map((p, i) => {
    const r = { ...row }
    delete r._facts; delete r._source; delete r._note; delete r._pr

    const badges = badgeMap.get(p.key) ?? []
    r['求人タイトル'] = buildTitle(baseTitle, badges, i, f)
    r['仕事内容'] = buildBody(row['仕事内容'], p, f, badges)
    r['この仕事のやりがい'] = buildAppeal(p, f, badges, row['この仕事のやりがい'] || '')
    r['対象となる方'] = buildAbout(row['対象となる方'], p)

    // タグは変種ごとに並び順を変える（内容は原稿の裏付けどおり）
    const tags = [...f.tags]
    p.extraTags.forEach(t => { if (!tags.includes(t)) tags.push(t) })
    const head = tags.filter(t => badges.some(b => t.includes(b) || b.includes(t)))
    r['求人の特徴'] = [...new Set([...head, ...tags])].join(',')

    fillPr(r, row, p)
    r['メモ'] = String(`${row['メモ'] || ''}/${p.key}`).slice(0, 30)
    return r
  })
}

module.exports = { expand, extractFacts, PERSONAS }
