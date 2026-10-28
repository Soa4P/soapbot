/*
 * Roadmap page — synchronises diagram node status with progress.json.
 *
 * The diagram is authored as static SVG in roadmap.html rather than generated here.
 * Reason: a flowchart is a *design artefact*. Generating it from data would mean the
 * shape is implied by a layout algorithm, and any edit to the argument ("P1 must pass
 * before P2 starts") would become an edit to layout code. Static SVG keeps the
 * argument legible in the file itself; this script only paints the status dots.
 *
 * Failure behaviour: if progress.json cannot be read, the diagram keeps its authored
 * statuses and a banner says so. It never silently shows a stale green.
 */

(function () {
  'use strict';

  const STATUS_LABEL = {
    done: '已完成',
    doing: '进行中',
    todo: '未启动',
    blocked: '受阻',
    unverified: '未验证',
  };

  const banner = document.getElementById('roadmap-banner');

  function paint(statusMap) {
    const nodes = document.querySelectorAll('[data-node]');
    let painted = 0;
    nodes.forEach(function (node) {
      const id = node.getAttribute('data-node');
      const status = statusMap[id];
      if (!status) return;
      node.setAttribute('data-status', status);
      const badge = node.querySelector('.node__status');
      if (badge) badge.textContent = STATUS_LABEL[status] || status;
      painted += 1;
    });
    return painted;
  }

  async function sync() {
    try {
      const resp = await fetch('progress.json', { cache: 'no-store' });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();

      /* progress.json is the source of truth for *tasks*; the roadmap maps phases to
       * whichever task is the phase's gate. A phase is only "done" when every one of
       * its tasks is done — a phase with 3 of 4 tasks done is still in progress, and
       * rounding that to "done" is the specific dishonesty this page exists to avoid. */
      const statusMap = {};
      (data.phases || []).forEach(function (phase) {
        const tasks = phase.tasks || [];
        if (!tasks.length) return;
        const files = tasks.flatMap(function (t) { return t.files || []; });
        const doneFiles = files.filter(function (f) { return f.status === 'done'; }).length;
        const allDone = tasks.every(function (t) { return t.status === 'done'; }) &&
          (files.length === 0 || doneFiles === files.length);
        const anyDoing = tasks.some(function (t) { return t.status === 'doing'; });
        statusMap[phase.id] = allDone ? 'done' : anyDoing ? 'doing' : 'todo';
      });

      const painted = paint(statusMap);
      if (banner && painted > 0) {
        banner.hidden = true;
      } else if (banner) {
        banner.textContent = '进度数据中没有匹配的阶段，图示状态为手工标注值。';
        banner.hidden = false;
      }
    } catch (err) {
      if (banner) {
        banner.textContent =
          '无法读取 progress.json（' + err.message + '）。图示保留手工标注状态，不代表实时进度。';
        banner.hidden = false;
      }
    }
  }

  /* Docker is a cross-cutting constraint, not a phase: it gates nothing in code but
   * blocks the word "verified" in the final report. Painted separately so it cannot
   * be mistaken for a phase someone can tick off. */
  function markDocker() {
    const box = document.querySelector('[data-node="docker"]');
    if (!box) return;
    box.setAttribute('data-status', 'unverified');
  }

  document.addEventListener('DOMContentLoaded', function () {
    markDocker();
    sync();
  });
})();
