/* ============================================================
   API 层 — 严格遵循 docs/API_CONTRACT.md
   统一响应结构：{ success, data, error }
   SSE：fetch + ReadableStream，按 \n\n 分割，去 "data: " 前缀
   ============================================================ */
(function (global) {
  'use strict';

  var BASE = ''; // 同源

  // ---- 普通 JSON 请求，返回契约中的 data，失败抛出 error ----
  async function request(path, options) {
    var res = await fetch(BASE + path, options);
    var body;
    try {
      body = await res.json();
    } catch (e) {
      throw new Error('响应解析失败 (HTTP ' + res.status + ')');
    }
    if (!body || body.success !== true) {
      throw new Error((body && body.error) || ('请求失败 (HTTP ' + res.status + ')'));
    }
    return body.data;
  }

  function getConfig() {
    return request('/api/config', { method: 'GET' });
  }

  function saveConfig(cfg) {
    return request('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg)
    });
  }

  function testLlm(payload) {
    return request('/api/test/llm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  }

  function testAmap(payload) {
    return request('/api/test/amap', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  }

  function testTicket(payload) {
    return request('/api/test/ticket', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  }

  function testHotel(payload) {
    return request('/api/test/hotel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  }

  function queryTickets(payload) {
    return request('/api/ticket/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  }

  function queryHotels(payload) {
    return request('/api/hotel/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  }

  /**
   * SSE 流式请求。
   * @param {string} path
   * @param {object} payload  请求体
   * @param {object} handlers { onEvent(evt), onError(msg), onDone() }
   * @param {AbortSignal} [signal]
   */
  async function stream(path, payload, handlers, signal) {
    handlers = handlers || {};
    var res;
    try {
      res = await fetch(BASE + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: signal
      });
    } catch (e) {
      if (e && e.name === 'AbortError') return;
      handlers.onError && handlers.onError('网络请求失败：' + e.message);
      return;
    }

    if (!res.ok || !res.body) {
      // 尝试解析统一错误结构
      var msg = '请求失败 (HTTP ' + res.status + ')';
      try {
        var errBody = await res.json();
        if (errBody && errBody.error) msg = errBody.error;
      } catch (_) {}
      handlers.onError && handlers.onError(msg);
      return;
    }

    var reader = res.body.getReader();
    var decoder = new TextDecoder('utf-8');
    var buffer = '';

    function dispatch(rawEvent) {
      // 去掉每一行的 "data: " 前缀后拼接（SSE 单事件可能多行 data）
      var dataLines = rawEvent
        .split('\n')
        .map(function (l) { return l.replace(/^data:\s?/, ''); })
        .filter(function (l) { return l.trim() !== ''; });
      if (dataLines.length === 0) return;
      var jsonStr = dataLines.join('\n');
      var evt;
      try {
        evt = JSON.parse(jsonStr);
      } catch (e) {
        return; // 忽略无法解析的片段
      }
      if (evt && evt.type === 'error') {
        handlers.onError && handlers.onError(evt.message || '发生未知错误');
        return;
      }
      handlers.onEvent && handlers.onEvent(evt);
    }

    try {
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });

        // 按空行分割事件；保留最后一段可能不完整的缓冲
        var parts = buffer.split(/\n\n/);
        buffer = parts.pop();
        for (var k = 0; k < parts.length; k++) {
          if (parts[k].trim() !== '') dispatch(parts[k]);
        }
      }
      // 处理结尾残留
      if (buffer.trim() !== '') dispatch(buffer);
    } catch (e) {
      if (e && e.name === 'AbortError') return;
      handlers.onError && handlers.onError('数据流中断：' + e.message);
      return;
    }

    handlers.onDone && handlers.onDone();
  }

  global.API = {
    getConfig: getConfig,
    saveConfig: saveConfig,
    testLlm: testLlm,
    testAmap: testAmap,
    testTicket: testTicket,
    testHotel: testHotel,
    queryTickets: queryTickets,
    queryHotels: queryHotels,
    stream: stream
  };
})(window);
