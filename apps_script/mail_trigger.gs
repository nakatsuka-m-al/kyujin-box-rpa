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

const ATS_SENDER = 'do-not-reply@kyujinbu.com';
const KYUJINBOX_SENDER = 'notice@kyujinbox.com';

const LABEL_DONE = 'RPA処理済み';
const LABEL_SKIPPED = 'RPA対象外';      // 他社宛。正常なので通知しない
const LABEL_NEEDS_CHECK = 'RPA要確認';  // 形式が変わった可能性。要調査

/** 取りこぼし対策で少し広めに検索する */
const SEARCH_WINDOW = 'newer_than:2d';

// ===== エントリポイント =====

function checkAtsMail() {
  processMails({
    name: 'ATS',
    sender: ATS_SENDER,
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
    sender: KYUJINBOX_SENDER,
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
      `from:${config.sender}` +
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

    // 対象単位で1回だけ起動する
    const doneLabel = getOrCreateLabel(LABEL_DONE);
    Object.keys(byKey).forEach(function (key) {
      const entry = byKey[key];
      try {
        dispatch(config.eventType, entry.payload, config.target);
        console.log(`[${config.name}] ${key}: ${entry.threads.length} 件を起動`);
        // 起動に成功したメールだけ処理済みにする
        entry.threads.forEach(function (t) { t.addLabel(doneLabel); });
      } catch (e) {
        // ラベルを付けないので次回の実行で再試行される
        console.error(`[${config.name}] ${key}: 起動に失敗（次回再試行） ${e}`);
      }
    });

  } finally {
    lock.releaseLock();
  }
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
  dumpDetection('ATS', ATS_SENDER, checkAtsMailExtract());
}

function testDetectKyujinbox() {
  dumpDetection('求人ボックス', KYUJINBOX_SENDER, checkKyujinboxMailExtract());
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

function dumpDetection(name, sender, extract) {
  const threads = GmailApp.search(`from:${sender} newer_than:30d`);
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
