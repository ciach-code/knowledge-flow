// background.js — service worker：响应图标点击 / Alt+S 快捷键，
// 按需注入抓取脚本，把结果 POST 到本地 n8n webhook。

const WEBHOOK_URL = 'http://localhost:5678/webhook/capture';
const MAX_CHARS = 15000; // 抓取文本过长时截断，避免摘要模型一次吃太多

// 点击工具栏图标触发（Alt+S 通过 _execute_action 命令也走这里）
chrome.action.onClicked.addListener(async (tab) => {
  await capture(tab);
});

async function capture(tab) {
  if (!tab || tab.id == null) return;
  try {
    const config = await loadSelectors();

    // 按需把抓取函数注入当前页面执行（activeTab 已授予临时权限）
    const [injected] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractConversation,
      args: [config.sites || [], MAX_CHARS],
    });
    const res = injected && injected.result;

    if (res && res.error) return showResult(false, res.error);
    if (!res || !res.raw_text) return showResult(false, '未找到对话内容');

    const ok = await postToWebhook(res);
    showResult(ok, ok ? '已提交，摘要后台生成' : '发送到 n8n webhook 失败');
  } catch (_e) {
    // executeScript 失败：浏览器内部页（chrome:// 等）或权限受限
    showResult(false, '当前页面无法捕获（浏览器内部页或权限受限）');
  }
}

// 每次点击都现读配置，这样改了 selectors.json 下次触发立即生效，无需重载扩展
async function loadSelectors() {
  try {
    const r = await fetch(chrome.runtime.getURL('selectors.json'));
    return await r.json();
  } catch (_e) {
    return { sites: [] };
  }
}

async function postToWebhook(payload) {
  try {
    const resp = await fetch(WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    // n8n webhook 响应模式为 onReceived，成功返回 200
    return resp.ok;
  } catch (_e) {
    return false; // 网络失败 / n8n 未启动
  }
}

// 反馈：角标 ✓/✗ + 系统通知；几秒后清掉角标
function showResult(ok, message) {
  chrome.action.setBadgeBackgroundColor({ color: ok ? '#2ea043' : '#f85149' });
  chrome.action.setBadgeText({ text: ok ? '✓' : '✗' });
  chrome.notifications.create({
    type: 'basic',
    iconUrl: 'icon128.png',
    title: ok ? '已捕获' : '捕获失败',
    message,
  });
  setTimeout(() => chrome.action.setBadgeText({ text: '' }), 4000);
}

// 下面的函数会被序列化注入到网页里执行，必须自包含，不能引用外部变量。
// sites：selectors.json 里的 sites 数组；maxChars：截断长度。
function extractConversation(sites, maxChars) {
  const host = location.hostname;
  const site = (sites || []).find((c) =>
    (c.match || []).some((m) => host.indexOf(m) !== -1)
  );

  const lines = [];
  if (site && site.message) {
    const els = document.querySelectorAll(site.message);
    for (const el of els) {
      const role = detectRole(el, site);
      if (!role) continue;
      const text = clean(el.innerText);
      if (!text) continue;
      lines.push((role === 'user' ? '用户' : '助手') + '：' + text);
    }
  }

  let source, title, raw_text;
  if (lines.length) {
    raw_text = lines.join('\n\n');
    source = site.source;
    title = firstUserLine(lines) || document.title || site.name;
  } else {
    // 兜底：未配置或没抓到，取主内容区全文
    const el =
      document.querySelector('main') ||
      document.querySelector('[role="main"]') ||
      document.body;
    raw_text = clean(el && el.innerText);
    source = hostToSource(host);
    title = document.title || host;
  }

  if (!raw_text) return { error: '未抓取到任何内容' };
  if (raw_text.length > maxChars) {
    raw_text = raw_text.slice(0, maxChars) + '\n\n…（内容过长，已截断）';
  }
  return { source: source, title: title, raw_text: raw_text };

  function detectRole(el, cfg) {
    if (cfg.roleAttr) {
      const v = (el.getAttribute(cfg.roleAttr) || '').toLowerCase();
      if (v === 'user') return 'user';
      if (v === 'assistant') return 'assistant';
      return null; // system / tool / developer 等非对话内容，忽略
    }
    if (cfg.userSelector && el.matches(cfg.userSelector)) return 'user';
    if (cfg.assistantSelector && el.matches(cfg.assistantSelector)) return 'assistant';
    return null;
  }

  function clean(s) {
    return (s || '').replace(/ /g, ' ').trim();
  }

  function firstUserLine(ls) {
    const l = (ls || []).find((x) => x.indexOf('用户：') === 0);
    if (!l) return '';
    const t = l.slice(3).replace(/\s+/g, ' ').trim();
    return t.length > 80 ? t.slice(0, 80) + '…' : t;
  }

  function hostToSource(h) {
    return h
      .replace(/^www\./, '')
      .replace(/\.(com|cn|ai|net|org|io|dev)$/i, '')
      .replace(/\./g, '-');
  }
}
