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
const LABEL_DONE = 'RPA処理済み';
const LABEL_NEEDS_CHECK = 'RPA要確認';

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
      `from:${ATS_SENDER} -label:${LABEL_DONE} -label:${LABEL_NEEDS_CHECK} ${SEARCH_WINDOW}`
    );
    if (threads.length === 0) {
      return;
    }
    console.log(`未処理のスレッド: ${threads.length} 件`);

    // アカウントごとにスレッドをまとめる
    const byAccount = {};   // { ats1: [thread, ...], ats2: [...] }
    const unknown = [];

    threads.forEach(function (thread) {
      const account = detectAccount(thread);
      if (account) {
        (byAccount[account] = byAccount[account] || []).push(thread);
      } else {
        unknown.push(thread);
      }
    });

    // 判別できなかったものは隔離して通知する
    if (unknown.length > 0) {
      const label = getOrCreateLabel(LABEL_NEEDS_CHECK);
      unknown.forEach(function (t) {
        console.error(`アカウントを判別できません: ${t.getFirstMessageSubject()}`);
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

/** メール本文の求人URLから blaze / blaze2 を判別する */
function detectAccount(thread) {
  const messages = thread.getMessages();
  for (var i = 0; i < messages.length; i++) {
    const body = messages[i].getPlainBody();
    // blaze2 を先に判定すること（blaze が前方一致してしまうため）
    const m = body.match(/kyujinbu\.com\/(blaze2|blaze)\//);
    if (m) {
      return m[1] === 'blaze2' ? 'ats2' : 'ats1';
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
  const threads = GmailApp.search(`from:${ATS_SENDER} ${SEARCH_WINDOW}`);
  if (threads.length === 0) {
    console.log('対象のメールが見つかりません。検索期間を広げてください。');
    return;
  }
  threads.forEach(function (t) {
    console.log(`${detectAccount(t) || '判別不可'}  <-  ${t.getFirstMessageSubject()}`);
  });
}
