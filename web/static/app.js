// ── AUTH ─────────────────────────────────────────────────────────────────────
var authToken = localStorage.getItem('brain_token');

function authHeaders() {
  return {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ' + authToken
  };
}

async function doLogin() {
  var pw  = document.getElementById('pw-input').value;
  var err = document.getElementById('login-err');
  var btn = document.getElementById('login-btn');
  err.style.display = 'none';
  btn.disabled = true;
  btn.textContent = '...';
  try {
    var res = await fetch('/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pw })
    });
    if (!res.ok) {
      err.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'Entrar';
      return;
    }
    var data = await res.json();
    authToken = data.token;
    localStorage.setItem('brain_token', authToken);
    showApp();
  } catch(e) {
    err.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Entrar';
  }
}

async function doLogout() {
  try {
    await fetch('/logout', { method: 'POST', headers: authHeaders() });
  } catch(e) {}
  authToken = null;
  localStorage.removeItem('brain_token');
  document.getElementById('app').classList.remove('visible');
  document.getElementById('login-screen').classList.add('visible');
  document.getElementById('pw-input').value = '';
  document.getElementById('login-btn').disabled = false;
  document.getElementById('login-btn').textContent = 'Entrar';
}

async function checkAuth() {
  if (!authToken) { showLogin(); return; }
  try {
    var res = await fetch('/auth/google/status', { headers: authHeaders() });
    if (res.status === 401) {
      localStorage.removeItem('brain_token');
      authToken = null;
      showLogin();
      return;
    }
  } catch(e) {
    showLogin();
    return;
  }
  showApp();
}

function showLogin() {
  document.getElementById('login-screen').classList.add('visible');
  document.getElementById('app').classList.remove('visible');
  setTimeout(function(){ document.getElementById('pw-input').focus(); }, 50);
}

function showApp() {
  document.getElementById('login-screen').classList.remove('visible');
  document.getElementById('app').classList.add('visible');
  initApp();
}

// ── APP INIT ─────────────────────────────────────────────────────────────────
var notes = [];
var selected = {};
var currentFilter = 'all';

function initApp() {
  try { notes = JSON.parse(localStorage.getItem('sf_notes') || '[]'); } catch(e) { notes = []; }
  syncFromNotion(true);
  // Escuchar postMessage de OAuth popup
  window.addEventListener('message', function(e) {
    if (e.data === 'google_connected') {
      checkGoogleStatus();
    }
  });
}

// ── NOTION SYNC ───────────────────────────────────────────────────────────────
async function syncFromNotion(silent) {
  var btn      = document.getElementById('sync-btn');
  var statusEl = document.getElementById('sync-status');
  if (btn) { btn.textContent = '⟳ ...'; btn.disabled = true; }
  if (!silent && statusEl) { statusEl.style.display = 'block'; statusEl.textContent = 'Sincronizando con Notion...'; }
  try {
    var res = await fetch('/notes', { method: 'GET', headers: authHeaders() });
    if (res.status === 401) { doLogout(); return; }
    var data = await res.json();
    if (data.error) throw new Error(data.error);

    var localMap = {};
    notes.forEach(function(n) {
      if (n.page_id) localMap[n.page_id] = n;
      else if (n.url) {
        var id = n.url.split('-').pop().replace(/\//g,'');
        localMap[id] = n;
      }
    });

    notes = data.notes.map(function(n) {
      var local = localMap[n.page_id] || localMap[n.page_id.replace(/-/g,'')] || {};
      return Object.assign({}, n, {
        pinned:  local.pinned  || false,
        content: local.content || ''
      });
    });

    try { localStorage.setItem('sf_notes', JSON.stringify(notes.slice(0, 100))); } catch(e) {}

    var histActive  = document.getElementById('view-history').classList.contains('active');
    var statsActive = document.getElementById('view-stats').classList.contains('active');
    var chatActive  = document.getElementById('view-chat').classList.contains('active');
    if (histActive)  renderHistory();
    if (statsActive) { renderStats(); renderReminders(); }
    if (chatActive)  renderCtx();

    var tbSub = document.getElementById('tb-sub');
    if (tbSub && document.getElementById('view-history').classList.contains('active')) {
      tbSub.textContent = notes.length + ' notas procesadas';
    }

    if (!silent && statusEl) {
      statusEl.textContent = '✓ ' + notes.length + ' notas sincronizadas desde Notion';
      statusEl.style.color = 'var(--green)';
      setTimeout(function(){ statusEl.style.display = 'none'; statusEl.style.color = 'var(--text3)'; }, 3000);
    }
  } catch(e) {
    if (!silent && statusEl) {
      statusEl.style.display = 'block';
      statusEl.textContent = '✗ Error al sincronizar: ' + e.message;
      statusEl.style.color = 'var(--red)';
      setTimeout(function(){ statusEl.style.display = 'none'; statusEl.style.color = 'var(--text3)'; }, 5000);
    }
  }
  if (btn) { btn.textContent = '⟳ Sync'; btn.disabled = false; }
}

// ── VIEWS ────────────────────────────────────────────────────────────────────
function showView(name, sidebarEl, bnavId) {
  document.querySelectorAll('.view').forEach(function(v){ v.classList.remove('active'); });
  document.querySelectorAll('.nav-item').forEach(function(n){ n.classList.remove('active'); });
  document.querySelectorAll('.bnav-item').forEach(function(n){ n.classList.remove('active'); });
  document.getElementById('view-' + name).classList.add('active');

  if (sidebarEl) sidebarEl.classList.add('active');
  var sidebarMap = { new:'btn-new', history:'btn-history', stats:'btn-stats', chat:'btn-chat', inbox:'btn-inbox' };
  var sBtn = document.getElementById(sidebarMap[name]);
  if (sBtn) sBtn.classList.add('active');

  if (bnavId) document.getElementById(bnavId).classList.add('active');
  var bnavMap = { new:'bnav-new', history:'bnav-history', stats:'bnav-stats', chat:'bnav-chat', inbox:'bnav-inbox' };
  var bBtn = document.getElementById(bnavMap[name]);
  if (bBtn) bBtn.classList.add('active');

  var titles = {
    'new':     ['Nueva nota',       'Escribe y procesa a Notion'],
    'history': ['Historial',        notes.length + ' notas procesadas'],
    'stats':   ['Stats',            'Resumen de tu knowledge base'],
    'chat':    ['Chat con notas',   'Pregunta sobre tu conocimiento'],
    'inbox':   ['Inbox',            'Gmail + Calendar'],
  };
  document.getElementById('tb-title').textContent = titles[name][0];
  document.getElementById('tb-sub').textContent   = titles[name][1];
  document.getElementById('process-btn').style.display = name === 'new' ? '' : 'none';

  var clearBtn = document.getElementById('clear-btn');
  if (clearBtn) {
    if (name === 'new') {
      var t = (document.getElementById('note-title').value||'').length;
      var b = (document.getElementById('note-body').value||'').length;
      clearBtn.style.display = (t + b > 0) ? '' : 'none';
    } else {
      clearBtn.style.display = 'none';
    }
  }

  if (name === 'history') renderHistory();
  if (name === 'stats')   { renderStats(); renderReminders(); }
  if (name === 'chat')    renderCtx();
  if (name === 'inbox')   initInboxView();
}

function setFilter(f, el) {
  currentFilter = f;
  document.querySelectorAll('.filter-btn').forEach(function(b){ b.classList.remove('on'); });
  if (el) el.classList.add('on');
  renderHistory();
}

function updateCount() {
  var t = document.getElementById('note-title').value.length;
  var b = document.getElementById('note-body').value.length;
  document.getElementById('char-count').textContent = t + b;
  var clearBtn = document.getElementById('clear-btn');
  if (clearBtn) clearBtn.style.display = (t + b > 0) ? '' : 'none';
}

function clearNote() {
  if (!confirm('¿Descartar el contenido actual y empezar una nueva nota?')) return;
  document.getElementById('note-title').value = '';
  document.getElementById('note-body').value  = '';
  document.getElementById('char-count').textContent = '0';
  document.getElementById('clear-btn').style.display = 'none';
  setStatus('idle', 'Esperando nota...');
  document.getElementById('result-info').style.display = 'none';
  document.getElementById('res-summary').textContent = 'El resumen aparecerá aquí.';
  document.getElementById('note-title').focus();
}

// ── PROCESS ──────────────────────────────────────────────────────────────────
async function processNote() {
  var title = document.getElementById('note-title').value.trim();
  var body  = document.getElementById('note-body').value.trim();
  if (!title && !body) return;
  var content = title ? ('# ' + title + '\n\n' + body) : body;
  var btn = document.getElementById('process-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spin"></span>';
  setStatus('processing', '⏳ Procesando con Gemini...');
  document.getElementById('result-info').style.display = 'none';
  try {
    var res = await fetch('/process', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ content: content })
    });
    if (res.status === 401) { doLogout(); return; }
    if (res.status === 429) { setStatus('error', '⏳ Demasiadas solicitudes. Espera un momento.'); btn.disabled = false; btn.textContent = '⚡ Procesar'; return; }
    var data = await res.json();
    setStatus('success', '✓ Guardado en Notion');
    document.getElementById('result-info').style.display = 'flex';
    document.getElementById('res-title').textContent   = data.title   || '—';
    document.getElementById('res-type').textContent    = data.type    || '—';
    document.getElementById('res-summary').textContent = data.summary || '—';
    document.getElementById('res-link').href           = data.url     || '#';
    var tagsEl = document.getElementById('res-tags');
    tagsEl.innerHTML = '';
    (data.tags || []).forEach(function(t) {
      var s = document.createElement('span');
      s.className = 'tag'; s.textContent = t;
      tagsEl.appendChild(s);
    });
    data.content = content;
    data.date    = new Date().toISOString();
    notes.unshift(data);
    try { localStorage.setItem('sf_notes', JSON.stringify(notes.slice(0,50))); } catch(e){}
  } catch(e) {
    setStatus('error', '✗ ' + e.message);
  }
  btn.disabled = false;
  btn.textContent = '⚡ Procesar';
}

function setStatus(type, msg) {
  var box = document.getElementById('status-box');
  box.className = 'status-box ' + type;
  box.textContent = msg;
}

// ── HISTORY ──────────────────────────────────────────────────────────────────
function renderHistory() {
  var c = document.getElementById('history-container');
  var q = (document.getElementById('search-input') ? document.getElementById('search-input').value : '').toLowerCase();
  var filtered = notes.filter(function(n) {
    var matchSearch = !q || (n.title||'').toLowerCase().includes(q) ||
                     (n.summary||'').toLowerCase().includes(q) ||
                     (n.tags||[]).join(' ').toLowerCase().includes(q);
    var matchFilter = currentFilter === 'all' ||
                     (currentFilter === 'pinned' && n.pinned) ||
                      n.type === currentFilter;
    return matchSearch && matchFilter;
  });
  if (!filtered.length) {
    c.innerHTML = '<div class="empty"><div class="empty-icon">◎</div><div class="empty-text">' +
      (q ? 'Sin resultados para "'+esc(q)+'"' : 'Aún no hay notas procesadas') + '</div></div>';
    return;
  }
  filtered.sort(function(a,b){ return (b.pinned?1:0)-(a.pinned?1:0); });
  var html = '<div class="history-grid' + (bulkMode ? ' selecting-mode' : '') + '">';
  filtered.forEach(function(n) {
    var realIdx = notes.indexOf(n);
    var tags    = (n.tags||[]).slice(0,3).map(function(t){ return '<span class="card-tag">'+esc(t)+'</span>'; }).join('');
    var pinIcon = n.pinned ? '📌' : '○';
    var dateStr = n.date ? new Date(n.date).toLocaleDateString('es-PE', {day:'2-digit',month:'short',year:'numeric'}) : '';
    var isBulkSel = bulkMode && bulkSelected[n.page_id];
    var today = new Date().toISOString().slice(0,10);
    var rdClass = '';
    var reminderBadge = '';
    if (n.reminder_date) {
      var rd = n.reminder_date.slice(0,10);
      if (rd < today) { rdClass = ' has-reminder overdue'; reminderBadge = '<span class="reminder-badge overdue">🔔 '+rd+'</span>'; }
      else if (rd === today) { rdClass = ' has-reminder today'; reminderBadge = '<span class="reminder-badge today">🔔 Hoy</span>'; }
      else { rdClass = ' has-reminder'; reminderBadge = '<span class="reminder-badge">🔔 '+rd+'</span>'; }
    }
    var cardClick = bulkMode
      ? 'onclick="toggleBulkCard(event,\''+n.page_id+'\')"'
      : 'onclick="window.open(\''+n.url+'\',\'_blank\')"';
    html += '<div class="note-card'+(n.pinned?' pinned':'')+(isBulkSel?' bulk-selected':'')+rdClass+'" '+cardClick+'>' +
      '<div class="card-header">' +
        '<div style="display:flex;align-items:flex-start;gap:8px;flex:1;min-width:0">' +
          '<div class="card-checkbox">'+(isBulkSel?'<svg width="9" height="9" viewBox="0 0 9 9"><path d="M1.5 4.5l2 2L7.5 2" stroke="#0a0a0a" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>':'')+'</div>' +
          '<div class="card-title">'+esc(n.title)+'</div>' +
        '</div>' +
        '<div style="display:flex;align-items:center;gap:6px;flex-shrink:0">' +
          '<span class="card-badge">'+esc(n.type)+'</span>' +
          (bulkMode ? '' :
            '<button class="card-reminder" onclick="openReminderModal(event,'+realIdx+')" title="Recordatorio">🔔</button>' +
            '<button class="card-pin" onclick="pinNote(event,'+realIdx+')" title="Pin">'+pinIcon+'</button>' +
            '<button class="card-reprocess" onclick="openEditModal(event,'+realIdx+')" title="Editar">✎</button>' +
            '<button class="card-delete" onclick="deleteNote(event,'+realIdx+')" title="Eliminar">×</button>'
          ) +
        '</div></div>' +
      (reminderBadge ? '<div style="margin-bottom:6px">'+reminderBadge+'</div>' : '') +
      (dateStr ? '<div class="card-date">'+dateStr+'</div>' : '') +
      '<div class="card-summary">'+esc(n.summary||'')+'</div>' +
      '<div class="card-footer"><div class="card-tags">'+tags+'</div>' +
      (bulkMode ? '' : '<a href="'+n.url+'" target="_blank" class="card-ext-link" onclick="event.stopPropagation()">Notion →</a>') +
      '</div>' +
      '</div>';
  });
  html += '</div>';
  c.innerHTML = html;
}

function pinNote(e, i) {
  e.stopPropagation();
  notes[i].pinned = !notes[i].pinned;
  try { localStorage.setItem('sf_notes', JSON.stringify(notes)); } catch(e){}
  renderHistory();
}

async function reprocessNote(e, i) {
  e.stopPropagation();
  var n = notes[i];
  if (!n.content) { alert('No hay contenido guardado para re-procesar.'); return; }
  if (!confirm('¿Re-procesar "'+n.title+'" con Gemini?')) return;
  try {
    var res = await fetch('/reprocess', {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ content: n.content })
    });
    if (res.status === 401) { doLogout(); return; }
    var data = await res.json();
    if (data.error) throw new Error(data.error);
    data.content = n.content;
    data.date    = new Date().toISOString();
    data.pinned  = n.pinned;
    notes[i]     = data;
    try { localStorage.setItem('sf_notes', JSON.stringify(notes)); } catch(e){}
    renderHistory();
    alert('✓ Re-procesado: ' + data.title);
  } catch(err) {
    alert('Error: ' + err.message);
  }
}

// ── DELETE ────────────────────────────────────────────────────────────────────
var _pendingDelete = null;

function deleteNote(e, i) {
  e.stopPropagation();
  _pendingDelete = i;
  showDeleteModal(notes[i].title);
}

function showDeleteModal(title) {
  document.getElementById('edit-title').value = '';
  document.getElementById('edit-body').value  = '';
  var st = document.getElementById('edit-status');
  st.style.display    = 'block';
  st.style.background = 'rgba(248,113,113,0.07)';
  st.style.border     = '1px solid rgba(248,113,113,0.2)';
  st.style.color      = 'var(--red)';
  st.textContent      = '¿Eliminar "' + title + '"?';
  var saveBtn = document.getElementById('edit-save-btn');
  saveBtn.textContent = '🗑 Solo del historial';
  saveBtn.onclick     = confirmDeleteLocal;
  var notionBtn = document.getElementById('delete-notion-btn');
  if (!notionBtn) {
    notionBtn = document.createElement('button');
    notionBtn.id        = 'delete-notion-btn';
    notionBtn.className = 'btn btn-danger';
    notionBtn.textContent = '🗑 Historial + Notion';
    document.querySelector('.modal-footer').insertBefore(notionBtn, saveBtn);
  }
  notionBtn.style.display = 'inline-block';
  notionBtn.onclick = confirmDeleteNotion;
  document.querySelector('.modal-title').textContent = 'Eliminar nota';
  document.getElementById('edit-modal').classList.add('visible');
}

function confirmDeleteLocal() {
  if (_pendingDelete === null) return;
  notes.splice(_pendingDelete, 1);
  try { localStorage.setItem('sf_notes', JSON.stringify(notes)); } catch(e){}
  _pendingDelete = null;
  closeDeleteModal();
  renderHistory();
}

function confirmDeleteNotion() {
  if (_pendingDelete === null) return;
  var n = notes[_pendingDelete];
  if (n.page_id) {
    fetch('/delete-notion', {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ page_id: n.page_id })
    }).catch(function(){});
  }
  notes.splice(_pendingDelete, 1);
  try { localStorage.setItem('sf_notes', JSON.stringify(notes)); } catch(e){}
  _pendingDelete = null;
  closeDeleteModal();
  renderHistory();
}

function closeDeleteModal() {
  document.querySelector('.modal-title').textContent = 'Editar nota';
  var notionBtn = document.getElementById('delete-notion-btn');
  if (notionBtn) notionBtn.style.display = 'none';
  var st = document.getElementById('edit-status');
  st.style.display = 'none';
  var saveBtn = document.getElementById('edit-save-btn');
  saveBtn.textContent = '⚡ Re-procesar y guardar';
  saveBtn.onclick     = saveEditedNote;
  document.getElementById('edit-modal').classList.remove('visible');
}

// ── STATS ─────────────────────────────────────────────────────────────────────
function renderStats() {
  var c = document.getElementById('stats-container');
  if (!notes.length) {
    c.innerHTML = '<div class="empty"><div class="empty-icon">◎</div><div class="empty-text">Procesa notas primero</div></div>';
    return;
  }
  var knowledge = notes.filter(function(n){ return n.type === 'KNOWLEDGE'; }).length;
  var business  = notes.filter(function(n){ return n.type === 'BUSINESS';  }).length;
  var pinned    = notes.filter(function(n){ return n.pinned; }).length;
  var tagCount  = {};
  notes.forEach(function(n){ (n.tags||[]).forEach(function(t){ tagCount[t] = (tagCount[t]||0) + 1; }); });
  var topTags  = Object.keys(tagCount).sort(function(a,b){ return tagCount[b]-tagCount[a]; }).slice(0,8);
  var maxCount = topTags.length ? tagCount[topTags[0]] : 1;
  var html = '<div class="stats-grid">' +
    '<div class="stat-card"><div class="stat-value">'+notes.length+'</div><div class="stat-label">Total notas</div></div>' +
    '<div class="stat-card"><div class="stat-value">'+knowledge+'</div><div class="stat-label">Knowledge</div></div>' +
    '<div class="stat-card"><div class="stat-value">'+business+'</div><div class="stat-label">Business</div></div>' +
    '<div class="stat-card"><div class="stat-value">'+pinned+'</div><div class="stat-label">Pinneadas</div></div>' +
    '</div>';
  if (topTags.length) {
    html += '<div class="tags-chart"><div class="tags-chart-title">Tags más usados</div>';
    topTags.forEach(function(t){
      var pct = Math.round((tagCount[t]/maxCount)*100);
      html += '<div class="tag-bar-row">' +
        '<div class="tag-bar-label">'+esc(t)+'</div>' +
        '<div class="tag-bar-track"><div class="tag-bar-fill" style="width:'+pct+'%"></div></div>' +
        '<div class="tag-bar-count">'+tagCount[t]+'</div>' +
        '</div>';
    });
    html += '</div>';
  }
  c.innerHTML = html;
}

// ── CHAT ──────────────────────────────────────────────────────────────────────
var chatFilter = 'all';
var ideasMode  = false;

function setChatFilter(f, el) {
  chatFilter = f;
  document.querySelectorAll('.chat-filter-btn:not(#cf-ideas)').forEach(function(b){ b.classList.remove('active'); });
  el.classList.add('active');
  renderCtx();
}

function toggleIdeasMode(el) {
  ideasMode = !ideasMode;
  el.classList.toggle('active', ideasMode);
  el.style.borderColor = ideasMode ? '#444' : 'transparent';
  el.style.color       = ideasMode ? 'var(--text)' : 'var(--text3)';
  var input = document.getElementById('chat-input');
  input.placeholder = ideasMode ? 'Tema o área para explorar ideas...' : 'Pregunta sobre tus notas...';
}

function renderCtx() {
  var c = document.getElementById('ctx-list');
  if (!notes.length) { c.innerHTML = '<div style="color:var(--text3);font-size:12px">Procesa notas primero.</div>'; return; }
  var filteredNotes = notes.filter(function(n) {
    if (chatFilter === 'all') return true;
    return n.type === chatFilter;
  });
  if (!filteredNotes.length) {
    c.innerHTML = '<div style="color:var(--text3);font-size:12px">No hay notas de tipo ' + chatFilter + '.</div>';
    return;
  }
  var html = '';
  filteredNotes.forEach(function(n) {
    var pid   = n.page_id;
    var on    = selected[pid] ? 'on' : '';
    var check = selected[pid] ? '<svg width="9" height="9" viewBox="0 0 9 9"><path d="M1.5 4.5l2 2L7.5 2" stroke="#0a0a0a" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>' : '';
    html += '<div class="context-note '+on+'" onclick="toggleCtx(\''+pid+'\')">' +
      '<div class="ctx-check">'+check+'</div>' +
      '<div class="ctx-title">'+esc(n.title)+'</div></div>';
  });
  c.innerHTML = html;
}

function toggleCtx(pid) {
  selected[pid] = !selected[pid];
  renderCtx();
}

function chatKey(e) {
  if (e.key === 'Enter') { e.preventDefault(); sendChat(); }
}

async function sendChat() {
  var input = document.getElementById('chat-input');
  var q     = input.value.trim();
  if (!q) return;
  input.value = '';
  addMsg('user', q);
  var ctx = '';
  Object.keys(selected).forEach(function(pid) {
    if (selected[pid]) {
      var nota = notes.find(function(n){ return n.page_id === pid; });
      if (nota) ctx += 'NOTA: ' + nota.title + '\n' + (nota.content || nota.summary || '') + '\n\n---\n\n';
    }
  });
  var loadEl = addMsg('assistant', '<span class="spin"></span>');
  try {
    var body = { question: q, context: ctx };
    if (ideasMode) body.ideas_mode = true;
    var res = await fetch('/chat', {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify(body)
    });
    if (res.status === 401) { doLogout(); return; }
    var data = await res.json();
    loadEl.textContent = data.answer || 'Sin respuesta.';
  } catch(e) {
    loadEl.textContent = 'Error al consultar.';
  }
}

function addMsg(role, html) {
  var msgs = document.getElementById('chat-msgs');
  var av   = role === 'user' ? 'D' : 'S';
  var div  = document.createElement('div');
  div.className = 'msg ' + role;
  div.innerHTML = '<div class="msg-av">'+av+'</div><div class="msg-body"></div>';
  var body = div.querySelector('.msg-body');
  body.innerHTML = html;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return body;
}

function esc(str) {
  if (!str) return '';
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── BULK SELECT ───────────────────────────────────────────────────────────────
var bulkMode     = false;
var bulkSelected = {};

function toggleBulkMode() {
  bulkMode     = !bulkMode;
  bulkSelected = {};
  var btn = document.getElementById('bulk-toggle');
  var bar = document.getElementById('bulk-bar');
  btn.classList.toggle('on', bulkMode);
  btn.textContent = bulkMode ? '✕ Salir' : '☐ Seleccionar';
  bar.classList.toggle('visible', bulkMode);
  renderHistory();
}

function toggleBulkCard(e, pageId) {
  e.stopPropagation();
  if (!bulkMode) return;
  bulkSelected[pageId] = !bulkSelected[pageId];
  var count = Object.values(bulkSelected).filter(Boolean).length;
  document.getElementById('bulk-count').textContent = count + ' seleccionada' + (count !== 1 ? 's' : '');
  renderHistory();
}

async function bulkDelete() {
  var ids = Object.keys(bulkSelected).filter(function(id){ return bulkSelected[id]; });
  if (!ids.length) return;
  if (!confirm('¿Eliminar ' + ids.length + ' nota(s) de Notion y del historial?')) return;
  var bar = document.getElementById('bulk-bar');
  bar.querySelector('.btn-danger').disabled = true;
  bar.querySelector('.btn-danger').textContent = '⏳ Eliminando...';
  for (var i = 0; i < ids.length; i++) {
    var pageId = ids[i];
    try {
      await fetch('/delete-notion', {
        method: 'POST', headers: authHeaders(),
        body: JSON.stringify({ page_id: pageId })
      });
    } catch(e) {}
    notes = notes.filter(function(n){ return n.page_id !== pageId; });
  }
  try { localStorage.setItem('sf_notes', JSON.stringify(notes)); } catch(e) {}
  toggleBulkMode();
}

// ── EDIT MODAL ────────────────────────────────────────────────────────────────
var editingIndex = -1;

function openEditModal(e, idx) {
  e.stopPropagation();
  editingIndex = idx;
  var n = notes[idx];
  document.getElementById('edit-title').value = n.title  || '';
  document.getElementById('edit-body').value  = n.content || '';
  var st = document.getElementById('edit-status');
  st.style.display = 'none'; st.textContent = '';
  document.getElementById('edit-save-btn').disabled = false;
  document.getElementById('edit-save-btn').textContent = '⚡ Re-procesar y guardar';
  document.getElementById('edit-modal').classList.add('visible');
}

function closeEditModal(e) {
  if (e && e.target !== document.getElementById('edit-modal')) return;
  if (_pendingDelete !== null) { closeDeleteModal(); return; }
  document.getElementById('edit-modal').classList.remove('visible');
  editingIndex = -1;
}

async function saveEditedNote() {
  var title   = document.getElementById('edit-title').value.trim();
  var body    = document.getElementById('edit-body').value.trim();
  var saveBtn = document.getElementById('edit-save-btn');
  var st      = document.getElementById('edit-status');
  if (!title && !body) return;
  var content = title ? ('# ' + title + '\n\n' + body) : body;
  saveBtn.disabled = true;
  saveBtn.innerHTML = '<span class="spin"></span> Procesando...';
  st.style.display = 'none';
  try {
    var res = await fetch('/reprocess', {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ content: content })
    });
    if (res.status === 401) { doLogout(); return; }
    var data = await res.json();
    if (data.error) throw new Error(data.error);
    data.content = content;
    data.date    = new Date().toISOString();
    data.pinned  = notes[editingIndex] ? notes[editingIndex].pinned : false;
    if (editingIndex >= 0) notes[editingIndex] = data;
    try { localStorage.setItem('sf_notes', JSON.stringify(notes)); } catch(e) {}
    st.style.display = 'block';
    st.style.background = 'rgba(74,222,128,0.07)';
    st.style.border     = '1px solid rgba(74,222,128,0.2)';
    st.style.color      = 'var(--green)';
    st.textContent      = '✓ Guardado en Notion';
    saveBtn.textContent = '✓ Guardado';
    renderHistory();
    setTimeout(function(){ closeEditModal({}); }, 1200);
  } catch(err) {
    st.style.display = 'block';
    st.style.background = 'rgba(248,113,113,0.07)';
    st.style.border     = '1px solid rgba(248,113,113,0.2)';
    st.style.color      = 'var(--red)';
    st.textContent      = '✗ ' + err.message;
    saveBtn.disabled    = false;
    saveBtn.textContent = '⚡ Re-procesar y guardar';
  }
}

// ── REMINDERS ─────────────────────────────────────────────────────────────────
var reminderIndex = -1;

function openReminderModal(e, idx) {
  e.stopPropagation();
  reminderIndex = idx;
  var n = notes[idx];
  document.getElementById('reminder-note-title').textContent = n.title || '—';
  document.getElementById('reminder-date-input').value = n.reminder_date ? n.reminder_date.slice(0,10) : '';
  document.getElementById('reminder-save-btn').disabled = false;
  document.getElementById('reminder-save-btn').textContent = 'Guardar';
  document.getElementById('reminder-modal').classList.add('visible');
}

function closeReminderModal(e) {
  if (e && e.target !== document.getElementById('reminder-modal')) return;
  document.getElementById('reminder-modal').classList.remove('visible');
  reminderIndex = -1;
}

function setReminderShortcut(days) {
  var d = new Date();
  d.setDate(d.getDate() + days);
  document.getElementById('reminder-date-input').value = d.toISOString().slice(0,10);
}

async function saveReminder() {
  var dateVal = document.getElementById('reminder-date-input').value;
  if (!dateVal) { alert('Selecciona una fecha.'); return; }
  var btn = document.getElementById('reminder-save-btn');
  btn.disabled = true; btn.textContent = '...';
  var n = notes[reminderIndex];
  try {
    var res = await fetch('/set-reminder', {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ page_id: n.page_id, date: dateVal })
    });
    if (res.status === 401) { doLogout(); return; }
    var data = await res.json();
    if (data.error) throw new Error(data.error);
    notes[reminderIndex].reminder_date = dateVal;
    try { localStorage.setItem('sf_notes', JSON.stringify(notes)); } catch(e) {}
    document.getElementById('reminder-modal').classList.remove('visible');
    reminderIndex = -1;
    renderHistory();
    if (document.getElementById('view-stats').classList.contains('active')) renderStats();
  } catch(err) {
    alert('Error: ' + err.message);
    btn.disabled = false; btn.textContent = 'Guardar';
  }
}

async function clearReminder() {
  var btn = document.getElementById('reminder-save-btn');
  btn.disabled = true;
  var n = notes[reminderIndex];
  try {
    await fetch('/set-reminder', {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ page_id: n.page_id, date: '' })
    });
    notes[reminderIndex].reminder_date = null;
    try { localStorage.setItem('sf_notes', JSON.stringify(notes)); } catch(e) {}
    document.getElementById('reminder-modal').classList.remove('visible');
    reminderIndex = -1;
    renderHistory();
    if (document.getElementById('view-stats').classList.contains('active')) renderStats();
  } catch(err) {
    alert('Error: ' + err.message);
  }
  btn.disabled = false;
}

async function renderReminders() {
  var c = document.getElementById('reminders-container');
  if (!c) return;
  try {
    var res = await fetch('/reminders', { method: 'GET', headers: authHeaders() });
    if (res.status === 401) { doLogout(); return; }
    var data = await res.json();
    var reminders = data.reminders || [];
    if (!reminders.length) { c.innerHTML = ''; return; }
    var html = '<div class="reminder-panel">' +
      '<div class="reminder-panel-header">' +
        '<span class="panel-label">🔔 Recordatorios</span>' +
        '<span class="panel-label">'+reminders.length+' pendiente'+(reminders.length!==1?'s':'')+'</span>' +
      '</div>';
    reminders.forEach(function(r) {
      var dotClass  = r.is_overdue ? 'overdue' : r.is_today ? 'today' : '';
      var dateLabel = r.is_today ? 'Hoy' : r.is_overdue ? 'Vencido · '+r.reminder_date.slice(0,10) : r.reminder_date.slice(0,10);
      html += '<div class="reminder-item">' +
        '<div class="reminder-dot '+dotClass+'"></div>' +
        '<a href="'+r.url+'" target="_blank" class="reminder-title" style="text-decoration:none;color:var(--text)">'+esc(r.title)+'</a>' +
        '<span class="reminder-date-label">'+dateLabel+'</span>' +
        '<button class="reminder-clear" title="Quitar recordatorio" onclick="clearReminderById(\''+r.page_id+'\',this)">×</button>' +
      '</div>';
    });
    html += '</div>';
    c.innerHTML = html;
  } catch(e) {
    c.innerHTML = '';
  }
}

async function clearReminderById(pageId, btn) {
  btn.disabled = true;
  try {
    await fetch('/set-reminder', {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ page_id: pageId, date: '' })
    });
    notes.forEach(function(n){ if (n.page_id === pageId) n.reminder_date = null; });
    try { localStorage.setItem('sf_notes', JSON.stringify(notes)); } catch(e) {}
    renderReminders();
    renderHistory();
  } catch(e) {
    btn.disabled = false;
  }
}

// ── INBOX / GOOGLE ────────────────────────────────────────────────────────────
var googleConnected = false;
var calWeekOffset   = 0;
var _inboxEmails    = [];

function avatarColor(str) {
  var palette = ['#4A8EF5','#E57373','#81C784','#FFB74D','#BA68C8','#4DD0E1','#F06292','#AED581','#FF8A65','#90A4AE'];
  var hash = 0;
  for (var i = 0; i < str.length; i++) { hash = str.charCodeAt(i) + ((hash << 5) - hash); }
  return palette[Math.abs(hash) % palette.length];
}

function emailTimeStr(rfcDate) {
  if (!rfcDate) return '';
  var d = new Date(rfcDate), now = new Date();
  if (d.toDateString() === now.toDateString())
    return d.toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' });
  return d.toLocaleDateString('es-PE', { day: '2-digit', month: 'short' });
}

async function checkGoogleStatus() {
  try {
    var res = await fetch('/auth/google/status', { headers: authHeaders() });
    var data = await res.json();
    googleConnected = data.connected;
    var connectDiv = document.getElementById('inbox-connect');
    var contentDiv = document.getElementById('inbox-content');
    if (connectDiv) connectDiv.style.display = googleConnected ? 'none' : 'block';
    if (contentDiv) contentDiv.style.display = googleConnected ? 'block' : 'none';
    if (googleConnected) {
      loadInbox();
      loadCalendar();
    }
  } catch(e) {
    console.error('Error checking Google status:', e);
  }
}

function initInboxView() {
  checkGoogleStatus();
}

function connectGoogle() {
  // Abre el flujo OAuth en popup
  var w = 600, h = 700;
  var left = (screen.width  - w) / 2;
  var top  = (screen.height - h) / 2;
  // El endpoint /auth/google necesita el token — lo pasamos via header no es posible en redirect
  // Alternativa: window.location para redirect directo
  window.open(
    '/auth/google?_token=' + encodeURIComponent(authToken),
    'google_oauth',
    'width='+w+',height='+h+',left='+left+',top='+top
  );
}

function showEmailPreview(email, itemEl) {
  var preview = document.getElementById('email-preview');
  if (!preview || !email) return;

  var fromName = email.from.replace(/<[^>]+>/, '').trim() || email.from;
  var isMobile = window.innerWidth <= 900;
  var pane = document.querySelector('.gmail-2pane');

  document.querySelectorAll('.email-item').forEach(function(el) {
    el.classList.remove('selected');
  });
  if (itemEl) itemEl.classList.add('selected');

  preview.innerHTML =
    '<div class="email-preview-panel">' +
      (isMobile ? '<button class="email-back-btn" onclick="hideEmailPreview()">← Volver</button>' : '') +
      '<div class="preview-subject">' + esc(email.subject || '') + '</div>' +
      '<div class="preview-from">' + esc(fromName) + '</div>' +
      '<div class="preview-date">' + esc(emailTimeStr(email.date)) + '</div>' +
      '<div class="preview-body">' + esc(email.snippet || '') + '</div>' +
      '<a href="' + esc(email.url || '#') + '" target="_blank" class="preview-open-link">Abrir en Gmail ↗</a>' +
    '</div>';

  preview.classList.add('active');
  if (isMobile && pane) pane.classList.add('preview-open');
}

function hideEmailPreview() {
  var preview = document.getElementById('email-preview');
  if (preview) preview.classList.remove('active');
  var pane = document.querySelector('.gmail-2pane');
  if (pane) pane.classList.remove('preview-open');
  document.querySelectorAll('.email-item').forEach(function(el) {
    el.classList.remove('selected');
  });
}

function switchInboxTab(tab) {
  document.querySelectorAll('.inbox-tab').forEach(function(t){ t.classList.remove('active'); });
  document.querySelectorAll('.inbox-pane').forEach(function(p){ p.classList.remove('active'); });
  var tabEl  = document.getElementById('tab-' + tab);
  var paneEl = document.getElementById('pane-' + tab);
  if (tabEl)  tabEl.classList.add('active');
  if (paneEl) paneEl.classList.add('active');
  if (tab === 'gmail')    loadInbox();
  if (tab === 'calendar') loadCalendar();
}

async function loadInbox() {
  var el = document.getElementById('email-list');
  if (!el) return;
  el.innerHTML = '<div class="inbox-loading"><span class="spin"></span> Cargando Gmail...</div>';
  try {
    var res = await fetch('/inbox', { headers: authHeaders() });
    if (res.status === 401) { doLogout(); return; }
    if (res.status === 403) {
      el.innerHTML = '<div class="inbox-empty">Google desconectado. <button class="btn btn-primary" style="margin-top:10px" onclick="connectGoogle()">Reconectar</button></div>';
      googleConnected = false;
      document.getElementById('inbox-connect').style.display = 'block';
      document.getElementById('inbox-content').style.display = 'none';
      return;
    }
    var data = await res.json();
    if (data.error) throw new Error(data.error);
    var emails  = data.emails || [];
    var unread  = emails.filter(function(e){ return e.unread; }).length;
    var badge = document.getElementById('nav-unread');
    if (badge) {
      if (unread > 0) { badge.textContent = unread; badge.style.display = 'inline'; }
      else            { badge.style.display = 'none'; }
    }
    if (!emails.length) {
      el.innerHTML = '<div class="inbox-empty">Inbox vacío 🎉</div>';
      return;
    }
    _inboxEmails = emails;
    var html = '';
    emails.forEach(function(email, idx) {
      var fromName = email.from.replace(/<[^>]+>/, '').trim() || email.from;
      html += '<div class="email-item' + (email.unread ? ' unread' : '') + '" onclick="showEmailPreview(_inboxEmails[' + idx + '], this)">' +
        '<div class="email-avatar" style="background:' + avatarColor(email.from) + '">' +
          (email.from.charAt(0) || '?').toUpperCase() +
          (email.unread ? '<div class="email-unread-dot"></div>' : '') +
        '</div>' +
        '<div class="email-from">' + esc(fromName) + '</div>' +
        '<div class="email-time-col">' + esc(emailTimeStr(email.date)) + '</div>' +
        '<div class="email-subject">' + esc(email.subject) + '</div>' +
        '</div>';
    });
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = '<div class="inbox-empty" style="color:var(--red)">Error: '+esc(e.message)+'</div>';
  }
}

function calPrevWeek() { calWeekOffset--; loadCalendar(); }
function calNextWeek() { calWeekOffset++; loadCalendar(); }
function calGoToday()  { calWeekOffset = 0; loadCalendar(); }

async function loadCalendar() {
  var el = document.getElementById('cal-grid-wrap');
  if (!el) { console.warn('loadCalendar: #cal-grid-wrap not found'); return; }

  try {
    var HOUR_START = 7, HOUR_COUNT = 14, HOUR_H = 56;
    var DAY_NAMES  = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
    var EVT_COLORS = ['#4A8EF5','#E57373','#81C784','#FFB74D','#BA68C8','#4DD0E1'];

    var today  = new Date();
    var monday = new Date(today);
    var dow    = today.getDay();
    monday.setDate(today.getDate() - (dow === 0 ? 6 : dow - 1) + (calWeekOffset * 7));
    monday.setHours(0, 0, 0, 0);
    var sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);
    sunday.setHours(23, 59, 59, 999);

    var labelEl = document.getElementById('cal-week-label');
    if (labelEl) {
      labelEl.textContent =
        monday.toLocaleDateString('es-PE', { day: '2-digit', month: 'short' }) +
        ' — ' +
        sunday.toLocaleDateString('es-PE', { day: '2-digit', month: 'short' });
    }

    el.innerHTML = '<div class="inbox-loading"><span class="spin"></span> Cargando Calendar...</div>';

    var res = await fetch(
      '/calendar?time_min=' + encodeURIComponent(monday.toISOString()) +
      '&time_max=' + encodeURIComponent(sunday.toISOString()),
      { headers: authHeaders() }
    );
    if (res.status === 401) { doLogout(); return; }
    if (res.status === 403) {
      el.innerHTML = '<div class="inbox-empty">Google desconectado.</div>';
      return;
    }
    var data = await res.json();
    if (data.error) throw new Error(data.error);
    var events = data.events || [];

    // Build day array: monday..sunday
    var days = [];
    for (var d = 0; d < 7; d++) {
      var day = new Date(monday);
      day.setDate(monday.getDate() + d);
      days.push(day);
    }

    var nowH   = today.getHours();
    var nowMin = today.getMinutes();

    // ── Header ────────────────────────────────────────────────────────────────
    var headHtml = '<div class="cal-grid-head"><div class="cal-gutter-head"></div>';
    days.forEach(function(day) {
      var isToday = day.toDateString() === today.toDateString();
      headHtml += '<div class="cal-day-head' + (isToday ? ' today' : '') + '">' +
        DAY_NAMES[day.getDay()] +
        '<span class="cal-day-head-num">' + day.getDate() + '</span>' +
        '</div>';
    });
    headHtml += '</div>';

    // ── Body ──────────────────────────────────────────────────────────────────
    var bodyHtml = '<div class="cal-grid-body">';

    // Gutter (time labels)
    bodyHtml += '<div class="cal-gutter">';
    for (var h = 0; h < HOUR_COUNT; h++) {
      var hh = HOUR_START + h;
      bodyHtml += '<div class="cal-time-label">' + (hh < 10 ? '0' : '') + hh + ':00</div>';
    }
    bodyHtml += '</div>';

    // Day columns
    days.forEach(function(day) {
      var isToday = day.toDateString() === today.toDateString();
      bodyHtml += '<div class="cal-day-col' + (isToday ? ' today-col' : '') + '">';

      // Hour background stripes
      for (var h = 0; h < HOUR_COUNT; h++) {
        bodyHtml += '<div class="cal-hour-bg"></div>';
      }

      // Events for this day
      events.forEach(function(ev, ei) {
        var evStart = ev.start ? new Date(ev.start) : null;
        var evEnd   = ev.end   ? new Date(ev.end)   : null;
        if (!evStart) return;

        if (ev.all_day) {
          // all_day dates are YYYY-MM-DD strings — compare by date string
          var evDateStr  = ev.start.substring(0, 10);
          var dayDateStr = day.getFullYear() + '-' +
            String(day.getMonth() + 1).padStart(2, '0') + '-' +
            String(day.getDate()).padStart(2, '0');
          if (evDateStr !== dayDateStr) return;
          var color = EVT_COLORS[ei % EVT_COLORS.length];
          bodyHtml += '<div class="cal-event-allday" style="position:absolute;top:3px;background:' + color + ';left:2px;right:2px;border-radius:3px;padding:1px 4px;font-size:10px;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;z-index:2">' +
            esc(ev.title) + '</div>';
        } else {
          if (evStart.toDateString() !== day.toDateString()) return;
          var startH = evStart.getHours() + evStart.getMinutes() / 60;
          var endH   = evEnd ? (evEnd.getHours() + evEnd.getMinutes() / 60) : (startH + 1);
          var durH   = Math.max(endH - startH, 0.25);
          var topPx  = (startH - HOUR_START) * HOUR_H;
          var htPx   = durH * HOUR_H;
          var color  = EVT_COLORS[ei % EVT_COLORS.length];
          var timeLabel = evStart.toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' }) +
            (evEnd ? ' – ' + evEnd.toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' }) : '');
          bodyHtml += '<a href="' + ev.url + '" target="_blank" class="cal-event-block" style="top:' + topPx + 'px;height:' + htPx + 'px;background:' + color + ';left:2px;right:2px">' +
            '<div class="cal-event-block-title">' + esc(ev.title) + '</div>' +
            '<div class="cal-event-block-time">' + esc(timeLabel) + '</div>' +
            '</a>';
        }
      });

      // Now line
      if (isToday) {
        var nowTop = (nowH + nowMin / 60 - HOUR_START) * HOUR_H;
        bodyHtml += '<div class="cal-now-line" style="top:' + nowTop + 'px"></div>';
      }

      bodyHtml += '</div>';
    });

    bodyHtml += '</div>';

    el.innerHTML = headHtml + bodyHtml;

    // Auto-scroll to current hour
    if (calWeekOffset === 0) {
      el.scrollTop = (nowH - 8) * HOUR_H;
    }
  } catch(e) {
    console.error('loadCalendar error:', e);
    el.innerHTML = '<div class="inbox-empty" style="color:var(--red)">Error: ' + esc(e.message) + '</div>';
  }
}

// ── BOOT ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', checkAuth);
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    document.getElementById('reminder-modal').classList.remove('visible');
    reminderIndex = -1;
  }
});
