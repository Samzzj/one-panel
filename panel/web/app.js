'use strict';

/* ============================================================
 * Reality Panel 前端（无框架、无构建、无外部依赖）
 * ============================================================ */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const svg = (inner, size = 17) =>
  `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" ` +
  `stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`;

const ICON = {
  dash: svg('<rect x="3" y="3" width="7.5" height="7.5" rx="1.6"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.6"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.6"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.6"/>'),
  nodes: svg('<rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/><path d="M7 7h.01M7 17h.01"/>'),
  server: svg('<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 16.5h.01M11 6.5h5M11 16.5h5"/>'),
  terminal: svg('<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>', 15),
  push: svg('<path d="M12 19V5"/><polyline points="5 12 12 5 19 12"/>', 15),
  users: svg('<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/>'),
  chain: svg('<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>'),
  logs: svg('<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>'),
  settings: svg('<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>'),
  plus: svg('<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>', 15),
  copy: svg('<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>', 14),
  edit: svg('<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/>', 14),
  trash: svg('<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>', 14),
  key: svg('<circle cx="7.5" cy="15.5" r="4.5"/><path d="M10.7 12.3 21 2m-4 4 3 3m-6 0 2 2"/>', 14),
  qr: svg('<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM20 14h1M14 20h1M18 18h3v3h-3"/>', 14),
  reset: svg('<path d="M3 12a9 9 0 1 0 3-6.7"/><polyline points="3 4 3 10 9 10"/>', 14),
  audit: svg('<path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 12h6M9 16h4"/>'),
  upload: svg('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>', 15),
  sun: svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>', 17),
  moon: svg('<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>', 17),
  refresh: svg('<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>', 15),
  download: svg('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>', 15),
  arrow: svg('<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>', 14),
};

const LOGO = `<svg class="mark" viewBox="0 0 48 48" width="30" height="30" aria-hidden="true">
  <defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#8b6dff"/><stop offset="1" stop-color="#22d3ee"/>
  </linearGradient></defs>
  <path d="M24 4 42 14v20L24 44 6 34V14z" fill="#0d1017" stroke="url(#lg)" stroke-width="1.6"/>
  <path d="M24 13.5 33 19v10l-9 5.5-9-5.5V19z" fill="none" stroke="url(#lg)" stroke-width="2" stroke-linejoin="round"/>
  <circle cx="24" cy="24" r="2.4" fill="url(#lg)"/>
</svg>`;

const AGENT_INSTALL_URL = 'https://raw.githubusercontent.com/Samzzj/one-panel/main/deploy/agent-install.sh';

/* ------------------------------------------------------------ 状态 */

let CSRF = '';
let STATE = null;
let BOOTSTRAP = { setup_required: false, panel_name: 'Reality Panel', version: '' };
let SS_NODE = null;

/* ------------------------------------------------------------ 主题 */

function currentTheme() {
  return document.documentElement && document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('rp-theme', theme); } catch (err) { /* ignore */ }
  const btn = $('#btn-theme');
  if (btn) {
    btn.innerHTML = theme === 'light' ? ICON.moon : ICON.sun;
    btn.title = theme === 'light' ? '切换到深色' : '切换到浅色';
  }
}

function bindThemeButton() {
  const btn = $('#btn-theme');
  if (!btn) return;
  const theme = currentTheme();
  btn.innerHTML = theme === 'light' ? ICON.moon : ICON.sun;
  btn.title = theme === 'light' ? '切换到深色' : '切换到浅色';
  btn.onclick = () => setTheme(currentTheme() === 'light' ? 'dark' : 'light');
}

/* ------------------------------------------------------------ 工具 */

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}

function fmtBytes(n) {
  n = Number(n || 0);
  if (n <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; }
  return `${i === 0 ? Math.round(n) : n.toFixed(2)} ${units[i]}`;
}

function fmtTime(ts) {
  if (!ts) return '永久';
  const d = new Date(Number(ts) * 1000);
  const p = (x) => String(x).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function fmtQuota(used, quota) {
  const u = fmtBytes(used);
  return quota > 0 ? `${u} / ${fmtBytes(quota)}` : `${u} / 不限`;
}

function agentUrlFromAddress(value) {
  let host = String(value || '').trim().replace(/^https?:\/\//i, '').replace(/\/.*$/, '');
  if (!host) return '';
  if (host.startsWith('[')) {
    return /^\[[^\]]+\]:\d+$/.test(host) ? `http://${host}` : `http://${host}:8787`;
  }
  if ((host.match(/:/g) || []).length > 1) return `http://[${host}]:8787`;
  if (/:\d+$/.test(host)) return `http://${host}`;
  return `http://${host}:8787`;
}

function looksLikeDomain(value) {
  let host = String(value || '').trim().replace(/^https?:\/\//i, '').replace(/\/.*$/, '');
  if (!host || /^\d{1,3}(\.\d{1,3}){3}$/.test(host) || host.includes(':')) return false;
  return /^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(host);
}

function toast(text, type = 'ok', timeout = 3600) {
  const root = $('#toast-root');
  if (!root) return;
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = text;
  root.appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity .2s, transform .2s';
    el.style.opacity = '0';
    el.style.transform = 'translateX(8px)';
    setTimeout(() => el.remove(), 220);
  }, timeout);
}

async function api(path, opts = {}) {
  const init = { method: opts.method || 'GET', headers: {}, credentials: 'same-origin' };
  if (opts.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(opts.body);
  }
  if (CSRF) init.headers['X-CSRF-Token'] = CSRF;
  const res = await fetch(path, init);
  const ct = res.headers.get('content-type') || '';
  let data = null;
  if (ct.includes('application/json')) {
    try { data = await res.json(); } catch { data = null; }
  } else {
    data = await res.text();
  }
  if (!res.ok) {
    const message = (data && data.error) || (typeof data === 'string' && data) || `HTTP ${res.status}`;
    const err = new Error(message);
    err.status = res.status;
    throw err;
  }
  if (data && data.csrf) CSRF = data.csrf;
  return data;
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch { /* ignore */ }
    ta.remove();
  }
  toast('已复制到剪贴板');
}

function showQr(title, text) {
  if (typeof qrcode !== 'function') {
    toast('二维码组件未加载，请刷新页面', 'err');
    return;
  }
  let markup;
  try {
    const qr = qrcode(0, 'M');
    qr.addData(text);
    qr.make();
    markup = qr.createSvgTag({ cellSize: 6, margin: 4, scalable: true });
  } catch (err) {
    toast(`二维码生成失败：${err.message || err}`, 'err');
    return;
  }
  const m = openModal({
    title,
    body: `<div class="qr-box">${markup}</div>
      <div class="copy-row" style="margin-top:14px">
        <input class="input" readonly value="${esc(text)}">
        <button class="btn btn-sm" data-copy="${esc(text)}">${ICON.copy}</button>
      </div>
      <div class="hint" style="margin-top:10px">用手机客户端扫码导入；订阅二维码在节点变更后仍然有效。</div>`,
    footer: '<button class="btn" data-close2>关闭</button>',
  });
  $('[data-close2]', m.modal).onclick = () => m.close();
  m.overlay.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-copy]');
    if (btn) copyText(btn.dataset.copy);
  });
}

function openModal({ title, body, footer = '', wide = false, onClose = null, closeOnOverlay = true }) {
  const overlay = document.createElement('div');
  overlay.className = 'overlay';
  overlay.innerHTML = `
    <div class="modal ${wide ? 'wide' : ''}" role="dialog" aria-modal="true">
      <div class="modal-head"><h3>${esc(title)}</h3><div class="spacer"></div>
        <button class="icon-btn" data-close aria-label="关闭">✕</button></div>
      <div class="modal-body">${body}</div>
      ${footer ? `<div class="modal-foot">${footer}</div>` : ''}
    </div>`;
  $('#modal-root').appendChild(overlay);

  let closed = false;
  const close = (result) => {
    if (closed) return;
    closed = true;
    document.removeEventListener('keydown', onKey);
    overlay.remove();
    if (onClose) onClose(result);
  };
  function onKey(e) {
    if (e.key === 'Escape') close();
  }
  overlay.addEventListener('click', (e) => {
    if (closeOnOverlay && e.target === overlay) close();
  });
  $('[data-close]', overlay).addEventListener('click', () => close());
  document.addEventListener('keydown', onKey);
  return { overlay, modal: overlay.querySelector('.modal'), close };
}

function confirmDialog(title, text, danger = false) {
  return new Promise((resolve) => {
    const m = openModal({
      title,
      body: `<div style="color:var(--muted);font-size:13px;line-height:1.75">${esc(text)}</div>`,
      footer: '<button class="btn" data-cancel>取消</button>' +
        `<button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-ok>确定</button>`,
      onClose: (result) => resolve(result === true),
    });
    $('[data-cancel]', m.modal).onclick = () => m.close();
    $('[data-ok]', m.modal).onclick = () => m.close(true);
  });
}

/* ------------------------------------------------------------ 登录 / 初始化 */

function renderAuth(mode) {
  const root = $('#boot');
  if (root) root.remove();
  $('#app').innerHTML = '';
  const setup = mode === 'setup';
  const app = $('#app');
  app.innerHTML = `
    <div class="auth-wrap">
      <button class="icon-btn auth-theme" id="btn-theme" title="切换明暗">${ICON.sun}</button>
      <form class="auth-card" id="auth-form" autocomplete="on">
        <div class="auth-brand">${LOGO}
          <div>
            <h1>${esc(BOOTSTRAP.panel_name || 'Reality Panel')}</h1>
            <p>${setup ? '首次使用，请创建管理员账号' : 'VLESS · REALITY 控制台'}</p>
          </div>
        </div>

        ${setup ? `
          <div class="field"><label>管理员用户名</label>
            <input class="input" name="username" value="admin" autocomplete="username" required></div>` : `
          <div class="field"><label>用户名</label>
            <input class="input" name="username" autocomplete="username" required autofocus></div>`}

        <div class="field"><label>密码</label>
          <input class="input" type="password" name="password"
            autocomplete="${setup ? 'new-password' : 'current-password'}"
            ${setup ? 'minlength="10"' : ''} required></div>

        ${setup ? `
          <div class="field"><label>确认密码</label>
            <input class="input" type="password" name="confirm" minlength="10" required></div>` : ''}

        <div id="auth-error" class="notice danger hidden" style="margin-bottom:14px"></div>

        <button class="btn btn-primary btn-block" id="auth-submit" type="submit">
          ${setup ? '创建并进入面板' : '登录'}
        </button>

        <div class="hint" style="text-align:center;margin-top:14px">
          ${setup
            ? '密码至少 10 位。创建完成后请到「设置」填写 SNI 域名与 Xray 路径。'
            : '连续输错会临时封禁当前 IP'}
        </div>
      </form>
    </div>`;

  const form = $('#auth-form');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = $('#auth-submit');
    const errorBox = $('#auth-error');
    const fd = new FormData(form);
    const username = String(fd.get('username') || '').trim();
    const password = String(fd.get('password') || '');
    errorBox.classList.add('hidden');

    if (setup && password !== String(fd.get('confirm') || '')) {
      errorBox.textContent = '两次输入的密码不一致';
      errorBox.classList.remove('hidden');
      return;
    }

    btn.disabled = true;
    btn.textContent = setup ? '创建中…' : '登录中…';
    try {
      const data = await api(setup ? '/api/setup' : '/api/login', {
        method: 'POST',
        body: { username, password },
      });
      CSRF = data.csrf;
      await loadState();
      if (setup) toast('初始化完成，欢迎使用');
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.classList.remove('hidden');
      btn.disabled = false;
      btn.textContent = setup ? '创建并进入面板' : '登录';
    }
  });

  bindThemeButton();
}

/* ------------------------------------------------------------ 外壳 */

function navItem(key, icon, label) {
  return `<div class="nav-item" data-nav="${key}">${icon}<span>${label}</span></div>`;
}

function renderShell() {
  const boot = $('#boot');
  if (boot) boot.remove();
  const s = STATE.settings;
  $('#app').innerHTML = `
    <div class="shell">
      <aside class="sidebar">
        <div class="brand">${LOGO}
          <div>
            <div class="brand-name">${esc(s.panel_name || 'Reality Panel')}</div>
            <div class="brand-sub">VLESS · REALITY</div>
          </div>
        </div>

        <div class="nav-label">管理</div>
        ${navItem('dashboard', ICON.dash, '概览')}
        ${navItem('servers', ICON.server, '服务器')}
        ${navItem('nodes', ICON.nodes, '节点')}
        ${navItem('subs', ICON.users, '订阅用户')}
        <div class="nav-label">部署</div>
        ${navItem('selfsteal', ICON.chain, '自偷自向导')}
        ${navItem('logs', ICON.logs, '运行日志')}
        ${navItem('audit', ICON.audit, '审计日志')}
        ${navItem('settings', ICON.settings, '设置')}

        <div class="sidebar-foot">
          <div class="who">
            <span class="dot ${STATE.xray.service_active ? '' : 'off'}" id="side-dot"></span>
            <span>${esc(STATE.user.username)}</span>
            <span style="margin-left:auto;color:var(--muted-2);font-size:11px">v${esc(STATE.version)}</span>
          </div>
          <button class="btn btn-ghost btn-sm btn-block" id="btn-logout">退出登录</button>
        </div>
      </aside>

      <main class="main">
        <header class="topbar">
          <div class="topbar-inner">
            <div>
              <h2 id="page-title">概览</h2>
              <div class="sub" id="page-sub"></div>
            </div>
            <div class="spacer"></div>
            <span class="dirty-pill hidden" id="dirty-pill">● 有未应用的更改</span>
            <button class="icon-btn" id="btn-theme" title="切换明暗">${ICON.sun}</button>
            <button class="btn btn-sm" id="btn-collect">${ICON.refresh}<span>同步流量</span></button>
            <button class="btn btn-primary btn-sm" id="btn-apply">应用配置</button>
          </div>
        </header>
        <div class="view" id="view"></div>
      </main>
    </div>`;

  $$('.nav-item').forEach((el) => {
    el.addEventListener('click', () => { location.hash = `#/${el.dataset.nav}`; });
  });
  $('#btn-logout').addEventListener('click', async () => {
    try { await api('/api/logout', { method: 'POST' }); } catch { /* ignore */ }
    location.reload();
  });
  $('#btn-apply').addEventListener('click', applyConfig);
  $('#btn-collect').addEventListener('click', async () => {
    const btn = $('#btn-collect');
    btn.disabled = true;
    try {
      const r = await api('/api/collect', { method: 'POST' });
      toast(`已同步流量，更新 ${r.updated} 个客户端`);
      await refresh();
    } catch (err) {
      toast(err.message, 'err');
    } finally {
      btn.disabled = false;
    }
  });
  $('#dirty-pill').addEventListener('click', applyConfig);
  bindThemeButton();
}

function updateTopbar() {
  if (!STATE) return;
  const pill = $('#dirty-pill');
  if (pill) pill.classList.toggle('hidden', !STATE.dirty);
  const dot = $('#side-dot');
  if (dot) {
    dot.classList.toggle('off', !STATE.xray.service_active);
    dot.classList.toggle('warn', !!STATE.xray.installed && !STATE.xray.service_active);
  }
}

/* ------------------------------------------------------------ 路由 */

async function route() {
  if (!STATE) return;
  const key = (location.hash || '#/dashboard').replace(/^#\//, '').split('?')[0];
  const name = VIEWS[key] ? key : 'dashboard';
  const view = VIEWS[name];

  $('#page-title').textContent = view.title;
  $('#page-sub').textContent = view.sub || '';
  $$('.nav-item').forEach((el) => el.classList.toggle('active', el.dataset.nav === name));

  const host = $('#view');
  host.onclick = null;
  try {
    host.innerHTML = await view.html();
    if (view.bind) view.bind();
  } catch (err) {
    if (err.status === 401) return renderAuth('login');
    host.innerHTML = `<div class="notice danger">加载失败：${esc(err.message)}</div>`;
  }
  updateTopbar();
}

async function refresh() {
  STATE = await api('/api/state');
  CSRF = STATE.csrf;
  updateTopbar();
  await route();
}

async function loadState() {
  STATE = await api('/api/state');
  CSRF = STATE.csrf;
  renderShell();
  if (!location.hash) location.hash = '#/dashboard';
  await route();
}

window.addEventListener('hashchange', () => { route(); });

/* ------------------------------------------------------------ 应用配置 */

async function applyConfig() {
  const btn = $('#btn-apply');
  if (!btn) return;
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = '应用中…';
  try {
    const r = await api('/api/apply', { method: 'POST' });
    const total = (r.servers || []).length;
    if (r.ok) {
      const warn = (r.warnings || []).join('；');
      toast(warn ? `已应用到 ${total} 台服务器，${warn}` : `配置已应用到 ${total} 台服务器`, warn ? 'info' : 'ok', 5000);
    } else {
      showApplyResult(r);
    }
    await refresh();
  } catch (err) {
    toast(err.message, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = old;
  }
}

function showApplyResult(r) {
  const servers = r.servers || [];
  const failed = servers.filter((item) => !item.ok);
  const blocks = failed.map((item) => {
    const parts = [`<div class="notice danger" style="margin-bottom:8px">${esc(item.error || '节点执行失败')}</div>`];
    if (item.test_output) {
      parts.push(`<div class="field"><label>配置测试输出</label>
        <pre class="step-cmd" style="margin:0"><code>${esc(item.test_output)}</code></pre></div>`);
    }
    if (item.restart_output) {
      parts.push(`<div class="field"><label>重启输出</label>
        <pre class="step-cmd" style="margin:0"><code>${esc(item.restart_output)}</code></pre></div>`);
    }
    return `<div class="field"><label>${esc(item.server_name)}${item.server_kind === 'local' ? '（本机）' : ''}</label>
      ${parts.join('')}</div>`;
  }).join('');

  const warnings = (r.warnings || []).map((w) => `<div class="notice warn" style="margin-bottom:8px">${esc(w)}</div>`).join('');

  const m = openModal({
    title: `应用失败（${failed.length}/${servers.length} 台）`,
    wide: true,
    body: `<div class="notice danger" style="margin-bottom:14px">有些服务器没有成功应用，下面是对应输出。</div>
      ${warnings}${blocks || '<div class="hint">没有更多信息。</div>'}`,
    footer: '<button class="btn" data-close2>关闭</button>',
  });
  $('[data-close2]', m.modal).onclick = () => m.close();
}

/* ------------------------------------------------------------ 概览 */

function chainItem(index, title, desc) {
  return `<div class="chain-node"><div class="chain-icon">${index}</div>
    <div class="chain-body"><div class="chain-title">${title}</div>
    <div class="chain-desc">${desc}</div></div></div>`;
}

function viewDashboard() {
  const s = STATE.summary;
  const x = STATE.xray;
  const first = STATE.nodes[0];
  const port = first ? first.port : 443;
  const sni = first ? first.sni : (STATE.settings.default_sni || 'node.example.com');
  const dest = first ? first.dest : (STATE.settings.dest || '127.0.0.1:8003');
  const upstream = (STATE.settings.nginx_upstream || 'https://www.lovelive-anime.jp').replace(/^https?:\/\//, '');
  const vision = STATE.nodes.filter((n) => n.transport === 'vision').length;
  const xhttp = STATE.nodes.length - vision;

  const nodeRows = STATE.nodes.slice(0, 6).map((n) => `
    <div class="kv">
      <span>${esc(n.name)} <span class="tag tag-${n.transport}">${n.transport === 'xhttp' ? 'XHTTP' : 'Vision'}</span></span>
      <span class="mono">${esc(n.server_name || '本机')} · :${n.port}</span>
    </div>`).join('') || '<div class="empty" style="padding:20px">还没有节点</div>';

  return `
    <div class="grid grid-4">
      <div class="card stat-accent">
        <div class="stat-label">节点</div>
        <div class="stat-value">${s.nodes_enabled}<small> / ${s.nodes}</small></div>
        <div class="stat-foot">${s.servers_enabled} / ${s.servers} 台服务器 · Vision ${vision} · XHTTP ${xhttp}</div>
      </div>
      <div class="card stat-cyan">
        <div class="stat-label">订阅用户</div>
        <div class="stat-value">${s.subs_enabled}<small> / ${s.subs}</small></div>
        <div class="stat-foot">${s.expiring_soon > 0 ? `<span style="color:var(--warn)">${s.expiring_soon} 个 3 天内到期</span>` : '暂无临期订阅'}</div>
      </div>
      <div class="card">
        <div class="stat-label">累计流量</div>
        <div class="stat-value">${fmtBytes(s.up_bytes + s.down_bytes)}</div>
        <div class="stat-foot">↑ ${fmtBytes(s.up_bytes)} · ↓ ${fmtBytes(s.down_bytes)}</div>
      </div>
      <div class="card">
        <div class="stat-label">Xray 服务</div>
        <div class="stat-value" style="font-size:20px">${x.service_active ? '<span style="color:var(--ok)">运行中</span>' : (x.installed ? '<span style="color:var(--warn)">未运行</span>' : '<span style="color:var(--muted)">未安装</span>')}</div>
        <div class="stat-foot truncate">${esc(x.version || '未检测到 xray 可执行文件')}</div>
      </div>
    </div>

    ${STATE.dirty ? `<div class="notice warn" style="margin-top:16px">配置有改动尚未应用。点击右上角「应用配置」写入并重启 Xray。</div>` : ''}

    <div class="grid grid-2" style="margin-top:16px">
      <div class="card">
        <div class="card-head"><h3>自己偷自己 · 链路</h3><div class="spacer"></div>
          <span class="card-sub">客户端 → 真实站点</span></div>
        <div class="chain">
          ${chainItem(1, '客户端 Xray REALITY', `连接 <code>${esc(STATE.public_host)}:${port}</code>，SNI <code>${esc(sni)}</code>`)}
          ${chainItem(2, 'REALITY 校验', '校验握手、SNI、公钥与 shortId')}
          ${chainItem(3, 'PROXY protocol', `未通过校验的流量转到 <code>${esc(dest)}</code>，并携带真实源 IP`)}
          ${chainItem(4, '本机 Nginx · 本地 TLS', '用自有域名证书完成握手，探针看到的是合法站点')}
          ${chainItem(5, '反向代理', `拉取 <code>${esc(upstream)}</code> 的真实页面返回`)}
        </div>
        <div style="margin-top:14px"><a href="#/selfsteal">查看部署步骤与 Nginx 配置 →</a></div>
      </div>

      <div class="card">
        <div class="card-head"><h3>节点</h3><div class="spacer"></div>
          <button class="btn btn-sm" id="dash-new-node">${ICON.plus}<span>新建</span></button></div>
        ${nodeRows}
        <div style="margin-top:14px;display:flex;gap:8px">
          <a class="btn btn-sm" href="#/nodes">管理节点</a>
          <a class="btn btn-sm" href="#/subs">订阅用户</a>
        </div>
      </div>
    </div>

    <div class="grid grid-2" style="margin-top:16px">
      <div class="card">
        <div class="card-head"><h3>Xray 配置</h3></div>
        <div class="kv"><span>配置文件</span><span class="mono">${esc(x.config_path || '')}</span></div>
        <div class="kv"><span>文件状态</span><span>${x.config_exists ? '已存在' : '未写入'}</span></div>
        <div class="kv"><span>上次应用</span><span>${STATE.last_apply ? fmtTime(STATE.last_apply.at) : '从未'}</span></div>
        <div class="kv"><span>公网地址</span><span class="mono">${esc(STATE.public_host)}</span></div>
      </div>
      <div class="card">
        <div class="card-head"><h3>订阅入口</h3></div>
        <div class="kv"><span>订阅根地址</span><span class="mono truncate">${esc(STATE.sub_base)}</span></div>
        <div class="kv"><span>Base64 订阅</span><span class="mono">/sub/&lt;token&gt;</span></div>
        <div class="kv"><span>Clash 订阅</span><span class="mono">/sub/&lt;token&gt;/clash</span></div>
        <div class="hint" style="margin-top:10px">自偷自部署时，nginx 会把 <code>/sub/</code> 反代回面板，客户端用同一个域名拉订阅。</div>
      </div>
    </div>`;
}

function bindDashboard() {
  const btn = $('#dash-new-node');
  if (btn) btn.addEventListener('click', () => openNodeModal(null));
}

/* ------------------------------------------------------------ 服务器 */

function serverStatusTag(server) {
  if (server.kind === 'local') {
    return STATE.xray.service_active
      ? '<span class="tag tag-on">运行中</span>'
      : '<span class="tag tag-off">未运行</span>';
  }
  if (server.last_status === 'ok') return '<span class="tag tag-on">在线</span>';
  if (server.last_status === 'error') {
    return `<span class="tag tag-off" title="${esc(server.last_error || '')}">异常</span>`;
  }
  return '<span class="tag tag-off">未检测</span>';
}

function viewServers() {
  const rows = STATE.servers.map((s) => `
    <tr>
      <td>
        <div class="cell-title">${esc(s.name)}</div>
        <div class="cell-sub">${esc(s.domain || s.remark || (s.kind === 'local' ? '面板所在机器' : '节点机器'))}</div>
      </td>
      <td><span class="tag ${s.kind === 'local' ? 'tag-vision' : 'tag-xhttp'}">${s.kind === 'local' ? '本机' : 'Agent'}</span></td>
      <td class="mono">${esc(s.address || STATE.public_host)}</td>
      <td class="mono truncate" title="${esc(s.agent_url || '')}">${esc(s.kind === 'local' ? '—' : s.agent_url)}</td>
      <td>${s.node_count}</td>
      <td>${serverStatusTag(s)}</td>
      <td>${s.kind === 'local'
        ? '<span class="hint">常开</span>'
        : `<label class="switch"><input type="checkbox" data-toggle="${s.id}" ${s.enabled ? 'checked' : ''}><span></span></label>`}</td>
      <td class="row-actions">
        <button class="btn btn-sm" data-act="test" data-id="${s.id}">测试</button>
        ${s.kind === 'local'
          ? `<button class="icon-btn" data-act="edit" data-id="${s.id}" title="编辑">${ICON.edit}</button>`
          : `<button class="icon-btn" data-act="selfsteal" data-id="${s.id}" title="初始化自偷自（签证书 + 写 nginx）">${ICON.chain}</button>
             <button class="icon-btn" data-act="cmd" data-id="${s.id}" title="安装命令 / 重置令牌">${ICON.terminal}</button>
             <button class="icon-btn" data-act="edit" data-id="${s.id}" title="编辑">${ICON.edit}</button>
             <button class="icon-btn danger" data-act="del" data-id="${s.id}" title="删除">${ICON.trash}</button>`}
      </td>
    </tr>`).join('');

  return `
    <div class="card">
      <div class="card-head">
        <h3>服务器</h3><div class="spacer"></div>
        <span class="card-sub">主控只装一台，其余机器装 agent</span>
        <button class="btn btn-primary btn-sm" id="new-server">${ICON.plus}<span>添加服务器</span></button>
      </div>
      <div class="table-wrap">
        <table id="server-table">
          <thead><tr>
            <th>名称</th><th>类型</th><th>公网地址</th><th>Agent</th><th>节点</th><th>状态</th><th>启用</th><th></th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div class="hint" style="margin-top:12px">
        添加服务器时生成的安装命令，是在那台机器上装一个几十 KB 的 agent（不是面板）。
        装完点「测试」，之后在「应用配置」时主控会把配置推到所有服务器。
      </div>
    </div>`;
}

const SERVER_DRAFT_KEY = 'rp-server-draft';

function readServerDraft() {
  try {
    const raw = localStorage.getItem(SERVER_DRAFT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (err) {
    return null;
  }
}

function writeServerDraft(data) {
  try {
    localStorage.setItem(SERVER_DRAFT_KEY, JSON.stringify(data));
  } catch (err) { /* ignore */ }
}

function clearServerDraft() {
  try {
    localStorage.removeItem(SERVER_DRAFT_KEY);
  } catch (err) { /* ignore */ }
}

function openServerModal(server) {
  const editing = !!server;
  const isLocal = editing && server.kind === 'local';
  const draft = editing ? null : readServerDraft();
  const s = { ...(server || {}), ...(draft || {}) };
  const m = openModal({
    title: editing ? `编辑服务器 · ${s.name}` : '添加服务器',
    wide: true,
    closeOnOverlay: false,
    body: `<form id="server-form">
      ${draft ? '<div class="notice info" style="margin-bottom:14px">已恢复上次未保存的填写内容。</div>' : ''}
      <div class="field"><label>名称</label>
        <input class="input" name="name" value="${esc(s.name || '')}" placeholder="香港 02" maxlength="48" required></div>

      <div class="field"><label>公网地址</label>
        <input class="input" name="address" value="${esc(s.address || '')}" placeholder="1.2.3.4 或 node.example.com" required>
        <div class="hint">订阅链接里使用的地址。每台服务器可以不同。</div></div>

      ${isLocal ? '' : `
      <div class="field"><label>节点域名（已解析到这台机器）</label>
        <input class="input" name="domain" value="${esc(s.domain || '')}" placeholder="lisa2.example.com">
        <div class="hint">用于 REALITY 的 SNI。装好 agent 后可以一键签证书、写 nginx。</div></div>

      <div class="form-row">
        <div class="field"><label>Agent 地址</label>
          <input class="input" name="agent_url" value="${esc(s.agent_url || '')}" placeholder="http://1.2.3.4:8787" required>
          <div class="hint">输入公网地址后自动生成，可手动改端口。</div></div>
        <div class="field"><label>Agent 令牌</label>
          <input class="input" name="token" value="" placeholder="${editing ? '留空则不修改' : '留空自动生成'}"></div>
      </div>
      <div class="hint" style="margin-top:-6px;margin-bottom:12px">令牌等同于那台机器的控制权，不要发给别人。建议用防火墙把 8787 只放行面板 IP。</div>`}

      <div class="field"><label>备注</label>
        <input class="input" name="remark" value="${esc(s.remark || '')}" maxlength="120"></div>

      <label class="check-item"><input type="checkbox" name="enabled" ${s.enabled !== false ? 'checked' : ''}>
        <span>启用该服务器</span></label>
    </form>`,
    footer: `<button class="btn" data-cancel>取消</button>
      <button class="btn btn-primary" id="server-save">${editing ? '保存' : '添加'}</button>`,
  });

  const form = $('#server-form', m.modal);

  const saveDraft = () => {
    if (editing) return;
    const fd = new FormData(form);
    writeServerDraft({
      name: String(fd.get('name') || ''),
      address: String(fd.get('address') || ''),
      domain: String(fd.get('domain') || ''),
      agent_url: String(fd.get('agent_url') || ''),
      remark: String(fd.get('remark') || ''),
      enabled: fd.get('enabled') === 'on',
    });
  };
  form.addEventListener('input', saveDraft);
  form.addEventListener('change', saveDraft);

  // 输入公网地址后自动补 Agent 地址；如果地址本身是域名，顺便填节点域名
  const addressInput = form.querySelector('[name=address]');
  const domainInput = form.querySelector('[name=domain]');
  const agentInput = form.querySelector('[name=agent_url]');
  if (addressInput && agentInput) {
    let agentAuto = !agentInput.value.trim();
    let domainAuto = domainInput ? !domainInput.value.trim() : false;
    agentInput.addEventListener('input', () => { agentAuto = false; });
    if (domainInput) domainInput.addEventListener('input', () => { domainAuto = false; });
    const sync = () => {
      const address = addressInput.value.trim();
      if (agentAuto) agentInput.value = agentUrlFromAddress(address);
      if (domainInput && domainAuto) {
        domainInput.value = looksLikeDomain(address)
          ? address.replace(/^https?:\/\//i, '').replace(/\/.*$/, '')
          : '';
      }
    };
    addressInput.addEventListener('input', sync);
    if (addressInput.value.trim()) sync();
  }

  $('[data-cancel]', m.modal).onclick = () => {
    if (!editing) clearServerDraft();
    m.close();
  };
  $('#server-save', m.modal).onclick = async () => {
    if (!form.reportValidity()) return;
    const fd = new FormData(form);
    const body = {
      name: String(fd.get('name') || '').trim(),
      address: String(fd.get('address') || '').trim(),
      remark: String(fd.get('remark') || '').trim(),
      enabled: fd.get('enabled') === 'on',
    };
    if (!isLocal) {
      body.domain = String(fd.get('domain') || '').trim();
      body.agent_url = String(fd.get('agent_url') || '').trim();
      const token = String(fd.get('token') || '').trim();
      if (token) body.token = token;
    }
    const btn = $('#server-save', m.modal);
    btn.disabled = true;
    try {
      const result = editing
        ? await api(`/api/servers/${s.id}`, { method: 'PATCH', body })
        : await api('/api/servers', { method: 'POST', body });
      if (!editing) clearServerDraft();
      m.close();
      if (!editing) {
        toast('服务器已添加');
        showInstallCommand(result.server, result.token, result.install_url);
      } else {
        toast('服务器已更新');
      }
      await refresh();
    } catch (err) {
      toast(err.message, 'err');
      btn.disabled = false;
    }
  };
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    $('#server-save', m.modal).click();
  });
}

function showInstallCommand(server, token, installUrl) {
  const command = `curl -fsSL ${installUrl} | sudo bash -s -- --token ${token} --with-nginx`;
  const m = openModal({
    title: `在「${server.name}」上安装 agent`,
    wide: true,
    body: `<div class="notice info" style="margin-bottom:14px">
        这条命令只安装节点 agent，不是面板。用 SSH 登录到 <b>${esc(server.address)}</b> 执行。
      </div>
      <div class="field"><label>安装命令（在目标服务器上执行）</label>
        <div class="code-block">
          <div class="code-head"><span>root@${esc(server.address)}</span><div class="spacer"></div>
            <button class="btn btn-sm" data-copy="${esc(command)}">${ICON.copy}<span>复制</span></button>
          </div>
          <pre class="wrap">${esc(command)}</pre>
        </div>
      </div>
      <div class="field"><label>令牌（只显示这一次，丢失可在列表里重置）</label>
        <div class="copy-row"><input class="input" readonly value="${esc(token)}">
          <button class="btn btn-sm" data-copy="${esc(token)}">${ICON.copy}</button></div>
      </div>
      <div class="hint">装完回到本页点「测试」，成功后再点这一行的链条图标「初始化自偷自」；
        面板会让 agent 自动签证书、写 nginx。之后建节点时 SNI 用上面的节点域名。</div>`,
    footer: '<button class="btn" data-close2>关闭</button>',
  });
  $('[data-close2]', m.modal).onclick = () => m.close();
  m.overlay.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-copy]');
    if (btn) copyText(btn.dataset.copy);
  });
}

function showSelfstealResult(server, r) {
  const res = r.result || {};
  const nginx = res.nginx || {};
  const parts = [
    `<div class="kv"><span>服务器</span><span>${esc(server.name)}</span></div>`,
    `<div class="kv"><span>域名</span><span class="mono">${esc(r.domain || server.domain || '')}</span></div>`,
    `<div class="kv"><span>证书</span><span>${res.issued ? '本次已签发' : '已存在，跳过签发'}</span></div>`,
  ];
  if (res.error) {
    parts.push(`<div class="notice danger" style="margin-top:10px">${esc(res.error)}</div>`);
  }
  if (nginx.test_output) {
    parts.push(`<div class="field" style="margin-top:12px"><label>nginx -t</label>
      <div class="code-block"><pre class="wrap" style="max-height:220px">${esc(nginx.test_output)}</pre></div></div>`);
  }
  if (res.cert_output) {
    parts.push(`<div class="field"><label>certbot 输出</label>
      <div class="code-block"><pre class="wrap" style="max-height:220px">${esc(res.cert_output)}</pre></div></div>`);
  }
  const m = openModal({
    title: r.ok ? '自偷自初始化完成' : '自偷自初始化失败',
    wide: true,
    body: `${r.ok
      ? '<div class="notice info" style="margin-bottom:12px">证书和 nginx 已就绪。现在到「节点」新建节点，SNI 填这个域名即可。</div>'
      : '<div class="notice danger" style="margin-bottom:12px">证书或 nginx 没有成功，看下面的输出。</div>'}
      ${parts.join('')}`,
    footer: '<button class="btn" data-close2>关闭</button>',
  });
  $('[data-close2]', m.modal).onclick = () => m.close();
}

function bindServers() {
  const create = $('#new-server');
  if (create) create.addEventListener('click', () => openServerModal(null));

  const table = $('#server-table');
  if (!table) return;

  table.addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-act]');
    if (!btn) return;
    const id = Number(btn.dataset.id);
    const server = STATE.servers.find((item) => item.id === id);
    if (!server) return;

    if (btn.dataset.act === 'edit') return openServerModal(server);

    if (btn.dataset.act === 'selfsteal') {
      if (!server.domain) {
        toast('先在编辑里填写已解析到这台机器的节点域名', 'err');
        openServerModal(server);
        return;
      }
      const ok = await confirmDialog(
        '初始化自偷自',
        `将在「${server.name}」上用 certbot 签发 ${server.domain} 的证书，并写入 nginx。`
        + '需要该域名已解析到这台机器、80 端口可从公网访问；过程中会短暂停止 nginx。继续？',
        true,
      );
      if (!ok) return;
      btn.disabled = true;
      toast('正在签发证书并写入 nginx，可能需要 30-90 秒…', 'info', 8000);
      try {
        const result = await api(`/api/servers/${id}/selfsteal`, {
          method: 'POST',
          body: { domain: server.domain },
        });
        showSelfstealResult(server, result);
        await refresh();
      } catch (err) {
        toast(err.message, 'err', 6000);
      } finally {
        btn.disabled = false;
      }
      return;
    }

    if (btn.dataset.act === 'test') {
      btn.disabled = true;
      try {
        const result = await api(`/api/servers/${id}/test`, { method: 'POST' });
        if (result.ok) {
          toast(server.kind === 'local' ? '本机 Xray 正常' : `${server.name} 连接正常`);
        } else {
          const detail = (result.health && (result.health.error || result.health.message)) || '连接失败';
          toast(`${server.name}：${detail}`, 'err', 5000);
        }
        await refresh();
      } catch (err) {
        toast(err.message, 'err');
      } finally {
        btn.disabled = false;
      }
      return;
    }

    if (btn.dataset.act === 'cmd') {
      if (!(await confirmDialog('重置 Agent 令牌', `重置后「${server.name}」上的旧令牌立即失效，需要用新命令重装 agent。继续？`, true))) return;
      try {
        const result = await api(`/api/servers/${id}/token`, { method: 'POST' });
        showInstallCommand(result.server, result.token, AGENT_INSTALL_URL);
      } catch (err) {
        toast(err.message, 'err');
      }
      return;
    }

    if (btn.dataset.act === 'del') {
      if (!(await confirmDialog('删除服务器', `确定删除「${server.name}」？它上面的节点和订阅凭据会一起删除。`, true))) return;
      try {
        await api(`/api/servers/${id}`, { method: 'DELETE' });
        toast('服务器已删除');
        await refresh();
      } catch (err) {
        toast(err.message, 'err');
      }
    }
  });

  $$('input[data-toggle]', table).forEach((cb) => {
    cb.addEventListener('change', async () => {
      const id = Number(cb.dataset.toggle);
      try {
        await api(`/api/servers/${id}`, { method: 'PATCH', body: { enabled: cb.checked } });
        toast(cb.checked ? '服务器已启用' : '服务器已停用');
        await refresh();
      } catch (err) {
        cb.checked = !cb.checked;
        toast(err.message, 'err');
      }
    });
  });
}

/* ------------------------------------------------------------ 节点 */

function viewNodes() {
  const rows = STATE.nodes.map((n) => `
    <tr>
      <td>
        <div class="cell-title">${esc(n.name)}</div>
        <div class="cell-sub">${esc(n.remark || n.sni)}</div>
      </td>
      <td>${esc(n.server_name || '本机')}</td>
      <td><span class="tag tag-${n.transport}">${n.transport === 'xhttp' ? 'XHTTP' : 'Vision'}</span></td>
      <td class="mono">${n.port}</td>
      <td class="mono truncate" title="${esc(n.sni)}">${esc(n.sni)}</td>
      <td><span class="mono" style="color:var(--muted)">${esc(n.dest)}</span></td>
      <td>${n.client_count}</td>
      <td>
        <label class="switch"><input type="checkbox" data-toggle="${n.id}" ${n.enabled ? 'checked' : ''}><span></span></label>
      </td>
      <td class="row-actions">
        <button class="icon-btn" data-act="edit" data-id="${n.id}" title="编辑">${ICON.edit}</button>
        <button class="icon-btn" data-act="keys" data-id="${n.id}" title="更换 REALITY 密钥">${ICON.key}</button>
        <button class="icon-btn danger" data-act="del" data-id="${n.id}" title="删除">${ICON.trash}</button>
      </td>
    </tr>`).join('');

  return `
    <div class="card">
      <div class="card-head">
        <h3>节点列表</h3>
        <div class="spacer"></div>
        <button class="btn btn-primary btn-sm" id="new-node">${ICON.plus}<span>新建节点</span></button>
      </div>
      ${STATE.nodes.length ? `
      <div class="table-wrap">
        <table id="node-table">
          <thead><tr>
            <th>名称</th><th>服务器</th><th>传输</th><th>端口</th><th>SNI</th><th>回落</th><th>订阅数</th><th>启用</th><th></th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>` : `
      <div class="empty"><div class="big">◎</div>还没有节点。先建一个 Vision 节点，再考虑加一个 XHTTP 作为备用入口。</div>`}
      <div class="hint" style="margin-top:12px">
        Vision 走 TCP + XTLS，延迟最低；XHTTP 走 HTTP 传输，抗干扰更强，适合 CDN 或备用。
        两者共用同一个 REALITY 回落链路。
      </div>
    </div>`;
}

function bindNodes() {
  const create = $('#new-node');
  if (create) create.addEventListener('click', () => openNodeModal(null));

  const table = $('#node-table');
  if (!table) return;

  table.addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-act]');
    if (!btn) return;
    const id = Number(btn.dataset.id);
    const node = STATE.nodes.find((n) => n.id === id);
    if (!node) return;

    if (btn.dataset.act === 'edit') return openNodeModal(node);

    if (btn.dataset.act === 'keys') {
      if (!(await confirmDialog('更换 REALITY 密钥', '更换后所有客户端都必须重新导入订阅，否则无法连接。确定继续？', true))) return;
      try {
        await api(`/api/nodes/${id}/keys`, { method: 'POST' });
        toast('密钥已更换，请让客户端重新拉取订阅');
        await refresh();
      } catch (err) { toast(err.message, 'err'); }
      return;
    }

    if (btn.dataset.act === 'del') {
      if (!(await confirmDialog('删除节点', `确定删除「${node.name}」？该节点上的所有订阅凭据会一起删除。`, true))) return;
      try {
        await api(`/api/nodes/${id}`, { method: 'DELETE' });
        toast('节点已删除');
        await refresh();
      } catch (err) { toast(err.message, 'err'); }
    }
  });

  $$('input[data-toggle]', table).forEach((cb) => {
    cb.addEventListener('change', async () => {
      const id = Number(cb.dataset.toggle);
      try {
        await api(`/api/nodes/${id}`, { method: 'PATCH', body: { enabled: cb.checked } });
        toast(cb.checked ? '节点已启用' : '节点已停用');
        await refresh();
      } catch (err) {
        cb.checked = !cb.checked;
        toast(err.message, 'err');
      }
    });
  });
}

function nodeForm(n) {
  const transport = n.transport || 'vision';
  const fingerprint = n.fingerprint || STATE.settings.fingerprint || 'chrome';
  const shortIds = (n.short_ids || []).join(',');
  const servers = STATE.servers || [];
  const serverId = Number(n.server_id || (servers[0] && servers[0].id) || 1);
  const currentServer = servers.find((server) => server.id === serverId);
  const defaultSni = n.sni || (currentServer && currentServer.domain) || STATE.settings.default_sni || '';
  return `
    <div class="field"><label>节点名称</label>
      <input class="input" name="name" value="${esc(n.name || '')}" placeholder="香港 · Vision" maxlength="48" required></div>

    <div class="field"><label>所属服务器</label>
      <select class="select" name="server_id">
        ${servers.map((server) => `<option value="${server.id}" ${server.id === serverId ? 'selected' : ''}>${esc(server.name)} · ${esc(server.address || '本机')}</option>`).join('')}
      </select>
      <div class="hint">节点配置会随「应用配置」下发到这台服务器。</div></div>

    <div class="form-row">
      <div class="field"><label>传输方式</label>
        <select class="select" name="transport">
          <option value="vision" ${transport === 'vision' ? 'selected' : ''}>Vision（TCP + XTLS）</option>
          <option value="xhttp" ${transport === 'xhttp' ? 'selected' : ''}>XHTTP</option>
        </select></div>
      <div class="field"><label>监听端口</label>
        <input class="input" type="number" name="port" min="1" max="65535" value="${n.port || 443}"></div>
    </div>

    <div class="field"><label>SNI 域名</label>
      <input class="input" name="sni" value="${esc(defaultSni)}" placeholder="node.example.com">
      <div class="hint">必须与这台服务器上 Nginx 的证书域名完全一致。</div></div>

    <div class="form-row">
      <div class="field"><label>回落地址 dest</label>
        <input class="input" name="dest" value="${esc(n.dest || STATE.settings.dest || '127.0.0.1:8003')}"></div>
      <div class="field"><label>PROXY protocol</label>
        <select class="select" name="xver">
          <option value="1" ${Number(n.xver ?? 1) === 1 ? 'selected' : ''}>v1（推荐，Nginx 可拿真实 IP）</option>
          <option value="0" ${Number(n.xver ?? 1) === 0 ? 'selected' : ''}>关闭</option>
          <option value="2" ${Number(n.xver ?? 1) === 2 ? 'selected' : ''}>v2</option>
        </select></div>
    </div>

    <div class="form-row">
      <div class="field"><label>uTLS 指纹</label>
        <select class="select" name="fingerprint">
          ${STATE.meta.fingerprints.map((f) => `<option value="${f}" ${f === fingerprint ? 'selected' : ''}>${f}</option>`).join('')}
        </select></div>
      <div class="field"><label>shortId</label>
        <input class="input" name="short_ids" value="${esc(shortIds)}" placeholder="留空则自动生成">
        <div class="hint">多个用逗号分隔，最长 16 位十六进制。</div></div>
    </div>

    <div id="xhttp-fields" class="${transport === 'xhttp' ? '' : 'hidden'}">
      <div class="form-row">
        <div class="field"><label>XHTTP 路径</label>
          <input class="input" name="xhttp_path" value="${esc(n.xhttp_path || '/')}" placeholder="/reality"></div>
        <div class="field"><label>XHTTP 模式</label>
          <select class="select" name="xhttp_mode">
            ${STATE.meta.xhttp_modes.map((m) => `<option value="${m}" ${m === (n.xhttp_mode || 'auto') ? 'selected' : ''}>${m}</option>`).join('')}
          </select></div>
      </div>
      <div class="hint" style="margin-top:-6px;margin-bottom:12px">XHTTP 不支持 Vision flow；建议路径随机化，避免被按路径探测。</div>
    </div>

    <div class="field"><label>备注</label>
      <input class="input" name="remark" value="${esc(n.remark || '')}" placeholder="可选"></div>

    ${n.public_key ? `<div class="field"><label>REALITY 公钥（客户端使用）</label>
      <input class="input mono" readonly value="${esc(n.public_key)}"></div>` : ''}

    <label class="check-item"><input type="checkbox" name="enabled" ${n.enabled !== false ? 'checked' : ''}>
      <span>启用该节点</span></label>`;
}

function openNodeModal(node) {
  const editing = !!node;
  const m = openModal({
    title: editing ? `编辑节点 · ${node.name}` : '新建节点',
    wide: true,
    body: `<form id="node-form">${nodeForm(node || {})}</form>`,
    footer: `<button class="btn" data-cancel>取消</button>
      <button class="btn btn-primary" id="node-save">${editing ? '保存' : '创建'}</button>`,
  });
  const form = $('#node-form', m.modal);
  $('[data-cancel]', m.modal).onclick = () => m.close();

  const transportSel = form.querySelector('[name=transport]');
  transportSel.addEventListener('change', () => {
    $('#xhttp-fields', form).classList.toggle('hidden', transportSel.value !== 'xhttp');
  });

  const serverSel = form.querySelector('[name=server_id]');
  const sniInput = form.querySelector('[name=sni]');
  if (serverSel && sniInput) {
    serverSel.addEventListener('change', () => {
      const selected = STATE.servers.find((server) => String(server.id) === serverSel.value);
      const domains = new Set((STATE.servers || []).map((server) => server.domain).filter(Boolean));
      const current = sniInput.value.trim();
      if (selected && (!current || domains.has(current))) {
        sniInput.value = selected.domain || STATE.settings.default_sni || '';
      }
    });
  }

  $('#node-save', m.modal).onclick = async () => {
    if (!form.reportValidity()) return;
    const fd = new FormData(form);
    const body = {
      name: String(fd.get('name') || '').trim(),
      server_id: Number(fd.get('server_id')),
      transport: String(fd.get('transport')),
      port: Number(fd.get('port')),
      sni: String(fd.get('sni') || '').trim(),
      dest: String(fd.get('dest') || '').trim(),
      xver: Number(fd.get('xver')),
      fingerprint: String(fd.get('fingerprint')),
      short_ids: String(fd.get('short_ids') || '').split(',').map((s) => s.trim()).filter(Boolean),
      xhttp_path: String(fd.get('xhttp_path') || '/').trim(),
      xhttp_mode: String(fd.get('xhttp_mode')),
      remark: String(fd.get('remark') || '').trim(),
      enabled: fd.get('enabled') === 'on',
    };
    const btn = $('#node-save', m.modal);
    btn.disabled = true;
    try {
      if (editing) await api(`/api/nodes/${node.id}`, { method: 'PATCH', body });
      else await api('/api/nodes', { method: 'POST', body });
      m.close();
      toast(editing ? '节点已更新' : '节点已创建');
      await refresh();
    } catch (err) {
      toast(err.message, 'err');
      btn.disabled = false;
    }
  };

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    $('#node-save', m.modal).click();
  });
}

/* ------------------------------------------------------------ 订阅用户 */

function viewSubs() {
  const rows = STATE.subs.map((s) => `
    <tr>
      <td>
        <div class="cell-title">${esc(s.name)}</div>
        <div class="cell-sub">${esc(s.note || `创建于 ${fmtTime(s.created_at)}`)}</div>
      </td>
      <td>${s.node_count} 个</td>
      <td>${fmtQuota(s.used_bytes, s.quota_bytes)}</td>
      <td>${fmtTime(s.expires_at)}</td>
      <td><span class="tag ${s.enabled ? 'tag-on' : 'tag-off'}">${s.enabled ? '正常' : '停用'}</span></td>
      <td class="row-actions">
        <button class="btn btn-sm" data-act="links" data-id="${s.id}">订阅</button>
        <button class="icon-btn" data-act="edit" data-id="${s.id}" title="编辑">${ICON.edit}</button>
        <button class="icon-btn" data-act="reset" data-id="${s.id}" title="重置流量">${ICON.reset}</button>
        <button class="icon-btn" data-act="rotate" data-id="${s.id}" title="重置链接与 UUID">${ICON.refresh}</button>
        <button class="icon-btn danger" data-act="del" data-id="${s.id}" title="删除">${ICON.trash}</button>
      </td>
    </tr>`).join('');

  return `
    <div class="card">
      <div class="card-head">
        <h3>订阅用户</h3><div class="spacer"></div>
        <span class="card-sub">一个订阅可同时包含 Vision 与 XHTTP 节点</span>
        <button class="btn btn-primary btn-sm" id="new-sub">${ICON.plus}<span>新建订阅</span></button>
      </div>
      ${STATE.subs.length ? `
      <div class="table-wrap">
        <table id="sub-table">
          <thead><tr><th>名称</th><th>节点</th><th>已用 / 额度</th><th>到期</th><th>状态</th><th></th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>` : `
      <div class="empty"><div class="big">◎</div>还没有订阅用户。创建后把订阅链接发给客户端即可。</div>`}
      <div class="hint" style="margin-top:12px">
        订阅地址里带 token，等同于密码，请只发给使用者本人。需要作废时用「刷新」按钮重置。
      </div>
    </div>`;
}

function subForm(sub) {
  const checked = new Set(STATE.clients.filter((c) => c.sub_id === (sub ? sub.id : -1)).map((c) => c.node_id));
  if (!sub && STATE.nodes.length === 1) checked.add(STATE.nodes[0].id);

  const remainingDays = sub && sub.expires_at
    ? Math.max(0, Math.round((sub.expires_at - Date.now() / 1000) / 86400))
    : 0;
  const quotaGb = sub && sub.quota_bytes ? Math.round((sub.quota_bytes / 1024 ** 3) * 100) / 100 : 0;

  const nodeList = STATE.nodes.map((n) => `
    <label class="check-item">
      <input type="checkbox" name="node" value="${n.id}" ${checked.has(n.id) ? 'checked' : ''}>
      <span class="tag tag-${n.transport}">${n.transport === 'xhttp' ? 'XHTTP' : 'Vision'}</span>
      <span>${esc(n.name)}</span>
      <span style="margin-left:auto;color:var(--muted-2)" class="mono">:${n.port}</span>
    </label>`).join('') || '<div class="hint">还没有节点，请先去「节点」创建。</div>';

  return `
    <div class="field"><label>订阅名称</label>
      <input class="input" name="name" value="${esc(sub ? sub.name : '')}" placeholder="朋友 A" maxlength="48" required></div>

    <div class="field"><label>包含节点</label>
      <div class="check-list">${nodeList}</div></div>

    <div class="form-row">
      <div class="field"><label>有效期（天）</label>
        <input class="input" type="number" name="expires_days" min="0" max="36500" value="${remainingDays}">
        <div class="hint">0 表示永久</div></div>
      <div class="field"><label>流量额度（GB）</label>
        <input class="input" type="number" name="quota_gb" min="0" step="0.5" value="${quotaGb}">
        <div class="hint">0 表示不限</div></div>
    </div>

    <div class="field"><label>备注</label>
      <input class="input" name="note" value="${esc(sub ? sub.note : '')}" maxlength="200"></div>`;
}

function openSubModal(sub) {
  const editing = !!sub;
  const m = openModal({
    title: editing ? `编辑订阅 · ${sub.name}` : '新建订阅用户',
    wide: true,
    body: `<form id="sub-form">${subForm(sub || null)}</form>`,
    footer: `<button class="btn" data-cancel>取消</button>
      <button class="btn btn-primary" id="sub-save">${editing ? '保存' : '创建'}</button>`,
  });
  const form = $('#sub-form', m.modal);
  $('[data-cancel]', m.modal).onclick = () => m.close();

  $('#sub-save', m.modal).onclick = async () => {
    if (!form.reportValidity()) return;
    const fd = new FormData(form);
    const nodeIds = Array.from(form.querySelectorAll('input[name=node]:checked')).map((el) => Number(el.value));
    const body = {
      name: String(fd.get('name') || '').trim(),
      expires_days: Number(fd.get('expires_days') || 0),
      quota_gb: Number(fd.get('quota_gb') || 0),
      note: String(fd.get('note') || '').trim(),
    };
    const btn = $('#sub-save', m.modal);
    btn.disabled = true;
    try {
      if (editing) {
        await api(`/api/subs/${sub.id}`, { method: 'PATCH', body });
        await api(`/api/subs/${sub.id}/nodes`, { method: 'POST', body: { node_ids: nodeIds } });
      } else {
        await api('/api/subs', { method: 'POST', body: { ...body, node_ids: nodeIds } });
      }
      m.close();
      toast(editing ? '订阅已更新' : '订阅已创建');
      await refresh();
    } catch (err) {
      toast(err.message, 'err');
      btn.disabled = false;
    }
  };

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    $('#sub-save', m.modal).click();
  });
}

async function openLinks(sub) {
  let data;
  try {
    data = await api(`/api/subs/${sub.id}/links`);
  } catch (err) {
    toast(err.message, 'err');
    return;
  }
  const rows = data.links.map((link) => `
    <div class="copy-row" style="margin-bottom:8px">
      <input class="input" readonly value="${esc(link)}">
      <button class="btn btn-sm" data-copy="${esc(link)}">${ICON.copy}</button>
    </div>`).join('') || '<div class="hint">该订阅还没有可用节点。</div>';

  const m = openModal({
    title: `订阅链接 · ${sub.name}`,
    wide: true,
    body: `
      <div class="field"><label>订阅地址（v2rayN / v2rayNG / NekoBox）</label>
        <div class="copy-row">
          <input class="input" id="link-sub" readonly value="${esc(data.sub_url)}">
          <button class="btn btn-sm" data-copy="${esc(data.sub_url)}">${ICON.copy}</button>
          <button class="btn btn-sm" data-qr="${esc(data.sub_url)}" data-qr-title="订阅二维码">${ICON.qr}</button>
        </div>
        <div class="hint">客户端只需这一个地址；节点变更后自动同步。</div></div>

      <div class="field"><label>Clash / mihomo 订阅</label>
        <div class="copy-row">
          <input class="input" id="link-clash" readonly value="${esc(data.clash_url)}">
          <button class="btn btn-sm" data-copy="${esc(data.clash_url)}">${ICON.copy}</button>
          <button class="btn btn-sm" data-qr="${esc(data.clash_url)}" data-qr-title="Clash 订阅二维码">${ICON.qr}</button>
        </div>
        <div class="hint">需要 mihomo 内核（原版 Clash 不支持 REALITY）。</div></div>

      <div class="field"><label>单节点链接</label>${rows}</div>`,
    footer: '<button class="btn" data-close2>关闭</button>',
  });
  $('[data-close2]', m.modal).onclick = () => m.close();

  m.overlay.addEventListener('click', (e) => {
    const copyBtn = e.target.closest('[data-copy]');
    if (copyBtn) { copyText(copyBtn.dataset.copy); return; }
    const qrBtn = e.target.closest('[data-qr]');
    if (qrBtn) showQr(qrBtn.dataset.qrTitle || '二维码', qrBtn.dataset.qr);
  });
}

function bindSubs() {
  const create = $('#new-sub');
  if (create) create.addEventListener('click', () => openSubModal(null));

  const table = $('#sub-table');
  if (!table) return;

  table.addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-act]');
    if (!btn) return;
    const id = Number(btn.dataset.id);
    const sub = STATE.subs.find((s) => s.id === id);
    if (!sub) return;

    if (btn.dataset.act === 'links') return openLinks(sub);
    if (btn.dataset.act === 'edit') return openSubModal(sub);

    if (btn.dataset.act === 'reset') {
      if (!(await confirmDialog('重置流量', `把「${sub.name}」的已用流量清零？只影响统计，不影响连接。`, true))) return;
      try {
        await api(`/api/subs/${id}/reset-traffic`, { method: 'POST' });
        toast('流量已清零');
        await refresh();
      } catch (err) { toast(err.message, 'err'); }
      return;
    }

    if (btn.dataset.act === 'rotate') {
      if (!(await confirmDialog('重置订阅', '旧订阅地址和所有 UUID 会立即失效，已导入的客户端需要重新添加。确定继续？', true))) return;
      try {
        await api(`/api/subs/${id}/rotate`, { method: 'POST' });
        toast('订阅已重置');
        await refresh();
      } catch (err) { toast(err.message, 'err'); }
      return;
    }

    if (btn.dataset.act === 'del') {
      if (!(await confirmDialog('删除订阅', `确定删除「${sub.name}」？其所有节点凭据会一并删除。`, true))) return;
      try {
        await api(`/api/subs/${id}`, { method: 'DELETE' });
        toast('订阅已删除');
        await refresh();
      } catch (err) { toast(err.message, 'err'); }
    }
  });
}

/* ------------------------------------------------------------ 自偷自向导 */

async function viewSelfsteal() {
  if (!STATE.nodes.length) {
    return `<div class="card empty"><div class="big">◎</div>
      还没有节点。先在「节点」创建一个 Vision 或 XHTTP 节点，再回来生成自偷自配置。
      <div style="margin-top:14px"><a class="btn btn-sm" href="#/nodes">去创建节点</a></div></div>`;
  }

  const node = STATE.nodes.find((n) => n.id === SS_NODE) || STATE.nodes[0];
  SS_NODE = node.id;
  const plan = await api(`/api/selfsteal?node_id=${node.id}`);
  const warnings = (plan.warnings || []).map((w) => `<div class="notice warn" style="margin-bottom:8px">${esc(w)}</div>`).join('');
  const steps = plan.steps.map((s) => `
    <div class="step">
      <div class="step-title">${esc(s.title)}</div>
      <div class="step-detail">${esc(s.detail)}</div>
      ${s.command ? `<div class="step-cmd">
        <pre>${esc(s.command)}</pre>
        <button class="btn btn-sm" data-copy="${esc(s.command)}">${ICON.copy}</button>
      </div>` : ''}
    </div>`).join('');

  const selector = STATE.nodes.length > 1 ? `
    <select class="select" id="ss-node" style="max-width:280px">
      ${STATE.nodes.map((n) => `<option value="${n.id}" ${n.id === node.id ? 'selected' : ''}>${esc(n.name)} · :${n.port}</option>`).join('')}
    </select>` : '';

  return `
    <div class="card">
      <div class="card-head">
        <h3>自己偷自己</h3><div class="spacer"></div>${selector}
      </div>
      <div class="chain">
        ${chainItem(1, '客户端 Xray REALITY', `连接 <code>${esc(STATE.public_host)}:${node.port}</code>，SNI <code>${esc(plan.sni || node.sni)}</code>`)}
        ${chainItem(2, '验证握手', 'REALITY 校验 TLS 指纹、SNI、公钥、shortId，通过后进入 VLESS')}
        ${chainItem(3, `PROXY protocol → ${esc(plan.listen)}`, `未通过校验的连接原样转发，v${plan.xver} 头携带真实源 IP`)}
        ${chainItem(4, 'Nginx 本地 TLS', `加载 <code>${esc(plan.cert_path || '证书')}</code>，证书必须与 SNI 完全一致`)}
        ${chainItem(5, `反向代理 ${esc(plan.upstream_host)}`, '返回真实站点内容，探针与浏览器看到的是一个正常网站')}
      </div>
      <div class="notice info" style="margin-top:14px">
        为什么用自有域名：REALITY 不自己出示证书，未认证连接会原样交给 dest 完成握手。
        只有你自己的域名才能签发匹配证书，所以这是唯一稳定、又不依赖第三方的做法。
      </div>
    </div>

    ${warnings ? `<div style="margin-top:16px">${warnings}</div>` : ''}

    <div class="card" style="margin-top:16px">
      <div class="card-head">
        <h3>Nginx 回落配置</h3><div class="spacer"></div>
        <span class="card-sub mono">${esc(plan.config_path || '')}</span>
        <button class="btn btn-sm" data-copy="${esc(plan.conf || '')}">${ICON.copy}<span>复制</span></button>
        <button class="btn btn-sm" id="ss-download">${ICON.download}<span>下载</span></button>
      </div>
      ${plan.error
        ? `<div class="notice danger">${esc(plan.error)}</div>`
        : `<div class="code-block"><div class="code-head"><span>reality-selfsteal.conf</span><div class="spacer"></div>
             <span>nginx -t 后再 reload</span></div>
           <pre>${esc(plan.conf)}</pre></div>`}
      ${plan.server && plan.server.kind !== 'local'
        ? `<div style="margin-top:14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
             <button class="btn btn-primary btn-sm" id="ss-push">${ICON.push}<span>推送到 ${esc(plan.server.name)}</span></button>
             <span class="hint">通过 agent 写入 nginx 并 reload；证书需要先在那台机器上签好。</span>
           </div>`
        : `<div class="hint" style="margin-top:12px">本机请按上面的步骤手动写入 ${esc(plan.config_path || '')}。</div>`}
    </div>

    <div class="card" style="margin-top:16px">
      <div class="card-head"><h3>部署步骤</h3></div>
      <div class="steps">${steps}</div>
    </div>`;
}

function bindSelfsteal() {
  const sel = $('#ss-node');
  if (sel) {
    sel.addEventListener('change', async () => {
      SS_NODE = Number(sel.value);
      await route();
    });
  }
  const dl = $('#ss-download');
  if (dl) {
    dl.addEventListener('click', async () => {
      const plan = await api(`/api/selfsteal?node_id=${SS_NODE || STATE.nodes[0].id}`);
      const blob = new Blob([plan.conf || ''], { type: 'text/plain;charset=utf-8' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'reality-selfsteal.conf';
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 3000);
    });
  }

  const push = $('#ss-push');
  if (push) {
    push.addEventListener('click', async () => {
      const nodeId = SS_NODE || (STATE.nodes[0] && STATE.nodes[0].id);
      if (!nodeId) return;
      push.disabled = true;
      try {
        const result = await api('/api/selfsteal/apply', { method: 'POST', body: { node_id: nodeId } });
        if (result.ok) {
          toast('Nginx 配置已推送并 reload');
        } else {
          const detail = (result.result && (result.result.test_output || result.result.error)) || '推送失败';
          toast(detail, 'err', 6000);
        }
        await refresh();
      } catch (err) {
        toast(err.message, 'err');
      } finally {
        push.disabled = false;
      }
    });
  }

  const host = $('#view');
  host.onclick = (e) => {
    const btn = e.target.closest('[data-copy]');
    if (btn) copyText(btn.dataset.copy);
  };
}

/* ------------------------------------------------------------ 日志 */

async function viewLogs() {
  let data;
  try {
    data = await api('/api/logs?lines=300');
  } catch (err) {
    return `<div class="notice danger">${esc(err.message)}</div>`;
  }
  const text = (data.lines || []).join('\n') || '（暂无日志）';
  return `
    <div class="card">
      <div class="card-head">
        <h3>Xray 错误日志</h3><div class="spacer"></div>
        <span class="card-sub mono">${esc(data.path || '')}</span>
        <button class="btn btn-sm" id="log-refresh">${ICON.refresh}<span>刷新</span></button>
      </div>
      <div class="code-block"><pre style="max-height:60vh">${esc(text)}</pre></div>
    </div>`;
}

function bindLogs() {
  const btn = $('#log-refresh');
  if (btn) btn.addEventListener('click', () => route());
}

/* ------------------------------------------------------------ 审计 */

async function viewAudit() {
  let data;
  try {
    data = await api('/api/audit?limit=300');
  } catch (err) {
    return `<div class="notice danger">${esc(err.message)}</div>`;
  }
  const items = data.items || [];
  const rows = items.map((item) => `
    <tr>
      <td class="mono" style="white-space:nowrap">${fmtTime(item.at)}</td>
      <td>${esc(item.actor)}</td>
      <td><span class="tag tag-off">${esc(item.action)}</span></td>
      <td>${esc(item.target || '—')}</td>
      <td class="cell-sub">${esc(item.detail || '')}</td>
      <td class="mono">${esc(item.ip || '')}</td>
    </tr>`).join('');

  return `
    <div class="card">
      <div class="card-head"><h3>操作审计</h3><div class="spacer"></div>
        <span class="card-sub">最近 ${items.length} 条 · 自动保留 2000 条</span>
        <button class="btn btn-sm" id="audit-refresh">${ICON.refresh}<span>刷新</span></button></div>
      ${rows ? `<div class="table-wrap"><table>
        <thead><tr><th>时间</th><th>操作者</th><th>动作</th><th>对象</th><th>详情</th><th>IP</th></tr></thead>
        <tbody>${rows}</tbody></table></div>`
        : '<div class="empty"><div class="big">◎</div>还没有操作记录。</div>'}
      <div class="hint" style="margin-top:12px">登录、节点/订阅变更、应用配置、备份恢复都会记录在这里。</div>
    </div>`;
}

function bindAudit() {
  const btn = $('#audit-refresh');
  if (btn) btn.addEventListener('click', () => route());
}

/* ------------------------------------------------------------ 设置 */

function settingsField(key, label, hint = '', type = 'text', placeholder = '') {
  const value = STATE.settings[key] ?? '';
  return `
    <div class="field">
      <label>${label}</label>
      <input class="input" name="${key}" type="${type}" value="${esc(value)}" placeholder="${esc(placeholder)}" data-setting>
      ${hint ? `<div class="hint">${hint}</div>` : ''}
    </div>`;
}

function viewSettings() {
  const s = STATE.settings;
  return `
    <div class="grid grid-2">
      <div class="card">
        <div class="card-head"><h3>面板</h3></div>
        ${settingsField('panel_name', '面板名称', '显示在标题和订阅备注里')}
        ${settingsField('public_host', '公网地址', '订阅与分享链接中的服务器地址；留空自动探测出口 IP', 'text', '1.2.3.4')}
        ${settingsField('sub_base', '订阅根地址', '例如 https://node.example.com；留空则用 SNI 域名', 'text', 'https://node.example.com')}
      </div>

      <div class="card">
        <div class="card-head"><h3>REALITY 默认值</h3></div>
        ${settingsField('default_sni', '默认 SNI', '新建节点时自动填入，必须是有证书的自有域名', 'text', 'node.example.com')}
        ${settingsField('dest', '默认回落地址', '本机 nginx 的监听地址', 'text', '127.0.0.1:8003')}
        <div class="field"><label>默认 PROXY protocol</label>
          <select class="select" name="xver" data-setting>
            <option value="1" ${s.xver === '1' ? 'selected' : ''}>v1</option>
            <option value="0" ${s.xver === '0' ? 'selected' : ''}>关闭</option>
            <option value="2" ${s.xver === '2' ? 'selected' : ''}>v2</option>
          </select></div>
        <div class="field"><label>默认 uTLS 指纹</label>
          <select class="select" name="fingerprint" data-setting>
            ${STATE.meta.fingerprints.map((f) => `<option value="${f}" ${f === s.fingerprint ? 'selected' : ''}>${f}</option>`).join('')}
          </select></div>
      </div>
    </div>

    <div class="card" style="margin-top:16px">
      <div class="card-head"><h3>Xray</h3><div class="spacer"></div>
        <span class="card-sub">${STATE.xray.installed ? esc(STATE.xray.version) : '未检测到 xray'}</span></div>
      <div class="grid grid-2">
        <div>
          ${settingsField('xray_bin', 'xray 可执行文件', 'PATH 中的命令名或绝对路径', 'text', 'xray')}
          ${settingsField('xray_config', '配置文件路径', '', 'text', '/usr/local/etc/xray/config.json')}
          ${settingsField('xray_api', '统计 API 地址', '面板通过它读取每用户流量', 'text', '127.0.0.1:10085')}
        </div>
        <div>
          ${settingsField('restart_cmd', '重启命令', '需要能免密执行', 'text', 'sudo -n systemctl restart xray')}
          ${settingsField('status_cmd', '状态命令', '', 'text', 'systemctl is-active xray')}
          ${settingsField('xray_log', '错误日志路径', '', 'text', '/var/log/xray/error.log')}
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:16px">
      <div class="card-head"><h3>自偷自 · Nginx</h3></div>
      <div class="grid grid-2">
        <div>
          ${settingsField('nginx_listen', 'Nginx 监听', '必须是 127.0.0.1 上的端口，与节点 dest 一致', 'text', '127.0.0.1:8003')}
          ${settingsField('nginx_upstream', '伪装上游站点', '返回给探针的真实网站', 'text', 'https://www.lovelive-anime.jp')}
        </div>
        <div>
          ${settingsField('nginx_conf', '配置文件路径', '', 'text', '/etc/nginx/conf.d/reality-selfsteal.conf')}
          ${settingsField('cert_dir', '证书目录', '结构为 <cert_dir>/<域名>/fullchain.pem', 'text', '/etc/letsencrypt/live')}
          ${settingsField('panel_addr', '面板内网地址', 'nginx 把 /sub/ 反代到这里', 'text', '127.0.0.1:8080')}
        </div>
      </div>
      <div class="notice info" style="margin-top:6px">
        证书必须由公网可信 CA 签发（Let's Encrypt 即可）。自签证书会让探针直接判定异常。
      </div>
    </div>

    <div class="card" style="margin-top:16px">
      <div class="card-head"><h3>订阅</h3></div>
      ${settingsField('sub_interval_hours', '客户端更新间隔（小时）', '写入订阅响应的 Profile-Update-Interval', 'number', '12')}
    </div>

    <div class="card" style="margin-top:16px">
      <div class="card-head">
        <h3>访问白名单</h3><div class="spacer"></div>
        <span class="card-sub">当前 IP：<code>${esc(STATE.client_ip || '未知')}</code></span>
        <button class="btn btn-sm" id="fill-my-ip">填入当前 IP</button>
      </div>
      <div class="field">
        <label>允许访问面板的 IP / CIDR</label>
        <textarea class="textarea" name="access_allowlist" data-setting rows="4"
          placeholder="1.2.3.4&#10;10.0.0.0/8&#10;2001:db8::/32">${esc(s.access_allowlist || '')}</textarea>
        <div class="hint">一行一个，支持 IPv4 / IPv6 / CIDR；留空表示不限制。
          只限制面板与 API，<b>不影响 <code>/sub/</code> 订阅</b>。</div>
      </div>
      <label class="check-item">
        <input type="checkbox" name="access_allowlist_loopback" data-setting
          ${s.access_allowlist_loopback !== '0' ? 'checked' : ''}>
        <span>始终允许本机回环 <code>127.0.0.1 / ::1</code>（SSH 隧道、本机 nginx 需要）</span>
      </label>
      <label class="check-item" style="margin-top:8px">
        <input type="checkbox" name="access_allowlist_sub" data-setting
          ${s.access_allowlist_sub === '1' ? 'checked' : ''}>
        <span>同时限制订阅接口 <code>/sub/</code>（默认关闭，否则客户端会拉不到订阅）</span>
      </label>
      <div class="notice warn" style="margin-top:12px">
        保存时如果当前 IP 不在名单里，面板会拒绝保存，避免把自己锁死。
        真锁死了就在服务器上执行 <code>python3 app.py allow 你的IP</code>。
      </div>
    </div>

    <div style="margin-top:16px;display:flex;gap:10px">
      <button class="btn btn-primary" id="save-settings">保存设置</button>
    </div>

    <div class="card" style="margin-top:16px">
      <div class="card-head"><h3>备份与恢复</h3></div>
      <div class="hint">备份包含 REALITY 私钥与所有用户 UUID，等同于服务器控制权，请妥善保管。</div>
      <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
        <a class="btn" href="/api/export">${ICON.download}<span>导出备份</span></a>
        <label class="btn" style="cursor:pointer">${ICON.upload}<span>恢复备份</span>
          <input type="file" id="import-file" accept="application/json,.json" hidden></label>
      </div>
      <div class="hint" style="margin-top:10px">恢复会覆盖当前全部节点、订阅与流量记录，操作前建议先导出一份。</div>
    </div>

    <div class="card" style="margin-top:16px">
      <div class="card-head"><h3>修改密码</h3></div>
      <form id="password-form" class="grid grid-3">
        <div class="field"><label>当前密码</label>
          <input class="input" type="password" name="current" autocomplete="current-password" required></div>
        <div class="field"><label>新密码</label>
          <input class="input" type="password" name="password" autocomplete="new-password" minlength="10" required></div>
        <div class="field"><label>确认新密码</label>
          <input class="input" type="password" name="confirm" minlength="10" required></div>
      </form>
      <button class="btn" id="save-password" style="margin-top:4px">更新密码</button>
    </div>`;
}

function bindSettings() {
  $('#save-settings').addEventListener('click', async () => {
    const body = {};
    $$('[data-setting]').forEach((el) => {
      body[el.name] = el.type === 'checkbox' ? (el.checked ? '1' : '0') : el.value;
    });
    const btn = $('#save-settings');
    btn.disabled = true;
    try {
      await api('/api/settings', { method: 'POST', body });
      toast('设置已保存');
      await refresh();
    } catch (err) {
      toast(err.message, 'err');
      btn.disabled = false;
    }
  });

  const fillIp = $('#fill-my-ip');
  if (fillIp) {
    fillIp.addEventListener('click', () => {
      const box = $('textarea[name=access_allowlist]');
      const ip = STATE.client_ip || '';
      if (!box || !ip) {
        toast('拿不到当前 IP', 'err');
        return;
      }
      const lines = box.value.split('\n').map((line) => line.trim()).filter(Boolean);
      if (lines.includes(ip)) {
        toast('当前 IP 已经在列表里');
        return;
      }
      lines.push(ip);
      box.value = lines.join('\n');
      toast('已填入当前 IP，记得点「保存设置」');
    });
  }

  $('#save-password').addEventListener('click', async () => {
    const form = $('#password-form');
    if (!form.reportValidity()) return;
    const fd = new FormData(form);
    if (fd.get('password') !== fd.get('confirm')) {
      toast('两次输入的新密码不一致', 'err');
      return;
    }
    try {
      const data = await api('/api/password', {
        method: 'POST',
        body: { current: fd.get('current'), password: fd.get('password') },
      });
      CSRF = data.csrf;
      form.reset();
      toast('密码已更新');
    } catch (err) {
      toast(err.message, 'err');
    }
  });

  $('#password-form').addEventListener('submit', (e) => {
    e.preventDefault();
    $('#save-password').click();
  });

  const importInput = $('#import-file');
  if (importInput) {
    importInput.addEventListener('change', async () => {
      const file = importInput.files && importInput.files[0];
      if (!file) return;
      let data;
      try {
        data = JSON.parse(await file.text());
      } catch {
        toast('文件不是合法 JSON', 'err');
        importInput.value = '';
        return;
      }
      const nodes = Array.isArray(data.nodes) ? data.nodes.length : 0;
      const subs = Array.isArray(data.subs) ? data.subs.length : 0;
      const ok = await confirmDialog(
        '恢复备份',
        `将用备份覆盖当前数据：${nodes} 个节点、${subs} 个订阅，现有配置会被删除且不可撤销。继续？`,
        true,
      );
      if (!ok) {
        importInput.value = '';
        return;
      }
      try {
        const result = await api('/api/import', { method: 'POST', body: data });
        toast(`已恢复 ${result.servers} 台服务器 / ${result.nodes} 个节点 / ${result.subs} 个订阅，请检查后应用配置`);
        await refresh();
      } catch (err) {
        toast(err.message, 'err');
      }
      importInput.value = '';
    });
  }
}

/* ------------------------------------------------------------ 视图表 */

const VIEWS = {
  dashboard: { title: '概览', sub: '节点、订阅与链路状态', html: viewDashboard, bind: bindDashboard },
  servers: { title: '服务器', sub: '一台主控，多台节点', html: viewServers, bind: bindServers },
  nodes: { title: '节点', sub: 'VLESS + REALITY 入站', html: viewNodes, bind: bindNodes },
  subs: { title: '订阅用户', sub: '一个订阅可横跨多个节点', html: viewSubs, bind: bindSubs },
  selfsteal: { title: '自偷自向导', sub: 'Xray → PROXY protocol → Nginx → 真实站点', html: viewSelfsteal, bind: bindSelfsteal },
  logs: { title: '运行日志', sub: 'Xray 错误日志尾部', html: viewLogs, bind: bindLogs },
  audit: { title: '审计日志', sub: '谁在什么时候改了什么', html: viewAudit, bind: bindAudit },
  settings: { title: '设置', sub: '面板、Xray 与 Nginx', html: viewSettings, bind: bindSettings },
};

/* ------------------------------------------------------------ 启动 */

(async function boot() {
  try {
    BOOTSTRAP = await api('/api/bootstrap');
  } catch {
    /* 面板刚启动时可能还没来得及响应，继续尝试 state */
  }
  if (BOOTSTRAP.setup_required) {
    renderAuth('setup');
    return;
  }
  try {
    await loadState();
  } catch (err) {
    if (err.status === 401) {
      renderAuth('login');
      return;
    }
    const boot = $('#boot');
    if (boot) {
      boot.innerHTML = `<div class="notice danger">无法连接面板：${esc(err.message)}</div>`;
    }
  }
})();
