/**
 * 応募通知メールを検知して GitHub Actions を起動する。
 *
 * ATS(求人部) と 求人ボックス の両方を扱う。
 * トリガーは2つ設定する:
 *   checkAtsMail        … 1分おき
 *   checkKyujinboxMail  … 1分おき
 *
 * 設置手順は apps_script/README.md を参照。
 *
 * 設計上の注意:
 *   - ラベル付けは起動成功後に行う。失敗したメールは次回再試行される。
 *   - 同時に複数の応募が来ても、対象単位でまとめて1回だけ起動する。
 *   - 管理対象外のメールは専用ラベルを付けて静かに無視する。
 */

// ===== 設定 =====

/** GitHub の Personal Access Token（Contents: Read and write） */
const GITHUB_TOKEN = 'ここにトークンを貼る';

const REPO = 'nakatsuka-m-al/kyujin-box-rpa';

/** 書き込み先。検証中は 'test'、本番に切り替えるときに 'production' にする */
const TARGET_ATS = 'production';
const TARGET_KYUJINBOX = 'test';

/**
 * ATS: 求人URL のスラッグ → GitHub 側のアカウント名。
 * このメールボックスには他社の通知も届くため、ここに無いものは対象外として無視する。
 * 対象を増やすときは GitHub Secrets にも認証情報を追加すること。
 */
const ATS_ACCOUNT_BY_SLUG = {
  blaze:  'ats1',
  blaze2: 'ats2',
};

/**
 * 検索条件。送信元だけでは足りない。
 * 同じ送信元から「掲載開始のお知らせ」など応募と無関係な通知も届き、
 * それらにも【アカウントID】が含まれているため、件名で応募通知に限定する。
 */
const ATS_QUERY = 'from:do-not-reply@kyujinbu.com subject:新着応募';

/**
 * 求人ボックスの通知は notice@kyujinbox.com から直接ではなく、
 * blaze-ltd.com の転送リスト経由で届く。Gmail はリストのアドレスを
 * From として扱うため from:notice@kyujinbox.com では検索できない。
 *
 * 同じメールが両方のリストに重複配信されるが、
 * アカウントID単位でまとめるため起動は1回だけになる。
 *
 * 転送リストを増やしたときはここに追加すること
 * （漏れても定期実行の全件同期が保険になる）。
 */
const KYUJINBOX_QUERY =
  'from:(kb_announce@blaze-ltd.com OR oubopay@blaze-ltd.com)' +
  ' subject:新着応募のお知らせ';

const LABEL_DONE = 'RPA処理済み';
const LABEL_SKIPPED = 'RPA対象外';      // 他社宛。正常なので通知しない
const LABEL_NEEDS_CHECK = 'RPA要確認';  // 形式が変わった可能性。要調査

/** 取りこぼし対策で少し広めに検索する */
const SEARCH_WINDOW = 'newer_than:2d';

/**
 * 1回の実行で起動する上限。
 * 同時に大量のログインが走ると、対象サイト側でボット検知される恐れがある。
 * 上限を超えた分はラベルを付けないため、次回（1分後）に持ち越される。
 */
const MAX_DISPATCH_PER_RUN = 2;

// ===== エントリポイント =====

function checkAtsMail() {
  processMails({
    name: 'ATS',
    query: ATS_QUERY,
    eventType: 'ats-applicant',
    target: TARGET_ATS,
    // 求人URL は https://kyujinbu.com/{スラッグ}/detail/post_NNN.html の形
    extract: function (body) {
      const m = body.match(/kyujinbu\.com\/([A-Za-z0-9_-]+)\/detail\//);
      if (!m) return null;
      const slug = m[1];
      const account = ATS_ACCOUNT_BY_SLUG[slug];
      return account ? { key: account, label: slug, payload: { account: account } }
                     : { key: null, label: slug };
    },
  });
}

function checkKyujinboxMail() {
  processMails({
    name: '求人ボックス',
    query: KYUJINBOX_QUERY,
    eventType: 'kyujinbox-applicant',
    target: TARGET_KYUJINBOX,
    // 本文の 【アカウントID】 6617-5385 を拾う
    extract: function (body) {
      const m = body.match(/【アカウントID】[\s　]*([0-9]{4}-[0-9]{4})/);
      if (!m) return null;
      const id = m[1];
      // 求人ボックスはマスター配下の全アカウントが対象なので絞り込まない。
      // 管理外のIDが来た場合は GitHub 側で「一覧に無い」と判定され安全に終了する。
      return { key: id, label: id, payload: { account_id: id } };
    },
  });
}

// ===== 共通処理 =====

function processMails(config) {
  // 1分間隔で起動するため、前回の処理が終わる前に重ならないようにする
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) {
    console.log(`[${config.name}] 前回の処理が実行中のためスキップ`);
    return;
  }

  try {
    const threads = GmailApp.search(
      `${config.query}` +
      ` -label:${LABEL_DONE} -label:${LABEL_SKIPPED} -label:${LABEL_NEEDS_CHECK}` +
      ` ${SEARCH_WINDOW}`
    );
    if (threads.length === 0) {
      return;
    }
    console.log(`[${config.name}] 未処理のスレッド: ${threads.length} 件`);

    const byKey = {};    // { キー: { payload: {...}, threads: [...] } }
    const skipped = [];  // 対象外
    const unknown = [];  // 抽出できない

    threads.forEach(function (thread) {
      const hit = extractFromThread(thread, config.extract);
      if (!hit) {
        unknown.push(thread);
      } else if (hit.key) {
        if (!byKey[hit.key]) byKey[hit.key] = { payload: hit.payload, threads: [] };
        byKey[hit.key].threads.push(thread);
      } else {
        skipped.push({ thread: thread, label: hit.label });
      }
    });

    // 対象外。正常な状態なのでログだけ残して無視する
    if (skipped.length > 0) {
      const label = getOrCreateLabel(LABEL_SKIPPED);
      skipped.forEach(function (s) {
        console.log(`[${config.name}] 対象外(${s.label}): ${s.thread.getFirstMessageSubject()}`);
        s.thread.addLabel(label);
      });
    }

    // 必要な情報が取れない。メール形式が変わった可能性があるので隔離する
    if (unknown.length > 0) {
      const label = getOrCreateLabel(LABEL_NEEDS_CHECK);
      unknown.forEach(function (t) {
        console.error(`[${config.name}] 判別できません: ${t.getFirstMessageSubject()}`);
        t.addLabel(label);
      });
    }

    // 対象単位で1回だけ起動する。
    // 上限を超えた分は未処理のまま残し、次回の実行で拾う。
    const doneLabel = getOrCreateLabel(LABEL_DONE);
    const keys = Object.keys(byKey);
    if (keys.length > MAX_DISPATCH_PER_RUN) {
      console.log(
        `[${config.name}] ${keys.length} 対象のうち ${MAX_DISPATCH_PER_RUN} 件を処理し、` +
        `残り ${keys.length - MAX_DISPATCH_PER_RUN} 件は次回に持ち越します`
      );
    }
    const failures = [];
    keys.slice(0, MAX_DISPATCH_PER_RUN).forEach(function (key) {
      const entry = byKey[key];
      try {
        dispatch(config.eventType, entry.payload, config.target);
        console.log(`[${config.name}] ${key}: ${entry.threads.length} 件を起動`);
        // 起動に成功したメールだけ処理済みにする
        entry.threads.forEach(function (t) { t.addLabel(doneLabel); });
      } catch (e) {
        // ラベルを付けないので次回の実行で再試行される
        console.error(`[${config.name}] ${key}: 起動に失敗（次回再試行） ${e}`);
        failures.push(`${key}: ${e}`);
      }
    });

    // 例外を投げないと Apps Script が「正常終了」と判断し、
    // Google からの障害通知メールが飛ばない。
    // トークン切れなどが無音で放置されるのを防ぐため、最後に必ず投げる。
    if (failures.length > 0) {
      throw new Error(`[${config.name}] 起動に失敗: ${failures.join(' / ')}`);
    }

  } finally {
    lock.releaseLock();
  }
}

// ===== 死活監視 =====

/**
 * 1日1回、生存を GitHub に知らせる。
 *
 * 応募が無い日は何も起動しないため、「トリガーが止まっている」のか
 * 「応募が無いだけ」なのかを外部から区別できない。
 * 毎日必ず1回動かすことで、監視ワークフロー側が停止を検知できるようにする。
 *
 * トリガー設定: sendHeartbeat を「日タイマー」で1日1回
 */
function sendHeartbeat() {
  dispatch('heartbeat', {}, 'none');
  console.log('ハートビートを送信しました');
}

function extractFromThread(thread, extract) {
  const messages = thread.getMessages();
  for (var i = 0; i < messages.length; i++) {
    const hit = extract(messages[i].getPlainBody());
    if (hit) return hit;
  }
  return null;
}

/** GitHub Actions に実行命令を送る */
function dispatch(eventType, payload, target) {
  const body = Object.assign({ target: target }, payload);
  const res = UrlFetchApp.fetch(
    `https://api.github.com/repos/${REPO}/dispatches`,
    {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: `Bearer ${GITHUB_TOKEN}`,
        Accept: 'application/vnd.github+json',
      },
      payload: JSON.stringify({ event_type: eventType, client_payload: body }),
      muteHttpExceptions: true,
    }
  );

  const code = res.getResponseCode();
  if (code !== 204) {
    throw new Error(`GitHub API が ${code} を返しました: ${res.getContentText()}`);
  }
}

function getOrCreateLabel(name) {
  return GmailApp.getUserLabelByName(name) || GmailApp.createLabel(name);
}

// ===== 動作確認用 =====

/** GitHub との疎通確認（メールは読まない） */
function testDispatchAts() {
  dispatch('ats-applicant', { account: 'ats2' }, TARGET_ATS);
  console.log('ATS の起動に成功しました。GitHub の Actions タブを確認してください。');
}

/** 求人ボックスの疎通確認。実在するアカウントIDを指定すること */
function testDispatchKyujinbox() {
  dispatch('kyujinbox-applicant', { account_id: '6617-5385' }, TARGET_KYUJINBOX);
  console.log('求人ボックスの起動に成功しました。GitHub の Actions タブを確認してください。');
}

/** メールの判別確認（GitHubは呼ばない） */
function testDetectAts() {
  dumpDetection('ATS', ATS_QUERY, checkAtsMailExtract());
}

function testDetectKyujinbox() {
  dumpDetection('求人ボックス', KYUJINBOX_QUERY, checkKyujinboxMailExtract());
}

function checkAtsMailExtract() {
  return function (body) {
    const m = body.match(/kyujinbu\.com\/([A-Za-z0-9_-]+)\/detail\//);
    if (!m) return null;
    const account = ATS_ACCOUNT_BY_SLUG[m[1]];
    return account ? { key: account, label: m[1] } : { key: null, label: m[1] };
  };
}

function checkKyujinboxMailExtract() {
  return function (body) {
    const m = body.match(/【アカウントID】[\s　]*([0-9]{4}-[0-9]{4})/);
    return m ? { key: m[1], label: m[1] } : null;
  };
}

function dumpDetection(name, query, extract) {
  const threads = GmailApp.search(`${query} newer_than:30d`);
  if (threads.length === 0) {
    console.log(`[${name}] 対象のメールが見つかりません。`);
    return;
  }
  console.log(`[${name}] ${threads.length} 件を確認します`);
  threads.forEach(function (t) {
    const hit = extractFromThread(t, extract);
    var status;
    if (!hit) {
      status = '判別不可（要調査）';
    } else if (hit.key) {
      status = `${hit.key}`;
    } else {
      status = `対象外  [${hit.label}]`;
    }
    console.log(`${status}  <-  ${t.getFirstMessageSubject()}`);
  });
}

/**
 * 検索条件が合っているか調べる（一時的な診断用）。
 * 検索でメールが見つからないときに使う。
 */
function debugSearch() {
  const queries = [
    KYUJINBOX_QUERY,
    'subject:新着応募のお知らせ',
    'kyujinbox',
    ATS_QUERY,
  ];
  queries.forEach(function (q) {
    const threads = GmailApp.search(q + ' newer_than:30d', 0, 3);
    console.log(`=== ${q}  →  ${threads.length} 件 ===`);
    threads.forEach(function (t) {
      const m = t.getMessages()[0];
      console.log(`    From: ${m.getFrom()}`);
      console.log(`    件名: ${m.getSubject()}`);
    });
  });
}
