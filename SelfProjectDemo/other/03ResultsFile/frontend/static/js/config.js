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

  function collectTicket() {
    return {
      sse_url: els.ticketUrl.value.trim(),
      api_key: els.ticketKey.value.trim()
    };
  }

  function collectHotel() {
    return {
      sse_url: els.hotelUrl.value.trim(),
      api_key: els.hotelKey.value.trim()
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
      var ticket = (data && data.ticket) || {};
      var hotel = (data && data.hotel) || {};
      els.llmBase.value = llm.base_url || '';
      els.llmKey.value = llm.api_key || '';
      els.llmModel.value = llm.model || '';
      els.amapUrl.value = amap.sse_url || '';
      els.amapKey.value = amap.api_key || '';
      els.ticketUrl.value = ticket.sse_url || '';
      els.ticketKey.value = ticket.api_key || '';
      els.hotelUrl.value = hotel.sse_url || '';
      els.hotelKey.value = hotel.api_key || '';
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
      await API.saveConfig({
        llm: collectLlm(),
        amap: collectAmap(),
        ticket: collectTicket(),
        hotel: collectHotel()
      });
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

  // ---- 测试 12306 ----
  async function testTicket() {
    setBtnLoading(els.btnTestTicket, true);
    setPill(els.pillTicket, 'testing', '测试中…');
    try {
      var d = await API.testTicket(collectTicket());
      var count = d.tool_count != null ? d.tool_count : (d.tools ? d.tools.length : 0);
      setPill(els.pillTicket, 'ok', '成功 · ' + count + ' 个工具');
      els.msg.textContent = '12306：' + (d.message || '连接成功') +
        (d.tools && d.tools.length ? ' · ' + d.tools.slice(0, 5).join(', ') +
          (d.tools.length > 5 ? ' …' : '') : '');
    } catch (e) {
      setPill(els.pillTicket, 'err', '失败');
      els.msg.textContent = '12306：' + e.message;
    } finally {
      setBtnLoading(els.btnTestTicket, false);
    }
  }

  // ---- 测试酒店 ----
  async function testHotel() {
    setBtnLoading(els.btnTestHotel, true);
    setPill(els.pillHotel, 'testing', '测试中…');
    try {
      var d = await API.testHotel(collectHotel());
      var count = d.tool_count != null ? d.tool_count : (d.tools ? d.tools.length : 0);
      setPill(els.pillHotel, 'ok', '成功 · ' + count + ' 个工具');
      els.msg.textContent = '酒店：' + (d.message || '连接成功') +
        (d.tools && d.tools.length ? ' · ' + d.tools.slice(0, 5).join(', ') +
          (d.tools.length > 5 ? ' …' : '') : '');
    } catch (e) {
      setPill(els.pillHotel, 'err', '失败');
      els.msg.textContent = '酒店：' + e.message;
    } finally {
      setBtnLoading(els.btnTestHotel, false);
    }
  }

  function init() {
    els = {
      overlay: $('configOverlay'),
      llmBase: $('cfgLlmBase'), llmKey: $('cfgLlmKey'), llmModel: $('cfgLlmModel'),
      amapUrl: $('cfgAmapUrl'), amapKey: $('cfgAmapKey'),
      ticketUrl: $('cfgTicketUrl'), ticketKey: $('cfgTicketKey'),
      hotelUrl: $('cfgHotelUrl'), hotelKey: $('cfgHotelKey'),
      pillLlm: $('pillLlm'), pillAmap: $('pillAmap'),
      pillTicket: $('pillTicket'), pillHotel: $('pillHotel'),
      btnSave: $('btnSaveConfig'), btnTestLlm: $('btnTestLlm'), btnTestAmap: $('btnTestAmap'),
      btnTestTicket: $('btnTestTicket'), btnTestHotel: $('btnTestHotel'),
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
    els.btnTestTicket.addEventListener('click', testTicket);
    els.btnTestHotel.addEventListener('click', testHotel);

    prefill();
  }

  global.ConfigPanel = { init: init, open: open };
})(window);
