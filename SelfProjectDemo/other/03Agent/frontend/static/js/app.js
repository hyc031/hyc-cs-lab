/* ============================================================
   主入口：模式切换、Toast、初始化各模块
   依赖顺序：markdown.js → api.js → config.js → travel.js → chat.js → app.js
   ============================================================ */
(function (global) {
  'use strict';

  function $(id) { return document.getElementById(id); }

  // ---- Toast ----
  var toastTimer = null;
  function toast(msg, kind) {
    var el = $('toast');
    el.textContent = msg;
    el.className = 'toast' + (kind ? ' toast-' + kind : '');
    el.hidden = false;
    // 强制回流以触发过渡
    void el.offsetWidth;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      el.classList.remove('show');
      setTimeout(function () { el.hidden = true; }, 320);
    }, 2800);
  }

  global.UI = { toast: toast };

  // ---- 模式切换 ----
  function setupModeSwitch() {
    var btns = Array.prototype.slice.call(document.querySelectorAll('.mode-btn'));
    var thumb = document.querySelector('.mode-thumb');
    var views = {
      travel: $('view-travel'),
      chat: $('view-chat')
    };

    function moveThumb(btn) {
      // offsetLeft 相对 .mode-switch，减去容器 padding(5px) 对齐
      thumb.style.width = btn.offsetWidth + 'px';
      thumb.style.transform = 'translateX(' + (btn.offsetLeft - 5) + 'px)';
    }

    function activate(mode) {
      btns.forEach(function (b) {
        var on = b.dataset.mode === mode;
        b.classList.toggle('is-active', on);
        b.setAttribute('aria-selected', on ? 'true' : 'false');
        if (on) moveThumb(b);
      });
      Object.keys(views).forEach(function (k) {
        views[k].classList.toggle('is-active', k === mode);
      });
    }

    btns.forEach(function (b) {
      b.addEventListener('click', function () { activate(b.dataset.mode); });
    });

    // 初始定位 thumb
    var active = document.querySelector('.mode-btn.is-active');
    if (active) moveThumb(active);
    window.addEventListener('resize', function () {
      var cur = document.querySelector('.mode-btn.is-active');
      if (cur) moveThumb(cur);
    });
  }

  function init() {
    setupModeSwitch();
    ConfigPanel.init();
    TravelMode.init();
    ChatMode.init();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
