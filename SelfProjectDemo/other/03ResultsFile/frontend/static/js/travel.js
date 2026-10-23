/* ============================================================
   旅游模式：收集表单 → POST /api/travel/plan (SSE) → 渲染 Markdown
   事件：tool / content / done / error
   ============================================================ */
(function (global) {
  'use strict';

  var els = {};
  var selectedInterests = [];
  var currentMarkdown = '';
  var streaming = false;

  function $(id) { return document.getElementById(id); }

  function setBtnLoading(loading) {
    els.btnGenerate.classList.toggle('is-loading', loading);
    els.btnGenerate.disabled = loading;
    els.btnGenerate.querySelector('.btn-label').textContent = loading ? '生成中…' : '生成行程计划';
  }

  function showTool(text) {
    els.toolText.textContent = text;
    els.toolIndicator.hidden = false;
  }
  function hideTool() { els.toolIndicator.hidden = true; }

  function toolLabel(name) {
    var map = {
      maps_weather: '天气', maps_geo: '地理编码', maps_regeocode: '逆地理编码',
      maps_direction_driving: '驾车路线', maps_direction_walking: '步行路线',
      maps_direction_bicycling: '骑行路线', maps_direction_transit_integrated: '公交路线',
      maps_text_search: 'POI 搜索', maps_around_search: '周边搜索',
      maps_distance: '距离测量', maps_search_detail: 'POI 详情', maps_ip_location: 'IP 定位',
      'get-tickets': '12306 车票'
    };
    var raw = String(name || '').replace(/^[a-z]+__/, '');
    return map[raw] || map[name] || name;
  }

  function renderMarkdown(withCursor) {
    els.empty.hidden = true;
    els.output.hidden = false;
    var html = MiniMarkdown.render(currentMarkdown);
    if (withCursor) html += '<span class="stream-cursor"></span>';
    els.output.innerHTML = html;
  }

  function resetOutput() {
    currentMarkdown = '';
    els.output.innerHTML = '';
    els.output.hidden = true;
    els.empty.hidden = false;
    els.btnCopy.disabled = true;
    els.btnDownload.disabled = true;
  }

  function generate() {
    if (streaming) return;

    var origin = els.origin.value.trim();
    var dest = els.dest.value.trim();
    if (!origin || !dest) {
      global.UI.toast('请填写出发地和目的地', 'err');
      return;
    }

    var payload = {
      origin: origin,
      destination: dest,
      days: parseInt(els.days.value, 10) || 1,
      people: parseInt(els.people.value, 10) || 1,
      interests: selectedInterests.slice(),
      transport: els.transport.value,
      extra: els.extra.value.trim(),
      start_date: els.startDate.value,
      include_refs: els.includeRefs.checked
    };

    streaming = true;
    setBtnLoading(true);
    resetOutput();
    hideTool();

    API.stream('/api/travel/plan', payload, {
      onEvent: function (evt) {
        if (!evt || !evt.type) return;
        if (evt.type === 'tool') {
          showTool('🔧 正在查询' + toolLabel(evt.tool) + '…');
        } else if (evt.type === 'content') {
          hideTool();
          currentMarkdown += (evt.delta || '');
          renderMarkdown(true);
        } else if (evt.type === 'done') {
          hideTool();
          if (typeof evt.markdown === 'string' && evt.markdown) {
            currentMarkdown = evt.markdown;
          }
          renderMarkdown(false);
          els.btnCopy.disabled = false;
          els.btnDownload.disabled = false;
        }
      },
      onError: function (msg) {
        hideTool();
        streaming = false;
        setBtnLoading(false);
        if (!currentMarkdown) {
          els.output.hidden = true;
          els.empty.hidden = false;
        } else {
          renderMarkdown(false);
        }
        global.UI.toast('生成失败：' + msg, 'err');
      },
      onDone: function () {
        hideTool();
        streaming = false;
        setBtnLoading(false);
        renderMarkdown(false);
        if (currentMarkdown) {
          els.btnCopy.disabled = false;
          els.btnDownload.disabled = false;
        }
      }
    });
  }

  function copyMd() {
    if (!currentMarkdown) return;
    navigator.clipboard.writeText(currentMarkdown).then(function () {
      global.UI.toast('已复制 Markdown', 'ok');
    }, function () {
      global.UI.toast('复制失败，请手动选择', 'err');
    });
  }

  function downloadMd() {
    if (!currentMarkdown) return;
    var blob = new Blob([currentMarkdown], { type: 'text/markdown;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    var name = (els.dest.value.trim() || '行程计划').replace(/[\\/:*?"<>|]/g, '');
    a.href = url;
    a.download = name + '_行程计划.md';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function init() {
    els = {
      origin: $('fOrigin'), dest: $('fDest'), days: $('fDays'), people: $('fPeople'),
      transport: $('fTransport'), extra: $('fExtra'),
      startDate: $('fStartDate'), includeRefs: $('fIncludeRefs'),
      chips: $('interestChips'),
      btnGenerate: $('btnGeneratePlan'),
      toolIndicator: $('toolIndicator'), toolText: $('toolIndicatorText'),
      empty: $('planEmpty'), output: $('planOutput'),
      btnCopy: $('btnCopyMd'), btnDownload: $('btnDownloadMd')
    };

    // 默认出发日期为明天，便于直接生成含车票/酒店的行程
    if (els.startDate && !els.startDate.value) {
      var d = new Date();
      d.setDate(d.getDate() + 1);
      var mm = d.getMonth() + 1;
      var dd = d.getDate();
      els.startDate.value = d.getFullYear() + '-' +
        (mm < 10 ? '0' + mm : mm) + '-' +
        (dd < 10 ? '0' + dd : dd);
    }

    // 兴趣多选 chips
    els.chips.addEventListener('click', function (e) {
      var chip = e.target.closest('.chip');
      if (!chip) return;
      var val = chip.dataset.value;
      var idx = selectedInterests.indexOf(val);
      if (idx >= 0) {
        selectedInterests.splice(idx, 1);
        chip.classList.remove('is-selected');
        chip.setAttribute('aria-pressed', 'false');
      } else {
        selectedInterests.push(val);
        chip.classList.add('is-selected');
        chip.setAttribute('aria-pressed', 'true');
      }
    });

    els.btnGenerate.addEventListener('click', generate);
    els.btnCopy.addEventListener('click', copyMd);
    els.btnDownload.addEventListener('click', downloadMd);
  }

  global.TravelMode = { init: init };
})(window);
