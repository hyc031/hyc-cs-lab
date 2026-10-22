/* ============================================================
   配置面板逻辑：GET 回填 / POST 保存 / 连接测试
   ============================================================ */
(function (global) {
  'use strict';

  var els = {};

  function $(id) { return document.getElementById(id); }

  function setPill(pill, state, text) {
    pill.className = 'pill pill-' + state;
    pill.textContent = text;
  }

  function setBtnLoading(btn, loading) {
    if (!btn) return;
    btn.classList.toggle('is-loading', loading);
    btn.disabled = loading;
  }

  function collectLlm() {
    return {
      base_url: els.llmBase.value.trim(),
      api_key: els.llmKey.value.trim(),
      model: els.llmModel.value.trim()
    };
  }

  function collectAmap() {
    return {
      sse_url: els.amapUrl.value.trim(),
      api_key: els.amapKey.value.trim()
    };
  }

  // ---- 打开 / 关闭 ----
  function open() { els.overlay.hidden = false; }
  function close() { els.overlay.hidden = true; }

  // ---- 回填 ----
  async function prefill() {
    try {
      var data = await API.getConfig();
      var llm = (data && data.llm) || {};
      var amap = (data && data.amap) || {};
      els.llmBase.value = llm.base_url || '';
      els.llmKey.value = llm.api_key || '';
      els.llmModel.value = llm.model || '';
      els.amapUrl.value = amap.sse_url || '';
      els.amapKey.value = amap.api_key || '';
    } catch (e) {
      // 首次无配置时静默
      console.warn('加载配置失败：', e.message);
    }
  }

  // ---- 保存 ----
  async function save() {
    setBtnLoading(els.btnSave, true);
    els.msg.textContent = '';
    try {
      await API.saveConfig({ llm: collectLlm(), amap: collectAmap() });
      global.UI.toast('配置已保存', 'ok');
      els.msg.textContent = '已保存 ✓';
    } catch (e) {
      global.UI.toast('保存失败：' + e.message, 'err');
      els.msg.textContent = '保存失败：' + e.message;
    } finally {
      setBtnLoading(els.btnSave, false);
    }
  }

  // ---- 测试 LLM ----
  async function testLlm() {
    setBtnLoading(els.btnTestLlm, true);
    setPill(els.pillLlm, 'testing', '测试中…');
    try {
      var d = await API.testLlm(collectLlm());
      setPill(els.pillLlm, 'ok', '成功 · ' + (d.latency_ms != null ? d.latency_ms + 'ms' : '已连接'));
      els.msg.textContent = (d.message || '连接成功') + (d.model ? ' · ' + d.model : '');
    } catch (e) {
      setPill(els.pillLlm, 'err', '失败');
      els.msg.textContent = 'LLM：' + e.message;
    } finally {
      setBtnLoading(els.btnTestLlm, false);
    }
  }

  // ---- 测试高德 ----
  async function testAmap() {
    setBtnLoading(els.btnTestAmap, true);
    setPill(els.pillAmap, 'testing', '测试中…');
    try {
      var d = await API.testAmap(collectAmap());
      var count = d.tool_count != null ? d.tool_count : (d.tools ? d.tools.length : 0);
      setPill(els.pillAmap, 'ok', '成功 · ' + count + ' 个工具');
      els.msg.textContent = (d.message || '连接成功') +
        (d.tools && d.tools.length ? ' · ' + d.tools.slice(0, 5).join(', ') +
          (d.tools.length > 5 ? ' …' : '') : '');
    } catch (e) {
      setPill(els.pillAmap, 'err', '失败');
      els.msg.textContent = '高德：' + e.message;
    } finally {
      setBtnLoading(els.btnTestAmap, false);
    }
  }

  function init() {
    els = {
      overlay: $('configOverlay'),
      llmBase: $('cfgLlmBase'), llmKey: $('cfgLlmKey'), llmModel: $('cfgLlmModel'),
      amapUrl: $('cfgAmapUrl'), amapKey: $('cfgAmapKey'),
      pillLlm: $('pillLlm'), pillAmap: $('pillAmap'),
      btnSave: $('btnSaveConfig'), btnTestLlm: $('btnTestLlm'), btnTestAmap: $('btnTestAmap'),
      msg: $('configMsg')
    };

    $('btnSettings').addEventListener('click', open);
    $('btnCloseConfig').addEventListener('click', close);
    els.overlay.addEventListener('click', function (e) {
      if (e.target === els.overlay) close();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !els.overlay.hidden) close();
    });

    els.btnSave.addEventListener('click', save);
    els.btnTestLlm.addEventListener('click', testLlm);
    els.btnTestAmap.addEventListener('click', testAmap);

    prefill();
  }

  global.ConfigPanel = { init: init, open: open };
})(window);
