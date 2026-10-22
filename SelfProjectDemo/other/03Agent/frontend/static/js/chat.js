/* ============================================================
   日常聊天模式：POST /api/chat (SSE) + MCP 工具调用可视化
   事件：tool_call / tool_result / content / done / error
   会话历史保存在内存中（messages）
   ============================================================ */
(function (global) {
  'use strict';

  var els = {};
  var messages = [];      // [{role, content}]
  var streaming = false;

  function $(id) { return document.getElementById(id); }

  function setSendLoading(loading) {
    els.btnSend.classList.toggle('is-loading', loading);
    els.btnSend.disabled = loading;
    els.input.disabled = loading;
  }

  function scrollToBottom() {
    els.list.scrollTop = els.list.scrollHeight;
  }

  function hideEmpty() {
    if (els.empty) els.empty.hidden = true;
  }

  // ---- 用户气泡 ----
  function addUserMessage(text) {
    hideEmpty();
    var wrap = document.createElement('div');
    wrap.className = 'msg msg-user';
    wrap.innerHTML =
      '<div class="msg-avatar">你</div>' +
      '<div class="msg-bubble"></div>';
    wrap.querySelector('.msg-bubble').textContent = text;
    els.list.appendChild(wrap);
    scrollToBottom();
  }

  // ---- 助手气泡（返回内部 markdown-body 元素以便流式更新）----
  function addAssistantBubble() {
    hideEmpty();
    var wrap = document.createElement('div');
    wrap.className = 'msg msg-assistant';
    wrap.innerHTML =
      '<div class="msg-avatar">智</div>' +
      '<div class="msg-bubble"><div class="markdown-body"></div></div>';
    els.list.appendChild(wrap);
    scrollToBottom();
    return wrap.querySelector('.markdown-body');
  }

  // ---- 工具调用卡片 ----
  function addToolCard(tool, args) {
    hideEmpty();
    var card = document.createElement('div');
    card.className = 'tool-card';
    var argsStr = '';
    try { argsStr = JSON.stringify(args || {}, null, 2); } catch (e) { argsStr = String(args); }
    card.innerHTML =
      '<div class="tool-card-head">' +
        '<span class="tool-card-ico">🔧</span>' +
        '<span>调用工具</span>' +
        '<span class="tool-card-name"></span>' +
      '</div>' +
      '<div class="tool-card-args"></div>';
    card.querySelector('.tool-card-name').textContent = tool || '';
    card.querySelector('.tool-card-args').textContent = argsStr;
    els.list.appendChild(card);
    scrollToBottom();
    return card;
  }

  // ---- 工具结果（附加到最近同名卡片，或新建）----
  function addToolResult(card, tool, result) {
    var resultStr = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
    var block = document.createElement('div');
    block.className = 'tool-card-result';
    var label = document.createElement('div');
    label.className = 'tool-card-result-label';
    label.textContent = '✓ ' + (tool || '') + ' 返回';
    block.appendChild(label);
    var content = document.createElement('div');
    content.textContent = resultStr;
    block.appendChild(content);

    if (card && card.parentNode) {
      card.appendChild(block);
    } else {
      var standalone = document.createElement('div');
      standalone.className = 'tool-card';
      standalone.appendChild(block);
      els.list.appendChild(standalone);
    }
    scrollToBottom();
  }

  function send() {
    if (streaming) return;
    var text = els.input.value.trim();
    if (!text) return;

    messages.push({ role: 'user', content: text });
    addUserMessage(text);
    els.input.value = '';
    els.input.style.height = 'auto';

    streaming = true;
    setSendLoading(true);

    var assistantBody = null;   // 助手 markdown 容器（惰性创建）
    var assistantText = '';
    var lastToolCard = null;    // 最近的 tool_call 卡片，用于挂结果

    function ensureAssistantBody() {
      if (!assistantBody) assistantBody = addAssistantBubble();
      return assistantBody;
    }

    API.stream('/api/chat', { messages: messages.slice() }, {
      onEvent: function (evt) {
        if (!evt || !evt.type) return;
        if (evt.type === 'tool_call') {
          lastToolCard = addToolCard(evt.tool, evt.args);
        } else if (evt.type === 'tool_result') {
          addToolResult(lastToolCard, evt.tool, evt.result);
          lastToolCard = null;
        } else if (evt.type === 'content') {
          assistantText += (evt.delta || '');
          var body = ensureAssistantBody();
          body.innerHTML = MiniMarkdown.render(assistantText) + '<span class="stream-cursor"></span>';
          scrollToBottom();
        } else if (evt.type === 'done') {
          if (assistantBody) {
            assistantBody.innerHTML = MiniMarkdown.render(assistantText);
          }
        }
      },
      onError: function (msg) {
        streaming = false;
        setSendLoading(false);
        var body = ensureAssistantBody();
        body.innerHTML = '<p style="color:var(--err)">⚠️ ' +
          MiniMarkdown.escapeHtml(msg) + '</p>';
        scrollToBottom();
      },
      onDone: function () {
        streaming = false;
        setSendLoading(false);
        if (assistantBody) {
          assistantBody.innerHTML = MiniMarkdown.render(assistantText);
        }
        // 记录到历史（即便为空也保留占位，避免下一轮上下文缺失）
        if (assistantText) {
          messages.push({ role: 'assistant', content: assistantText });
        }
        els.input.focus();
        scrollToBottom();
      }
    });
  }

  function autoGrow() {
    els.input.style.height = 'auto';
    els.input.style.height = Math.min(els.input.scrollHeight, 140) + 'px';
  }

  function init() {
    els = {
      list: $('chatList'), empty: $('chatEmpty'),
      input: $('chatInput'), btnSend: $('btnSend')
    };

    els.btnSend.addEventListener('click', send);
    els.input.addEventListener('input', autoGrow);
    els.input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });
  }

  global.ChatMode = { init: init };
})(window);
