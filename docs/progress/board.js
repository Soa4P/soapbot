/*
 * Progress board renderer.
 *
 * Read-only by design: the numbers are recomputed from the file list every load,
 * so nobody can type "80%" into a form and have the board believe it. The only
 * trust anchor is `updated_at` — see STALE_MS below.
 */
'use strict';

var DATA_URL = 'progress.json';
var STALE_MS = 10 * 60 * 1000;
var POLL_MS = 15000;

var STATUS_TEXT = { done: '已完成', doing: '进行中', todo: '未启动', blocked: '受阻' };

var state = { data: null, filter: 'all', open: new Set(), timer: null, lastOkAt: null };

function $(id) { return document.getElementById(id); }

function el(tag, cls, text) {
  var n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

/* ---------------------------------------------------------------- progress */

/* Weight = number of files in the task (1 when the task lists none, so a task
   without a file breakdown still counts for something). A task with 3 of 4 files
   done contributes 0.75 — half-finished work must not read as either 0 or 1. */
function taskRatio(task) {
  var files = task.files || [];
  if (!files.length) return task.status === 'done' ? 1 : 0;
  var done = files.filter(function (f) { return f.status === 'done'; }).length;
  return done / files.length;
}

function taskWeight(task) {
  return (task.files && task.files.length) || 1;
}

function ratio(tasks) {
  var w = 0, acc = 0;
  tasks.forEach(function (t) {
    var weight = taskWeight(t);
    w += weight;
    acc += weight * taskRatio(t);
  });
  return w ? acc / w : 0;
}

function allTasks(data) {
  var out = [];
  (data.phases || []).forEach(function (p) {
    (p.tasks || []).forEach(function (t) { out.push({ phase: p, task: t }); });
  });
  return out;
}

/* ------------------------------------------------------------------ render */

function pill(status) {
  var p = el('span', 'pill pill--' + status, STATUS_TEXT[status] || status);
  return p;
}

function renderBanners(data) {
  var host = $('banners');
  host.textContent = '';
  if (!data) return;
  var age = Date.now() - new Date(data.updated_at).getTime();
  if (age > STALE_MS) {
    var b = el('div', 'banner banner--stale');
    b.appendChild(el('strong', null, '数据可能已过期'));
    b.appendChild(el('span', null, '最后一次更新于 ' + relTime(data.updated_at) + '，超过 10 分钟未刷新。以下是当时的进度，不代表现在。'));
    host.appendChild(b);
  }
}

function relTime(iso) {
  var t = new Date(iso).getTime();
  if (isNaN(t)) return iso;
  var d = Math.round((Date.now() - t) / 1000);
  if (d < 60) return d + ' 秒前';
  if (d < 3600) return Math.round(d / 60) + ' 分钟前';
  if (d < 86400) return Math.round(d / 3600) + ' 小时前';
  return Math.round(d / 86400) + ' 天前';
}

function renderSummary(data) {
  var tasks = allTasks(data).map(function (x) { return x.task; });
  var pct = Math.round(ratio(tasks) * 100);
  $('pct-value').innerHTML = pct + '<small>%</small>';
  $('overall-bar').setAttribute('aria-valuenow', String(pct));
  $('overall-fill').style.width = pct + '%';
  $('summary-sub').textContent = tasks.length + ' 个任务 · ' + (data.phases || []).length + ' 个阶段';

  var counts = { done: 0, doing: 0, todo: 0, blocked: 0 };
  tasks.forEach(function (t) { if (counts[t.status] != null) counts[t.status] += 1; });
  $('count-done').textContent = counts.done;
  $('count-doing').textContent = counts.doing;
  $('count-todo').textContent = counts.todo;
  $('count-blocked').textContent = counts.blocked;

  $('summary-card').hidden = false;
  $('filter-card').hidden = false;
}

function renderCurrent(data) {
  var body = $('current-body');
  body.textContent = '';
  var cur = data.current;
  $('current-card').hidden = false;

  if (!cur) {
    body.className = 'current current--idle';
    body.appendChild(el('div', 'current__task', '当前无进行中任务'));
    body.appendChild(el('div', 'current__step', '所有任务要么已完成，要么尚未启动。'));
    return;
  }
  body.className = 'current';
  var phase = (data.phases || []).filter(function (p) { return p.id === cur.phase; })[0];
  var task = phase && (phase.tasks || []).filter(function (t) { return t.id === cur.task; })[0];
  body.appendChild(el('div', 'current__crumbs',
    (phase ? phase.index + ' · ' + phase.name : cur.phase) + (task ? '  /  ' + task.name : '')));
  body.appendChild(el('div', 'current__task', task ? task.name : cur.task));
  if (cur.step) body.appendChild(el('div', 'current__step', cur.step));
  if (task) body.appendChild(pill(task.status));
}

function renderPhases(data) {
  var host = $('phases');
  host.textContent = '';
  var shown = 0;

  (data.phases || []).forEach(function (phase) {
    var tasks = (phase.tasks || []).filter(function (t) {
      return state.filter === 'all' || t.status === state.filter;
    });
    if (!tasks.length) return;
    shown += tasks.length;

    var pct = Math.round(ratio(phase.tasks || []) * 100);
    var wrap = el('section', 'phase');
    var head = el('div', 'phase__head');
    head.appendChild(el('span', 'phase__idx', phase.index));
    head.appendChild(el('span', 'phase__name', phase.name));
    var bar = el('div', 'phase__bar');
    var track = el('div', 'bar');
    track.setAttribute('role', 'progressbar');
    track.setAttribute('aria-valuemin', '0');
    track.setAttribute('aria-valuemax', '100');
    track.setAttribute('aria-valuenow', String(pct));
    track.setAttribute('aria-label', phase.name + ' 完成度');
    var fill = el('div', 'bar__fill');
    fill.style.width = pct + '%';
    track.appendChild(fill);
    bar.appendChild(track);
    head.appendChild(bar);
    head.appendChild(el('span', 'phase__pct', pct + '%'));
    wrap.appendChild(head);

    var body = el('div', 'phase__body');
    tasks.forEach(function (task) { body.appendChild(renderTask(task)); });
    wrap.appendChild(body);
    host.appendChild(wrap);
  });

  $('filter-meta').textContent = state.filter === 'all'
    ? '共 ' + allTasks(data).length + ' 个任务'
    : '匹配 ' + shown + ' 个任务';

  if (!shown) {
    var msg = state.filter === 'todo'
      ? '没有未启动的任务 —— 每一项都已经开始或完成。'
      : '当前筛选下没有任务。';
    host.appendChild(el('div', 'empty-state', msg));
  }
}

function renderTask(task) {
  var row = el('div', 'task');
  var head = el('div', 'task__row');
  head.appendChild(pill(task.status));

  var mid = el('div');
  mid.appendChild(el('div', 'task__name', task.name));
  if (task.note) mid.appendChild(el('div', 'task__note', task.note));
  head.appendChild(mid);

  var files = task.files || [];
  if (files.length) {
    var open = state.open.has(task.id);
    var btn = el('button', 'task__toggle', (open ? '收起' : '展开') + ' ' + files.length + ' 个文件');
    btn.type = 'button';
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    btn.addEventListener('click', function () {
      if (state.open.has(task.id)) state.open.delete(task.id);
      else state.open.add(task.id);
      renderPhases(state.data);
    });
    head.appendChild(btn);
  }
  row.appendChild(head);

  if (files.length && state.open.has(task.id)) {
    var list = el('ul', 'files');
    files.forEach(function (f) {
      var li = el('li');
      li.appendChild(el('span', 'dot dot--' + f.status));
      li.appendChild(el('span', 'path', f.path));
      li.appendChild(el('span', 'fl', STATUS_TEXT[f.status] || f.status));
      list.appendChild(li);
    });
    row.appendChild(list);
  }
  return row;
}

/* ------------------------------------------------------------------- load */

function showError(err) {
  var host = $('banners');
  var b = el('div', 'banner banner--error');
  b.appendChild(el('strong', null, '无法读取 progress.json'));
  b.appendChild(el('span', null, String(err && err.message ? err.message : err)));
  var sp = el('span', 'banner__spacer');
  b.appendChild(sp);
  var retry = el('button', 'btn', '重试');
  retry.type = 'button';
  retry.addEventListener('click', load);
  b.appendChild(retry);
  host.appendChild(b);
}

function paint(data) {
  state.data = data;
  $('project-name').textContent = data.project || '开发进度';
  $('updated-line').textContent = '最后更新 ' + relTime(data.updated_at) + '（' + new Date(data.updated_at).toLocaleString('zh-CN') + '）';
  $('initial-empty').hidden = true;
  renderBanners(data);
  renderSummary(data);
  renderCurrent(data);
  renderPhases(data);
}

function load() {
  fetch(DATA_URL + '?t=' + Date.now(), { cache: 'no-store' })
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status + '，请确认已用 HTTP 服务打开（file:// 下 fetch 会被浏览器拦截）');
      return r.json();
    })
    .then(function (data) {
      state.lastOkAt = Date.now();
      paint(data);
    })
    .catch(function (err) {
      console.error('progress load failed', err);
      $('initial-empty').hidden = true;
      /* Keep the last good render on screen and add the error above it. Blanking
         the board would look like "nothing has been done", a different claim. */
      showError(err);
      if (state.lastOkAt) {
        $('foot-stale').textContent = '上次成功读取 ' + relTime(new Date(state.lastOkAt).toISOString());
      }
    });
}

function setFilter(name) {
  state.filter = name;
  Array.prototype.forEach.call(document.querySelectorAll('.chip'), function (c) {
    c.setAttribute('aria-pressed', c.getAttribute('data-filter') === name ? 'true' : 'false');
  });
  if (state.data) renderPhases(state.data);
}

function startPolling() {
  stopPolling();
  state.timer = setInterval(load, POLL_MS);
}

function stopPolling() {
  if (state.timer) { clearInterval(state.timer); state.timer = null; }
}

document.addEventListener('DOMContentLoaded', function () {
  Array.prototype.forEach.call(document.querySelectorAll('.chip'), function (c) {
    c.addEventListener('click', function () { setFilter(c.getAttribute('data-filter')); });
  });
  $('refresh-btn').addEventListener('click', load);
  $('auto-poll').addEventListener('change', function (e) {
    if (e.target.checked) startPolling(); else stopPolling();
  });
  load();
  startPolling();
  /* Relative timestamps go stale on their own; re-read every 15s so
     "3 分钟前" does not sit there claiming it was just now. */
  setInterval(function () { if (state.data) paint(state.data); }, POLL_MS);
});
