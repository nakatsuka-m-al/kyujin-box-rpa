/**
 * ATS(求人部) の応募通知メールを検知して、GitHub Actions を起動する。
 *
 * 設置手順は apps_script/README.md を参照。
 *
 * 動作:
 *   1分おきに未処理の通知メールを探す
 *   → 求人URL から blaze / blaze2 を判別
 *   → アカウントごとに1回だけ GitHub に実行命令を送る
 *   → 成功したメールにだけ「処理済み」ラベルを付ける
 *
 * 設計上の注意:
 *   - ラベル付けは dispatch 成功後に行う。失敗したメールは次回再試行される。
 *   - 同時に複数の応募が来ても、アカウント単位でまとめて1回だけ起動する。
 *   - 判別できないメールは別ラベルを付けて隔離する（無限リトライを避けるため）。
 */

// ===== 設定 =====

/** GitHub の Personal Access Token（Contents: Read and write） */
const GITHUB_TOKEN = 'ここにトークンを貼る';

const REPO = 'nakatsuka-m-al/kyujin-box-rpa';

/** 書き込み先。検証中は 'test'、本番に切り替えるときに 'production' にする */
const TARGET = 'test';

const ATS_SENDER = 'do-not-reply@kyujinbu.com';

/**
 * 求人URL のスラッグ → GitHub 側のアカウント名。
 * このメールボックスには他社の通知も届くため、ここに無いものは対象外として無視する。
 * 対象を増やすときは、GitHub Secrets にも認証情報を追加すること。
 */
const ACCOUNT_BY_SLUG = {
  blaze:  'ats1',
  blaze2: 'ats2',
};

const LABEL_DONE = 'RPA処理済み';
const LABEL_SKIPPED = 'RPA対象外';      // 他社宛。正常なので通知しない
const LABEL_NEEDS_CHECK = 'RPA要確認';  // 形式が変わった可能性。要調査

/** 取りこぼし対策で少し広めに検索する */
const SEARCH_WINDOW = 'newer_than:2d';

// ===== メイン =====

function checkAtsMail() {
  // 1分間隔で起動するため、前回の処理が終わる前に重ならないようにする
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) {
    console.log('前回の処理が実行中のためスキップ');
    return;
  }

  try {
    const threads = GmailApp.search(
      `from:${ATS_SENDER}` +
      ` -label:${LABEL_DONE} -label:${LABEL_SKIPPED} -label:${LABEL_NEEDS_CHECK}` +
      ` ${SEARCH_WINDOW}`
    );
    if (threads.length === 0) {
      return;
    }
    console.log(`未処理のスレッド: ${threads.length} 件`);

    const byAccount = {};   // { ats1: [thread, ...], ats2: [...] }
    const skipped = [];     // 他社宛
    const unknown = [];     // URLが見つからない

    threads.forEach(function (thread) {
      const hit = detectAccount(thread);
      if (!hit) {
        unknown.push(thread);
      } else if (hit.account) {
        (byAccount[hit.account] = byAccount[hit.account] || []).push(thread);
      } else {
        skipped.push({ thread: thread, slug: hit.slug });
      }
    });

    // 他社宛。正常な状態なのでログだけ残して無視する
    if (skipped.length > 0) {
      const label = getOrCreateLabel(LABEL_SKIPPED);
      skipped.forEach(function (s) {
        console.log(`対象外(${s.slug}): ${s.thread.getFirstMessageSubject()}`);
        s.thread.addLabel(label);
      });
    }

    // 求人URLが見つからない。メール形式が変わった可能性があるので隔離する
    if (unknown.length > 0) {
      const label = getOrCreateLabel(LABEL_NEEDS_CHECK);
      unknown.forEach(function (t) {
        console.error(`求人URLが見つかりません: ${t.getFirstMessageSubject()}`);
        t.addLabel(label);
      });
    }

    // アカウント単位で1回だけ起動する
    const doneLabel = getOrCreateLabel(LABEL_DONE);
    Object.keys(byAccount).forEach(function (account) {
      const targets = byAccount[account];
      try {
        dispatch(account);
        console.log(`${account}: ${targets.length} 件を起動`);
        // 起動に成功したメールだけ処理済みにする
        targets.forEach(function (t) { t.addLabel(doneLabel); });
      } catch (e) {
        // ラベルを付けないので次回の実行で再試行される
        console.error(`${account}: 起動に失敗（次回再試行） ${e}`);
      }
    });

  } finally {
    lock.releaseLock();
  }
}

// ===== 補助 =====

/**
 * メール本文の求人URLから対象アカウントを判別する。
 *
 * 戻り値:
 *   { slug: 'blaze2', account: 'ats2' }  … 管理対象
 *   { slug: 'gss-b',  account: null   }  … 他社宛。無視してよい
 *   null                                 … URLが見つからない。形式変更の疑い
 */
function detectAccount(thread) {
  const messages = thread.getMessages();
  for (var i = 0; i < messages.length; i++) {
    // 求人URL は https://kyujinbu.com/{スラッグ}/detail/post_NNN.html の形
    const m = messages[i].getPlainBody().match(/kyujinbu\.com\/([A-Za-z0-9_-]+)\/detail\//);
    if (m) {
      const slug = m[1];
      return { slug: slug, account: ACCOUNT_BY_SLUG[slug] || null };
    }
  }
  return null;
}

/** GitHub Actions に実行命令を送る */
function dispatch(account) {
  const res = UrlFetchApp.fetch(
    `https://api.github.com/repos/${REPO}/dispatches`,
    {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: `Bearer ${GITHUB_TOKEN}`,
        Accept: 'application/vnd.github+json',
      },
      payload: JSON.stringify({
        event_type: 'ats-applicant',
        client_payload: { account: account, target: TARGET },
      }),
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

/** トークンと権限が正しいかだけを確認する（メールは読まない） */
function testDispatch() {
  dispatch('ats2');
  console.log('起動に成功しました。GitHub の Actions タブを確認してください。');
}

/** 直近のメールが正しく判別できるか確認する（GitHubは呼ばない） */
function testDetect() {
  // 確認用なので広めに見る
  const threads = GmailApp.search(`from:${ATS_SENDER} newer_than:30d`);
  if (threads.length === 0) {
    console.log('対象のメールが見つかりません。');
    return;
  }
  console.log(`${threads.length} 件を確認します`);
  threads.forEach(function (t) {
    const hit = detectAccount(t);
    var status;
    if (!hit) {
      status = '判別不可（要調査）';
    } else if (hit.account) {
      status = `${hit.account}  [${hit.slug}]`;
    } else {
      status = `対象外  [${hit.slug}]`;
    }
    console.log(`${status}  <-  ${t.getFirstMessageSubject()}`);
  });
}
