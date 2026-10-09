'use strict';

/* ============================== helpers ============================== */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const icon = (name, cls = '') => `<svg class="icon ${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const plural = (n, word) => `${fmtNum(n)} ${word}${n === 1 ? '' : 's'}`;

function readPref(key, fallback) { try { return localStorage.getItem('ds.' + key) || fallback; } catch { return fallback; } }
function writePref(key, value) { try { localStorage.setItem('ds.' + key, value); } catch { /* private mode */ } }

function fmtBytes(n) {
  if (n == null) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${i && v < 10 ? v.toFixed(1) : Math.round(v)} ${units[i]}`;
}
const fmtNum = (n) => (n ?? 0).toLocaleString();
const fmtDate = (ts) => (ts ? new Date(ts * 1000).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : '—');
const fmtDateTime = (ts) => (ts ? new Date(ts * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—');
function fmtAgo(ts) {
  if (!ts) return 'never';
  const s = Date.now() / 1000 - ts;
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)} d ago`;
  return fmtDate(ts);
}

const joinPath = (folder, name) => (folder === '/' ? '' : folder) + '/' + name;
const baseName = (path) => path.split('/').filter(Boolean).pop() || 'Files';
const parentOf = (path) => '/' + path.split('/').filter(Boolean).slice(0, -1).join('/');
const folderHash = (folder) => '#/files' + (folder === '/' ? '' : folder.split('/').map(encodeURIComponent).join('/'));

function kindOf(file) {
  const m = file.mime || '';
  if (m.startsWith('image/')) return 'image';
  if (m.startsWith('video/')) return 'video';
  if (m.startsWith('audio/')) return 'audio';
  if (/zip|rar|7z|tar|gzip|compressed/.test(m)) return 'archive';
  if (/pdf|word|document|text|sheet|excel|presentation|powerpoint|rtf|json|xml|csv/.test(m)) return 'doc';
  return 'file';
}
const isMedia = (f) => ['image', 'video'].includes(kindOf(f));
const IN_APP = navigator.userAgent.includes('DataStoreApp'); // the Android app's WebView
if (IN_APP) document.documentElement.classList.add('in-app');

const STATUS = {
  protected: { icon: 'check', label: 'Protected' },
  syncing: { icon: 'sync', label: 'Mirroring' },
  attention: { icon: 'alert', label: 'Needs attention' },
};
function statusLabel(f) {
  if (f.status === 'attention') return f.failed_copies ? 'Retrying' : f.ok_copies ? 'Needs another copy' : 'Not backed up yet';
  return STATUS[f.status].label;
}
const meterClass = (frac) => (frac > 0.9 ? 'bad' : frac > 0.75 ? 'warn' : '');
const meter = (frac, cls = meterClass(frac)) => `<div class="meter ${cls}"><i style="width:${Math.min(100, Math.max(0, frac * 100)).toFixed(1)}%"></i></div>`;

/* ============================== state + api ============================== */
const S = {
  route: { view: 'files', folder: '/' },
  layout: readPref('layout', 'grid'),
  state: null,
  items: [],
  selected: null,
  lightbox: { list: [], index: 0 },
  rclone: null,
};

async function api(path, { method = 'GET', body } = {}) {
  const init = { method, credentials: 'same-origin', headers: {} };
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  const res = await fetch('/api' + path, init);
  const data = (res.headers.get('content-type') || '').includes('json') ? await res.json() : null;
  if (res.status === 401) sessionExpired();
  if (!res.ok) throw new Error(data?.error || `${res.status} ${res.statusText}`);
  return data;
}

let expiredShown = false;
function sessionExpired() {
  if (expiredShown) return;
  expiredShown = true;
  toast('Session expired — reloading…', 'error');
  setTimeout(() => location.reload(), 1200);
}

function toast(message, kind = '') {
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.textContent = message;
  $('#toasts').append(el);
  setTimeout(() => el.remove(), kind === 'error' ? 6500 : 3500);
}

async function refreshState() {
  S.state = await api('/state');
  renderHealth();
  const trashed = S.state.summary.trashed;
  $('#trash-count').textContent = trashed ? fmtNum(trashed) : '';
  return S.state;
}

/* ============================== routing ============================== */
const TITLES = { photos: 'Photos', storage: 'Storage', accounts: 'Accounts', activity: 'Activity', trash: 'Trash' };

function parseRoute() {
  try {
    const [view = '', ...rest] = location.hash.replace(/^#\/?/, '').split('/');
    if (view === 'search') return { view: 'search', q: decodeURIComponent(rest.join('/')) };
    if (TITLES[view]) return { view };
    return { view: 'files', folder: '/' + rest.filter(Boolean).map(decodeURIComponent).join('/') };
  } catch {
    return { view: 'files', folder: '/' };
  }
}

let renderSeq = 0;
async function render({ quiet = false } = {}) {
  const seq = ++renderSeq;
  const previous = S.route;
  S.route = parseRoute();
  const routeChanged = !quiet || JSON.stringify(previous) !== JSON.stringify(S.route);
  renderChrome(routeChanged);
  const view = $('#view');
  const slow = quiet ? null : setTimeout(() => { if (seq === renderSeq) view.innerHTML = '<div class="skeleton"></div>'; }, 160);
  try {
    const html = await VIEWS[S.route.view]();
    if (seq !== renderSeq) return;
    view.innerHTML = html;
    markSelected();
    if (routeChanged && !quiet) $('#content').scrollTop = 0;
  } catch (err) {
    if (seq !== renderSeq) return;
    view.innerHTML = emptyState('alert', 'Something went wrong', esc(err.message), '<button class="btn" data-action="rerender">Try again</button>');
  } finally {
    clearTimeout(slow);
  }
}

function renderChrome(routeChanged) {
  const v = S.route.view;
  $$('#nav a').forEach((a) => a.classList.toggle('active', a.dataset.nav === v));
  let crumbs;
  if (v === 'files') {
    const parts = S.route.folder.split('/').filter(Boolean);
    crumbs = parts.length ? ['<a href="#/files">Files</a>'] : ['<span>Files</span>'];
    parts.forEach((part, i) => {
      const path = '/' + parts.slice(0, i + 1).join('/');
      crumbs.push(icon('chev-right', 'sep'));
      crumbs.push(i === parts.length - 1 ? `<span>${esc(part)}</span>` : `<a href="${folderHash(path)}">${esc(part)}</a>`);
    });
  } else if (v === 'search') {
    crumbs = [`<span>Results for “${esc(S.route.q)}”</span>`];
  } else {
    crumbs = [`<span>${TITLES[v]}</span>`];
  }
  $('#crumbs').innerHTML = crumbs.join('');
  $('#actions').innerHTML = (ACTIONS[v] || (() => ''))();
  if (routeChanged) $('#search').value = v === 'search' ? S.route.q : '';
}

const layoutToggle = () => `<div class="seg" role="group" aria-label="Layout">
  <button class="${S.layout === 'grid' ? 'on' : ''}" data-action="layout" data-value="grid" title="Grid">${icon('grid')}</button>
  <button class="${S.layout === 'list' ? 'on' : ''}" data-action="layout" data-value="list" title="List">${icon('list')}</button></div>`;
const uploadButtons = () => `
  ${IN_APP ? '' : `<button class="btn" data-action="upload-folder" title="Upload a whole folder">${icon('folder')}<span class="label">Folder</span></button>`}
  <button class="btn primary" data-action="upload">${icon('upload')}<span class="label">Upload</span></button>`;

const ACTIONS = {
  files: () => `${layoutToggle()}<button class="icon-btn" data-action="new-folder" title="New folder">${icon('folder-plus')}</button>${uploadButtons()}`,
  search: layoutToggle,
  photos: () => `<button class="btn primary" data-action="upload">${icon('upload')}<span class="label">Upload photos</span></button>`,
  storage: () => `<button class="btn" data-action="refresh-accounts">${icon('refresh')}<span class="label">Check quotas</span></button>`,
  accounts: () => `<button class="btn primary" data-action="add-account">${icon('plus')}<span class="label">Add account</span></button>`,
  activity: () => `<button class="btn" data-action="verify" ${S.state?.verifying ? 'disabled' : ''}>${icon('shield')}<span class="label">${S.state?.verifying ? 'Verifying…' : 'Verify all copies'}</span></button>`,
  trash: () => (S.state?.summary.trashed ? `<button class="btn danger" data-action="empty-trash">${icon('trash')}<span class="label">Empty trash</span></button>` : ''),
};

function renderHealth() {
  const st = S.state;
  if (!st) return;
  const s = st.summary;
  let cls; let ic; let title; let text;
  if (!st.accounts.length) {
    cls = 'attention'; ic = 'shield-alert'; title = 'No storage connected';
    text = s.files ? `${plural(s.files, 'file')} kept on this computer only.` : 'Add accounts to start mirroring.';
  } else if (s.attention) {
    cls = 'attention'; ic = 'shield-alert'; title = `${plural(s.attention, 'file')} not fully protected`;
    text = 'Open Activity for details.';
  } else if (s.syncing) {
    cls = 'syncing'; ic = 'sync'; title = `Mirroring ${plural(s.syncing, 'file')}`;
    text = `${fmtNum(s.protected)} of ${fmtNum(s.files)} protected`;
  } else {
    cls = 'ok'; ic = 'shield'; title = s.files ? 'Everything protected' : 'Ready';
    text = s.files ? `${plural(s.files, 'file')} · ${fmtBytes(s.bytes)} · ${st.copies} copies each` : 'Upload files to get started.';
  }
  if (st.accounts.length && st.pools.length < st.copies) text += ' Only one provider connected.';
  const pct = s.files ? s.protected / s.files : 1;
  $('#health').className = 'health ' + cls;
  $('#health').innerHTML = `<div class="health-head">${icon(ic)}<span>${esc(title)}</span></div><p>${esc(text)}</p>
    ${s.files ? meter(pct, cls === 'ok' ? 'ok' : cls === 'attention' ? 'warn' : '') : ''}`;
}

/* ============================== shared fragments ============================== */
const emptyState = (ic, title, text, extra = '') => `<div class="empty"><div class="big-icon">${icon(ic)}</div><h3>${esc(title)}</h3><p>${text}</p>${extra}</div>`;
const sectionTitle = (title, hint = '') => `<div class="section-title"><h2>${esc(title)}</h2>${hint ? `<span class="hint">${hint}</span>` : ''}</div>`;
const pip = (f) => `<span class="pip ${f.status}" title="${esc(statusLabel(f))}">${icon(STATUS[f.status].icon)}</span>`;
const badge = (f) => `<span class="badge ${f.status}">${icon(STATUS[f.status].icon)}${esc(statusLabel(f))}</span>`;
const thumbOrIcon = (f) => (f.has_thumb ? `<img src="/api/files/${f.id}/thumb" loading="lazy" alt="">` : icon(kindOf(f)));

function countLabel(d) {
  const parts = [];
  if (d.folders) parts.push(plural(d.folders, 'folder'));
  if (d.files) parts.push(plural(d.files, 'file'));
  return parts.join(' · ') || 'Empty';
}
const folderTile = (d) => `<a class="folder" href="${folderHash(d.path)}">${icon('folder')}
  <div style="min-width:0"><div class="fname">${esc(baseName(d.path))}</div><div class="fmeta">${countLabel(d)}</div></div></a>`;

const fileCard = (f) => `<button class="card" data-file="${f.id}">
  <div class="card-media k-${kindOf(f)}">${thumbOrIcon(f)}${pip(f)}</div>
  <div class="card-body"><div class="card-name" title="${esc(f.name)}">${esc(f.name)}</div>
  <div class="card-meta">${fmtBytes(f.size)} · ${fmtDate(f.modified_at)}</div></div></button>`;

function fileTable(files, { showFolder = false, trash = false } = {}) {
  const rows = files.map((f) => `<tr class="clickable" data-file="${f.id}">
    <td><div class="cell-name">${f.has_thumb ? `<img class="thumb" src="/api/files/${f.id}/thumb" loading="lazy" alt="">` : `<span class="tico">${icon(kindOf(f))}</span>`}<span title="${esc(f.name)}">${esc(f.name)}</span></div></td>
    ${showFolder ? `<td class="muted"><a href="${folderHash(f.folder)}">${esc(f.folder === '/' ? 'Files' : f.folder.slice(1))}</a></td>` : ''}
    <td class="num">${fmtBytes(f.size)}</td>
    <td class="muted">${trash ? fmtAgo(f.deleted_at) : fmtDate(f.modified_at)}</td>
    <td>${trash ? `<button class="btn sm" data-action="restore" data-id="${f.id}">${icon('restore')}Restore</button>` : badge(f)}</td></tr>`).join('');
  return `<div class="table-wrap"><table><thead><tr><th>Name</th>${showFolder ? '<th>Folder</th>' : ''}<th class="num">Size</th>
    <th>${trash ? 'Deleted' : 'Modified'}</th><th>${trash ? '' : 'Protection'}</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

const filesBlock = (files, opts) => (S.layout === 'list' ? fileTable(files, opts) : `<div class="grid">${files.map(fileCard).join('')}</div>`);

function onboarding() {
  return `<div class="onboard">
    <div class="empty" style="padding:24px 0 8px"><div class="big-icon">${icon('logo')}</div>
      <h3>Welcome to Data Store</h3>
      <p>One library for your pictures and documents. Every file is kept on two different cloud providers, so losing one never loses your data.</p>
      <div class="row"><button class="btn primary" data-action="demo">${icon('plus')}Try it with demo accounts</button>
      <a class="btn" href="#/accounts">${icon('cloud')}Connect real accounts</a></div></div>
    <ol>
      <li><div><strong>Connect accounts</strong><p>Add free accounts from at least two providers, for example MEGA and Blomp. Logins stay on this ${IN_APP ? 'phone' : 'computer'}.</p></div></li>
      <li><div><strong>Upload</strong><p>${IN_APP ? 'Tap Upload and pick photos or files.' : 'Drag files or whole folders onto this window.'} Each file goes to one account at each of two providers and is checked after upload.</p></div></li>
      <li><div><strong>Browse in one place</strong><p>Everything appears as one library, whichever account holds it. If a copy goes missing, it is rebuilt from the other one.</p></div></li>
    </ol>
    <div class="note">${icon('info')}<div>Demo accounts are local folders acting as cloud accounts (2 × MEGA 20 GB, 2 × Blomp 40 GB), so you can try everything safely. Remove them later on the Accounts page.</div></div>
  </div>`;
}

/* ============================== views ============================== */
const VIEWS = {
  async files() {
    const data = await api('/list?folder=' + encodeURIComponent(S.route.folder));
    S.items = data.files;
    if (!S.state.accounts.length && S.route.folder === '/' && !data.files.length && !data.folders.length) return onboarding();
    if (!data.folders.length && !data.files.length) {
      return emptyState('folder', 'This folder is empty', 'Drop files or whole folders anywhere on this window, or use Upload.',
        `<div class="row"><button class="btn primary" data-action="upload">${icon('upload')}Upload files</button>
        ${S.route.folder !== '/' ? `<button class="btn" data-action="delete-folder">${icon('trash')}Delete folder</button>` : ''}</div>`);
    }
    let html = '';
    if (data.folders.length) html += sectionTitle('Folders') + `<div class="folders">${data.folders.map(folderTile).join('')}</div>`;
    if (data.files.length) {
      const bytes = data.files.reduce((sum, f) => sum + f.size, 0);
      html += sectionTitle('Files', `${plural(data.files.length, 'item')} · ${fmtBytes(bytes)}`) + filesBlock(data.files);
    }
    return html;
  },

  async search() {
    const { files } = await api('/search?q=' + encodeURIComponent(S.route.q));
    S.items = files;
    if (!files.length) return emptyState('search', 'No matches', `Nothing is named like “${esc(S.route.q)}”.`);
    return sectionTitle('Matches', plural(files.length, 'file')) + filesBlock(files, { showFolder: true });
  },

  async photos() {
    const { files } = await api('/photos');
    S.items = files;
    if (!files.length) {
      return emptyState('image', 'No photos yet', 'Pictures and videos you upload anywhere appear here, newest first.',
        `<button class="btn primary" data-action="upload">${icon('upload')}Upload photos</button>`);
    }
    const groups = [];
    files.forEach((f, index) => {
      const d = new Date(f.modified_at * 1000);
      const key = d.getFullYear() * 100 + d.getMonth();
      if (!groups.length || groups[groups.length - 1].key !== key) {
        groups.push({ key, label: d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' }), items: [] });
      }
      groups[groups.length - 1].items.push({ f, index });
    });
    return groups.map((g) => `<div class="month">${esc(g.label)}<small>${fmtNum(g.items.length)}</small></div>
      <div class="photo-grid">${g.items.map(({ f, index }) => `<button class="photo" data-photo="${index}" title="${esc(f.name)}">${thumbOrIcon(f)}${pip(f)}</button>`).join('')}</div>`).join('');
  },

  async storage() {
    const st = await refreshState();
    const s = st.summary;
    if (!st.accounts.length) {
      return emptyState('database', 'No storage connected', 'Connect accounts to see how much space you have.',
        `<div class="row"><button class="btn primary" data-action="add-account">${icon('plus')}Add account</button><button class="btn" data-action="demo">Use demo accounts</button></div>`);
    }
    const protectedPct = s.files ? Math.round((100 * s.protected) / s.files) : 100;
    const tiles = `<div class="tiles">
      <div class="tile"><div class="label">Your library</div><div class="value">${fmtBytes(s.bytes)}</div><div class="sub">${plural(s.files, 'file')}</div></div>
      <div class="tile"><div class="label">Space left for new files</div><div class="value">${fmtBytes(st.usable_free)}</div><div class="sub">each file is stored ${st.copies}×</div></div>
      <div class="tile"><div class="label">Raw cloud space</div><div class="value">${fmtBytes(st.raw_capacity)}</div><div class="sub">${fmtBytes(st.raw_free)} free across ${plural(st.accounts.length, 'account')}</div></div>
      <div class="tile"><div class="label">Protected</div><div class="value">${protectedPct}%</div><div class="sub">${fmtNum(s.protected)} of ${fmtNum(s.files)} files</div></div>
    </div>`;
    const pools = st.pools.map((p) => {
      const members = st.accounts.filter((a) => a.provider.toLowerCase() === p.provider.toLowerCase());
      const frac = p.capacity ? p.used / p.capacity : 0;
      return `<div class="pool"><div class="pool-head"><h3>${esc(p.provider)}</h3><span>${plural(p.accounts, 'account')}</span></div>
        ${meter(frac)}<div class="nums"><span>${fmtBytes(p.used)} used</span><span>${p.capacity ? fmtBytes(p.free) + ' free' : 'quota unknown'}</span></div>
        <ul>${members.map((a) => {
          const af = a.capacity ? (a.used || 0) / a.capacity : 0;
          return `<li><span>${esc(a.label)}${a.status === 'error' ? ' <span class="badge error">Error</span>' : ''}</span>${meter(af)}<span class="n">${fmtBytes(a.used)} / ${a.capacity ? fmtBytes(a.capacity) : '?'}</span></li>`;
        }).join('')}</ul></div>`;
    }).join('');
    const notes = [];
    if (st.pools.length < st.copies) {
      notes.push(`<div class="note warn">${icon('alert')}<div><strong>Only one provider connected.</strong> Copies go to two accounts at the same provider, which does not protect you if that provider closes or locks you out. Add an account from a second provider.</div></div>`);
    }
    if (st.pools.some((p) => p.unknown)) {
      notes.push(`<div class="note">${icon('info')}<div>Some accounts do not report their quota or could not be reached; they are left out of the totals.</div></div>`);
    }
    notes.push(`<div class="note">${icon('info')}<div>Each file is stored on ${st.copies} different providers, so the space you can fill is limited by how free space is split between providers. With two providers, that is roughly the smaller pool, not the total.</div></div>`);
    return tiles + sectionTitle('Providers', 'Mirrored copies never share a provider') + `<div class="pools">${pools}</div>` + notes.join('');
  },

  async accounts() {
    const [st, rc] = await Promise.all([refreshState(), api('/rclone').catch(() => null)]);
    S.rclone = rc;
    let rcloneBox;
    if (rc && !rc.can_configure) {
      rcloneBox = `<div class="inline-status">${icon('check')}<span class="grow"><strong>rclone is built into this app.</strong> Logins are set up on the PC. Use <em>Export logins</em> there, copy the file to this phone over USB, then import it here.
        ${rc.remotes?.length ? `Imported: ${rc.remotes.map((r) => `<code>${esc(r)}</code>`).join(', ')}.` : ''}</span>
        <button class="btn sm primary" data-action="import-logins">${icon('upload')}Import logins</button></div>`;
    } else if (rc?.path) {
      rcloneBox = `<div class="inline-status">${icon('check')}<span class="grow"><strong>rclone is ready.</strong> Use it to log in to MEGA, Blomp, Google Drive and more. Logins are stored in <code>${esc(rc.config)}</code>.</span>
         <button class="btn sm" data-action="rclone-config">${icon('terminal')}Open rclone setup</button>
         ${rc.remotes?.length ? `<a class="btn sm" href="/api/rclone/export" download title="For the phone app">${icon('download')}Export logins</a>` : ''}</div>`;
    } else {
      rcloneBox = `<div class="inline-status">${icon('info')}<span class="grow"><strong>Cloud accounts need rclone</strong>, the open-source tool that talks to 70+ providers. Download the official ${esc(rc?.version || '')} build; its checksum is verified.</span>
         <button class="btn sm primary" data-action="rclone-download">${icon('download')}Download rclone</button></div>`;
    }
    let table;
    if (!st.accounts.length) {
      table = emptyState('cloud', 'No accounts yet', 'Add at least two providers so every file has an independent copy.',
        `<div class="row"><button class="btn primary" data-action="add-account">${icon('plus')}Add account</button><button class="btn" data-action="demo">Use demo accounts</button></div>`);
    } else {
      const rows = st.accounts.map((a) => {
        const frac = a.capacity ? (a.used || 0) / a.capacity : 0;
        const status = a.status === 'ok' ? '<span class="badge ok">Connected</span>'
          : a.status === 'error' ? `<span class="badge error" title="${esc(a.error)}">Error</span>` : '<span class="badge neutral">Checking</span>';
        return `<tr>
          <td><strong>${esc(a.label)}</strong>${a.status === 'error' ? `<div class="err-line">${esc(a.error)}</div>` : ''}</td>
          <td>${esc(a.provider)}</td>
          <td class="muted">${a.kind === 'rclone' ? 'rclone' : 'Folder'} · <code title="${esc(a.target)}">${esc(a.target)}</code></td>
          <td style="min-width:170px">${meter(frac)}<div class="tiny">${fmtBytes(a.used)} of ${a.capacity ? fmtBytes(a.capacity) : 'unknown'}</div></td>
          <td class="num">${fmtNum(a.stored_files)}</td>
          <td>${status}</td>
          <td class="muted" title="${esc(fmtDateTime(a.last_seen))}">${fmtAgo(a.last_seen)}</td>
          <td><button class="icon-btn sm" data-action="remove-account" data-id="${a.id}" data-name="${esc(a.label)}" data-files="${a.stored_files}" title="Remove account">${icon('trash')}</button></td></tr>`;
      }).join('');
      table = `<div class="table-wrap"><table><thead><tr><th>Account</th><th>Provider</th><th>Connection</th><th>Used</th><th class="num">Files</th><th>Status</th><th>Last seen</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`;
    }
    const help = rc && !rc.can_configure ? '' : `<div class="note">${icon('info')}<div><strong>Connecting a cloud account:</strong> click <em>Open rclone setup</em>, choose <code>n</code> (new remote), give it a name such as <code>mega1</code> and pick the provider (<code>mega</code>, <code>swift</code> for Blomp, <code>drive</code> for Google). Then use <em>Add account</em> here and select that remote.
      For end-to-end encryption, create an rclone <code>crypt</code> remote on top of each account and add the crypt remote instead.</div></div>`;
    return sectionTitle('Connected accounts', st.accounts.length ? plural(st.accounts.length, 'account') : '') + table + sectionTitle('Cloud connector') + rcloneBox + help;
  },

  async activity() {
    const [{ events }, st] = await Promise.all([api('/activity'), refreshState()]);
    const q = st.summary.queue;
    const tiles = `<div class="tiles">
      <div class="tile"><div class="label">Waiting to upload</div><div class="value">${fmtNum(q.pending || 0)}</div><div class="sub">copies queued</div></div>
      <div class="tile"><div class="label">Uploading now</div><div class="value">${fmtNum(q.uploading || 0)}</div><div class="sub">copies in progress</div></div>
      <div class="tile"><div class="label">Retrying</div><div class="value">${fmtNum(q.failed || 0)}</div><div class="sub">automatic, with back-off</div></div>
      <div class="tile"><div class="label">Not fully protected</div><div class="value">${fmtNum(st.summary.attention)}</div><div class="sub">files</div></div></div>`;
    const levelIcon = { ok: 'check', warn: 'alert', error: 'alert', info: 'info' };
    const list = events.length
      ? `<ul class="events">${events.map((e) => `<li class="${esc(e.level)}">${icon(levelIcon[e.level] || 'info')}<span>${esc(e.message)}</span><time title="${esc(fmtDateTime(e.at))}">${fmtAgo(e.at)}</time></li>`).join('')}</ul>`
      : emptyState('activity', 'Nothing yet', 'Uploads, repairs and account checks are logged here.');
    return tiles + sectionTitle('Recent activity', 'Verification re-checks every copy and repairs missing ones') + list;
  },

  async trash() {
    const { files, trash_days: days } = await api('/trash');
    S.items = files;
    if (!files.length) return emptyState('trash', 'Trash is empty', `Deleted files stay here for ${days} days before they are removed from every provider.`);
    return `<p class="lede">Files here are still stored on your providers. They are removed for good after ${days} days, or when you empty the trash.</p>` + fileTable(files, { showFolder: true, trash: true });
  },
};

/* ============================== drawer ============================== */
const drawer = $('#drawer');

function markSelected() {
  $$('[data-file]', $('#view')).forEach((el) => el.classList.toggle('selected', Number(el.dataset.file) === S.selected));
}

async function openDrawer(id) {
  S.selected = id;
  markSelected();
  try {
    const f = await api('/files/' + id);
    if (S.selected !== id) return;
    drawer.innerHTML = drawerHTML(f);
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
  } catch (err) {
    toast(err.message, 'error');
  }
}

function closeDrawer() {
  S.selected = null;
  drawer.classList.remove('open');
  drawer.setAttribute('aria-hidden', 'true');
  markSelected();
}

function drawerHTML(f) {
  const okReplicas = f.replicas.filter((r) => r.state === 'ok');
  const providers = new Set(okReplicas.map((r) => r.provider.toLowerCase())).size;
  let explain;
  if (f.status === 'protected') {
    explain = `Stored on ${plural(okReplicas.length, 'account')} at ${plural(providers, 'provider')}, each copy checked after upload.`;
  } else if (f.status === 'syncing') {
    explain = `${okReplicas.length} of ${f.copies_wanted} copies done. The rest are uploading in the background.`;
  } else if (f.failed_copies) {
    explain = 'An upload failed. It is retried automatically; see the error below.';
  } else {
    explain = 'No account has room for another copy yet. Add storage on the Accounts page.';
  }
  if (f.staged) explain += ' A local copy is kept on this computer until every copy is confirmed.';
  const stateBadge = (r) => ({
    ok: `<span class="badge ok">${icon('check')}Stored</span>`,
    pending: '<span class="badge pending">Waiting</span>',
    uploading: `<span class="badge uploading">${icon('sync')}Uploading</span>`,
    failed: '<span class="badge failed">Retrying</span>',
  }[r.state]);
  const replicas = f.replicas.length ? f.replicas.map((r) => `<li>
      <div class="top"><div><div class="acct">${esc(r.label)}</div><div class="prov">${esc(r.provider)}${r.verified_at && r.state === 'ok' ? ` · checked ${fmtAgo(r.verified_at)}` : ''}</div></div>${stateBadge(r)}</div>
      ${r.error ? `<div class="err">${esc(r.error)}</div>` : ''}
      <div class="key mono">${esc(r.remote_key)}</div></li>`).join('')
    : `<li><div class="prov">No copies assigned yet.</div></li>`;
  const preview = f.has_thumb ? `<img src="/api/files/${f.id}/thumb" alt="" data-action="lightbox-selected" title="Open">` : icon(kindOf(f));
  const content = `/api/files/${f.id}/content`;
  const actions = f.deleted_at
    ? `<button class="btn primary" data-action="restore" data-id="${f.id}">${icon('restore')}Restore</button>`
    : `<a class="btn primary" href="${content}?download=1" download>${icon('download')}Download</a>
       <a class="btn" href="${content}" target="_blank" rel="noopener">${icon('external')}Open</a>
       <button class="btn danger" data-action="trash-file" data-id="${f.id}">${icon('trash')}Delete</button>`;
  return `<div class="drawer-head"><h3 title="${esc(f.name)}">${esc(f.name)}</h3><button class="icon-btn sm" data-action="close-drawer" title="Close (Esc)">${icon('x')}</button></div>
    <div class="drawer-body">
      <div class="drawer-preview">${preview}</div>
      <div class="protect-box ${f.status}"><strong>${icon(STATUS[f.status].icon)}${esc(statusLabel(f))}</strong><p>${esc(explain)}</p></div>
      <div class="h4">Copies</div><ul class="replicas">${replicas}</ul>
      <div class="h4">Details</div>
      <dl class="kv">
        <dt>Folder</dt><dd><a href="${folderHash(f.folder)}">${esc(f.folder === '/' ? 'Files' : f.folder)}</a></dd>
        <dt>Size</dt><dd>${fmtBytes(f.size)} <span class="muted">(${fmtNum(f.size)} bytes)</span></dd>
        <dt>Modified</dt><dd>${fmtDateTime(f.modified_at)}</dd>
        <dt>Added</dt><dd>${fmtDateTime(f.created_at)}</dd>
        ${f.deleted_at ? `<dt>Deleted</dt><dd>${fmtDateTime(f.deleted_at)}</dd>` : ''}
        <dt>Type</dt><dd>${esc(f.mime)}</dd>
        <dt>SHA-256</dt><dd class="mono" title="${esc(f.sha256)}">${esc(f.sha256.slice(0, 20))}…</dd>
      </dl>
    </div>
    <div class="drawer-actions">${actions}</div>`;
}

/* ============================== lightbox ============================== */
function openLightbox(list, index) {
  const media = list.filter(isMedia);
  if (!media.length) return;
  const start = Math.max(0, media.indexOf(list[index]));
  S.lightbox = { list: media, index: start };
  $('#lightbox').hidden = false;
  drawLightbox();
}

function drawLightbox() {
  const { list, index } = S.lightbox;
  const f = list[index];
  const src = `/api/files/${f.id}/content`;
  const stage = $('#lb-stage');
  if (kindOf(f) === 'video') {
    stage.innerHTML = `<video src="${src}" controls autoplay playsinline></video>`;
  } else {
    stage.innerHTML = `<img alt="${esc(f.name)}" src="${f.has_thumb ? `/api/files/${f.id}/thumb` : src}">`;
    if (f.has_thumb) {
      const full = new Image();
      full.onload = () => { if (S.lightbox.list[S.lightbox.index] === f) $('img', stage).src = src; };
      full.src = src;
    }
  }
  $('#lb-caption').innerHTML = `<span>${esc(f.name)}</span><span>·</span><span>${fmtDate(f.modified_at)}</span><span>·</span><span>${index + 1} / ${list.length}</span>
    <a href="${src}?download=1" download>Download</a>`;
  $('.lb-prev').style.visibility = index > 0 ? 'visible' : 'hidden';
  $('.lb-next').style.visibility = index < list.length - 1 ? 'visible' : 'hidden';
}

function stepLightbox(delta) {
  const next = S.lightbox.index + delta;
  if (next < 0 || next >= S.lightbox.list.length) return;
  S.lightbox.index = next;
  drawLightbox();
}

function closeLightbox() {
  $('#lightbox').hidden = true;
  $('#lb-stage').innerHTML = '';
}

$('#lightbox').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-lb]');
  if (btn) {
    if (btn.dataset.lb === 'close') closeLightbox();
    else stepLightbox(btn.dataset.lb === 'next' ? 1 : -1);
  } else if (!e.target.closest('img, video, a')) {
    closeLightbox();
  }
});

/* ============================== modals ============================== */
const modal = $('#modal');

function openModal(html) {
  modal.innerHTML = html;
  modal.returnValue = '';
  if (!modal.open) modal.showModal();
  $$('[data-close]', modal).forEach((b) => b.addEventListener('click', () => modal.close('cancel')));
  return modal;
}

function confirmModal({ title, text, confirm = 'Confirm', danger = false }) {
  return new Promise((resolve) => {
    openModal(`<form method="dialog"><div class="modal-head"><h3>${esc(title)}</h3><p>${text}</p></div>
      <div class="modal-foot"><button type="button" class="btn" data-close>Cancel</button>
      <button class="btn ${danger ? 'danger solid' : 'primary'}" value="ok">${esc(confirm)}</button></div></form>`);
    modal.addEventListener('close', () => resolve(modal.returnValue === 'ok'), { once: true });
  });
}

function promptModal({ title, label, placeholder = '', confirm = 'Create' }) {
  return new Promise((resolve) => {
    openModal(`<form method="dialog"><div class="modal-head"><h3>${esc(title)}</h3></div>
      <div class="modal-body"><label class="field"><span>${esc(label)}</span><input name="value" required placeholder="${esc(placeholder)}" autocomplete="off"></label></div>
      <div class="modal-foot"><button type="button" class="btn" data-close>Cancel</button><button class="btn primary" value="ok">${esc(confirm)}</button></div></form>`);
    const input = $('input', modal);
    input.focus();
    modal.addEventListener('close', () => resolve(modal.returnValue === 'ok' ? input.value.trim() : null), { once: true });
  });
}

async function openAddAccount() {
  const rc = S.rclone || await api('/rclone').catch(() => ({ remotes: [] }));
  S.rclone = rc;
  const remotes = rc.remotes || [];
  const count = S.state?.accounts.length || 0;
  let remoteField;
  if (!rc.can_configure && !remotes.length) {
    remoteField = `<div class="inline-status">${icon('info')}<span class="grow">No logins on this phone yet. Export them on the PC and import the file here.</span>
      <button type="button" class="btn sm primary" data-action="import-logins">Import logins</button></div>`;
  } else if (!rc.path) {
    remoteField = `<div class="inline-status">${icon('info')}<span class="grow">rclone is not installed yet.</span><button type="button" class="btn sm primary" data-action="rclone-download">Download rclone</button></div>`;
  } else if (!remotes.length) {
    remoteField = `<div class="inline-status">${icon('info')}<span class="grow">No logins set up yet. Open rclone setup, create a remote, then refresh.</span>
      <button type="button" class="btn sm" data-action="rclone-config">Open setup</button><button type="button" class="btn sm" data-action="reopen-add">Refresh</button></div>`;
  } else {
    const more = rc.can_configure
      ? `<button type="button" class="link-btn" data-action="rclone-config">Open rclone setup</button> · <button type="button" class="link-btn" data-action="reopen-add">Refresh list</button>`
      : `<button type="button" class="link-btn" data-action="import-logins">Import logins again</button>`;
    remoteField = `<label class="field"><span>rclone remote</span><select name="remote">${remotes.map((r) => `<option>${esc(r)}</option>`).join('')}</select>
      <small>Missing one? ${more}</small></label>`;
  }
  openModal(`<form id="acct-form" novalidate>
    <div class="modal-head"><h3>Add a storage account</h3><p>Accounts with the same provider form one pool. Each file is copied to two different pools.</p></div>
    <div class="modal-body">
      <div class="choice">
        <label><input type="radio" name="kind" value="rclone" ${rc.path ? 'checked' : ''}><span><strong>Cloud account</strong><small>MEGA, Blomp, Google Drive… via rclone</small></span></label>
        <label><input type="radio" name="kind" value="local" ${rc.path ? '' : 'checked'}><span><strong>Local folder</strong><small>External drive, NAS share or testing</small></span></label>
      </div>
      <div class="field-row">
        <label class="field"><span>Provider</span><input name="provider" list="provider-list" placeholder="MEGA" autocomplete="off"></label>
        <label class="field"><span>Name</span><input name="label" placeholder="MEGA 1" autocomplete="off"></label>
      </div>
      <div data-kind="rclone">${remoteField}</div>
      <div data-kind="local" class="field-row">
        <label class="field"><span>Folder path</span><input name="path" placeholder="D:\\Backup\\DataStore" autocomplete="off"></label>
        <label class="field"><span>Size limit (GB)</span><input name="capacity_gb" type="number" min="1" step="1" placeholder="Optional"></label>
      </div>
      <div class="form-error" id="acct-error"></div>
    </div>
    <div class="modal-foot"><button type="button" class="btn" data-close>Cancel</button><button class="btn primary" type="submit" id="acct-submit">Connect</button></div>
    <datalist id="provider-list"><option>MEGA</option><option>Blomp</option><option>Google Drive</option><option>OneDrive</option><option>pCloud</option><option>Dropbox</option><option>External drive</option></datalist>
  </form>`);
  const form = $('#acct-form');
  const syncKind = () => {
    const kind = form.kind.value;
    $$('[data-kind]', form).forEach((el) => { el.hidden = el.dataset.kind !== kind; });
  };
  form.addEventListener('change', syncKind);
  syncKind();
  form.provider.addEventListener('input', () => {
    if (!form.label.dataset.touched) form.label.value = form.provider.value ? `${form.provider.value} ${count + 1}` : '';
  });
  form.label.addEventListener('input', () => { form.label.dataset.touched = '1'; });
  form.provider.focus();
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const kind = form.kind.value;
    const body = {
      kind,
      provider: form.provider.value.trim(),
      label: form.label.value.trim(),
      target: kind === 'rclone' ? (form.remote?.value || '') : form.path.value.trim(),
      capacity_gb: kind === 'local' ? form.capacity_gb.value : undefined,
    };
    const error = $('#acct-error');
    if (!body.provider || !body.label || !body.target) {
      error.textContent = 'Fill in provider, name and ' + (kind === 'rclone' ? 'an rclone remote.' : 'a folder path.');
      return;
    }
    const submit = $('#acct-submit');
    submit.disabled = true;
    submit.textContent = 'Connecting…';
    error.textContent = '';
    try {
      await api('/accounts', { method: 'POST', body });
      modal.close();
      toast(`Connected ${body.label}`);
      await refreshState();
      render({ quiet: true });
    } catch (err) {
      error.textContent = err.message;
      submit.disabled = false;
      submit.textContent = 'Connect';
    }
  });
}

/* ============================== uploads ============================== */
const U = { items: [], active: 0, max: 3, seq: 0 };
const JUNK = new Set(['thumbs.db', 'desktop.ini', '.ds_store']);

function enqueue(entries) {
  entries = entries.filter(({ file }) => !JUNK.has(file.name.toLowerCase()));
  if (!entries.length) return;
  if (!S.state?.accounts.length) toast('No storage accounts yet. Files stay on this computer until you add some.');
  for (const { file, folder } of entries) U.items.push({ id: ++U.seq, file, folder, loaded: 0, state: 'queued' });
  $('#transfers').hidden = false;
  $('#transfers').classList.remove('collapsed');
  pump();
}

function pump() {
  while (U.active < U.max) {
    const item = U.items.find((i) => i.state === 'queued');
    if (!item) break;
    startUpload(item);
  }
  drawTransfers();
}

function startUpload(item) {
  item.state = 'uploading';
  U.active++;
  const xhr = new XMLHttpRequest();
  const qs = new URLSearchParams({ folder: item.folder, name: item.file.name, mtime: String(Math.floor((item.file.lastModified || Date.now()) / 1000)) });
  xhr.open('PUT', '/api/upload?' + qs);
  xhr.upload.onprogress = (e) => { item.loaded = e.loaded; scheduleDraw(); };
  xhr.onload = () => {
    let result = null;
    try { result = JSON.parse(xhr.responseText); } catch { /* not json */ }
    if (xhr.status === 401) sessionExpired();
    finishUpload(item, xhr.status < 300 ? null : result?.error || `HTTP ${xhr.status}`, result);
  };
  xhr.onerror = () => finishUpload(item, 'Connection to Data Store lost');
  xhr.send(item.file);
}

function finishUpload(item, error, result) {
  U.active--;
  item.state = error ? 'error' : result?.duplicate ? 'duplicate' : 'done';
  item.error = error;
  item.loaded = item.file.size;
  pump();
  refreshSoon();
}

let drawPending = false;
function scheduleDraw() {
  if (drawPending) return;
  drawPending = true;
  requestAnimationFrame(() => { drawPending = false; drawTransfers(); });
}

function drawTransfers() {
  const total = U.items.length;
  const finished = U.items.filter((i) => ['done', 'duplicate', 'error'].includes(i.state)).length;
  const failed = U.items.filter((i) => i.state === 'error').length;
  $('#transfers-title').textContent = finished < total ? `Uploading ${fmtNum(finished + 1)} of ${fmtNum(total)}`
    : `${plural(total - failed, 'file')} added${failed ? `, ${failed} failed` : ''}`;
  const order = { uploading: 0, queued: 1, error: 2, done: 3, duplicate: 3 };
  const visible = [...U.items].sort((a, b) => order[a.state] - order[b.state] || a.id - b.id).slice(0, 150);
  $('#transfers-list').innerHTML = visible.map((i) => {
    const pct = i.file.size ? i.loaded / i.file.size : 1;
    const label = {
      queued: 'Waiting',
      uploading: `${Math.round(pct * 100)}%`,
      done: 'Added · mirroring',
      duplicate: 'Already stored',
      error: esc(i.error),
    }[i.state];
    const cls = i.state === 'error' ? 'error' : ['done', 'duplicate'].includes(i.state) ? 'done' : '';
    return `<li><div class="t-row"><span class="t-name" title="${esc(joinPath(i.folder, i.file.name))}">${esc(i.file.name)}</span><span class="t-state ${cls}">${label}</span></div>
      ${i.state === 'uploading' ? meter(pct, '') : ''}</li>`;
  }).join('');
}

$('#transfers-clear').addEventListener('click', () => {
  U.items = U.items.filter((i) => ['queued', 'uploading'].includes(i.state));
  if (!U.items.length) $('#transfers').hidden = true;
  else drawTransfers();
});
$('#transfers-toggle').addEventListener('click', () => $('#transfers').classList.toggle('collapsed'));
window.addEventListener('beforeunload', (e) => {
  if (U.items.some((i) => ['queued', 'uploading'].includes(i.state))) e.preventDefault();
});

const uploadTarget = () => (S.route.view === 'files' ? S.route.folder : S.route.view === 'photos' ? '/Photos' : '/');

$('#file-input').addEventListener('change', (e) => {
  const target = uploadTarget();
  enqueue([...e.target.files].map((file) => ({ file, folder: target })));
  e.target.value = '';
});
$('#folder-input').addEventListener('change', (e) => {
  const target = uploadTarget();
  enqueue([...e.target.files].map((file) => {
    const parts = file.webkitRelativePath.split('/').slice(0, -1);
    return { file, folder: parts.reduce(joinPath, target) };
  }));
  e.target.value = '';
});

$('#conf-input').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;
  try {
    const res = await fetch('/api/rclone/import', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'text/plain' }, body: await file.text() });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    toast(`Imported logins: ${data.remotes.join(', ')}. You can delete the file you copied now.`);
    S.rclone = null;
    if (modal.open) openAddAccount(); else render({ quiet: true });
  } catch (err) {
    toast(err.message, 'error');
  }
});

/* drag & drop, including whole folders */
let dragDepth = 0;
const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes('Files');
function showDrop(on) {
  $('#dropzone').classList.toggle('on', on);
  if (on) $('#dropzone-text').textContent = `Drop to upload to “${baseName(uploadTarget())}”`;
}
window.addEventListener('dragenter', (e) => { if (!hasFiles(e)) return; e.preventDefault(); dragDepth++; showDrop(true); });
window.addEventListener('dragover', (e) => { if (!hasFiles(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
window.addEventListener('dragleave', (e) => { if (!hasFiles(e)) return; dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) showDrop(false); });
window.addEventListener('drop', async (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault();
  dragDepth = 0;
  showDrop(false);
  try {
    enqueue(await collectDrop(e.dataTransfer, uploadTarget()));
  } catch (err) {
    toast('Could not read dropped files: ' + err.message, 'error');
  }
});

function collectDrop(dataTransfer, baseFolder) {
  // Entries must be grabbed synchronously, before the drop event ends.
  const entries = [...dataTransfer.items].map((i) => i.webkitGetAsEntry?.()).filter(Boolean);
  const plainFiles = [...dataTransfer.files];
  return (async () => {
    if (!entries.length) return plainFiles.map((file) => ({ file, folder: baseFolder }));
    const out = [];
    const walk = async (entry, folder) => {
      if (entry.isFile) {
        out.push({ file: await new Promise((res, rej) => entry.file(res, rej)), folder });
      } else if (entry.isDirectory) {
        const reader = entry.createReader();
        const sub = joinPath(folder, entry.name);
        let batch;
        do {
          batch = await new Promise((res, rej) => reader.readEntries(res, rej));
          for (const child of batch) await walk(child, sub);
        } while (batch.length);
      }
    };
    for (const entry of entries) await walk(entry, baseFolder);
    return out;
  })();
}

/* ============================== actions ============================== */
async function withButton(el, busyText, fn) {
  const original = el?.innerHTML;
  if (el) { el.disabled = true; if (busyText) el.textContent = busyText; }
  try { return await fn(); } finally { if (el && el.isConnected) { el.disabled = false; el.innerHTML = original; } }
}

const ACTION_HANDLERS = {
  upload: () => $('#file-input').click(),
  'upload-folder': () => $('#folder-input').click(),
  rerender: () => render(),
  layout: (el) => { S.layout = el.dataset.value; writePref('layout', S.layout); render({ quiet: true }); },
  'close-drawer': closeDrawer,

  async 'new-folder'() {
    const name = await promptModal({ title: 'New folder', label: 'Folder name', placeholder: 'e.g. Holidays 2026' });
    if (!name) return;
    const { path } = await api('/folders', { method: 'POST', body: { path: joinPath(S.route.folder, name) } });
    location.hash = folderHash(path);
  },
  async 'delete-folder'() {
    await api('/folders?path=' + encodeURIComponent(S.route.folder), { method: 'DELETE' });
    location.hash = folderHash(parentOf(S.route.folder));
  },
  async demo(el) {
    await withButton(el, 'Setting up…', () => api('/demo', { method: 'POST' }));
    toast('Demo accounts ready. Drop some files in to try it.');
    await refreshState();
    if (S.route.view !== 'files') location.hash = '#/files'; else render({ quiet: true });
  },
  'add-account': () => openAddAccount(),
  'reopen-add': () => { S.rclone = null; openAddAccount(); },
  async 'remove-account'(el) {
    const files = Number(el.dataset.files);
    const ok = await confirmModal({
      title: `Remove ${el.dataset.name}?`,
      text: `Data Store stops using this account. ${files ? `Its ${plural(files, 'copy')} will be re-created on your other accounts from the remaining copies.` : ''} Nothing is deleted from the account itself.`,
      confirm: 'Remove account',
      danger: true,
    });
    if (!ok) return;
    await api('/accounts/' + el.dataset.id, { method: 'DELETE' });
    toast('Account removed');
    await refreshState();
    render({ quiet: true });
  },
  async 'refresh-accounts'(el) {
    await withButton(el, 'Checking…', () => api('/accounts/refresh', { method: 'POST' }));
    toast('Quotas updated');
    await refreshState();
    render({ quiet: true });
  },
  async 'rclone-download'(el) {
    await withButton(el, 'Downloading…', () => api('/rclone/download', { method: 'POST' }));
    toast('rclone installed and verified');
    S.rclone = null;
    if (modal.open) openAddAccount(); else render({ quiet: true });
  },
  'import-logins': () => $('#conf-input').click(),
  async 'rclone-config'() {
    await api('/rclone/configure', { method: 'POST' });
    toast('rclone setup opened in a new window. Come back here when you are done.');
  },
  async verify(el) {
    await withButton(el, 'Starting…', () => api('/verify', { method: 'POST' }));
    toast('Verification started. Results appear in Activity.');
    await refreshState();
    render({ quiet: true });
  },
  async 'empty-trash'() {
    const n = S.state.summary.trashed;
    const ok = await confirmModal({
      title: 'Empty trash?',
      text: `${plural(n, 'file')} will be deleted permanently from every provider. This cannot be undone.`,
      confirm: 'Delete forever',
      danger: true,
    });
    if (!ok) return;
    await api('/trash/empty', { method: 'POST' });
    toast('Deleting from providers…');
  },
  async restore(el) {
    const f = await api(`/files/${el.dataset.id}/restore`, { method: 'POST' });
    toast(`Restored to ${f.folder === '/' ? 'Files' : f.folder}`);
    if (S.selected === f.id) closeDrawer();
    await refreshState();
    render({ quiet: true });
  },
  async 'trash-file'(el) {
    await api('/files/' + el.dataset.id, { method: 'DELETE' });
    closeDrawer();
    toast('Moved to trash');
    await refreshState();
    render({ quiet: true });
  },
  'lightbox-selected'() {
    const index = S.items.findIndex((f) => f.id === S.selected);
    if (index >= 0) openLightbox(S.items, index);
  },
};

document.addEventListener('click', async (e) => {
  const actionEl = e.target.closest('[data-action]');
  if (actionEl) {
    e.preventDefault();
    try {
      await ACTION_HANDLERS[actionEl.dataset.action]?.(actionEl);
    } catch (err) {
      toast(err.message, 'error');
    }
    return;
  }
  const fileEl = e.target.closest('[data-file]');
  if (fileEl && !e.target.closest('a')) {
    openDrawer(Number(fileEl.dataset.file));
    return;
  }
  const photoEl = e.target.closest('[data-photo]');
  if (photoEl) openLightbox(S.items, Number(photoEl.dataset.photo));
});

document.addEventListener('dblclick', (e) => {
  const fileEl = e.target.closest('[data-file]');
  if (!fileEl) return;
  const index = S.items.findIndex((f) => f.id === Number(fileEl.dataset.file));
  if (index >= 0 && isMedia(S.items[index])) openLightbox(S.items, index);
});

document.addEventListener('keydown', (e) => {
  if (!$('#lightbox').hidden) {
    if (e.key === 'Escape') closeLightbox();
    if (e.key === 'ArrowRight') stepLightbox(1);
    if (e.key === 'ArrowLeft') stepLightbox(-1);
    return;
  }
  if (modal.open) return;
  if (e.key === 'Escape' && S.selected) closeDrawer();
  if (e.key === '/' && document.activeElement?.tagName !== 'INPUT') { e.preventDefault(); $('#search').focus(); }
});

$('#search-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const q = $('#search').value.trim();
  if (q) location.hash = '#/search/' + encodeURIComponent(q);
});

$('#menu-btn').addEventListener('click', () => $('#sidebar').classList.toggle('open'));

/* ============================== live updates ============================== */
let refreshTimer = null;
function refreshSoon() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(async () => {
    try { await refreshState(); render({ quiet: true }); } catch { /* next poll retries */ }
  }, 450);
}

async function refreshDrawer() {
  if (!S.selected) return;
  try {
    const f = await api('/files/' + S.selected);
    const scroll = $('.drawer-body', drawer)?.scrollTop || 0;
    drawer.innerHTML = drawerHTML(f);
    $('.drawer-body', drawer).scrollTop = scroll;
  } catch {
    closeDrawer();
  }
}

async function poll() {
  try {
    const previous = S.state?.revision;
    await refreshState();
    if (previous !== undefined && S.state.revision !== previous && !modal.open) {
      await render({ quiet: true });
      refreshDrawer();
    }
  } catch { /* server restarting; keep polling */ }
  setTimeout(poll, document.hidden ? 15000 : 2500);
}

async function boot() {
  try {
    await refreshState();
  } catch {
    $('#view').innerHTML = emptyState('alert', 'Cannot reach Data Store', 'Is the app still running? Start DataStore again, then reload this page.');
    return;
  }
  window.addEventListener('hashchange', () => {
    $('#sidebar').classList.remove('open');
    if (S.selected) closeDrawer();
    render();
  });
  await render();
  setTimeout(poll, 2500);
}

boot();
