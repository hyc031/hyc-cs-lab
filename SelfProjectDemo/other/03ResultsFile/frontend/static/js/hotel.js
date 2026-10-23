/* ============================================================
   酒店查询模式：POST /api/hotel/query（JSON）→ 渲染酒店列表
   后端优先酒店 MCP，失败时回退到高德 POI 搜索
   ============================================================ */
(function (global) {
  'use strict';

  var els = {};
  var loading = false;

  function $(id) { return document.getElementById(id); }

  function pad(n) { return n < 10 ? '0' + n : '' + n; }

  function localDate(offset) {
    var d = new Date();
    d.setDate(d.getDate() + (offset || 0));
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }

  function setLoading(on) {
    loading = on;
    els.btn.classList.toggle('is-loading', on);
    els.btn.disabled = on;
    els.btn.querySelector('.btn-label').textContent = on ? '查询中…' : '查询酒店';
  }

  function showEmpty(title, desc) {
    els.empty.hidden = false;
    els.list.hidden = true;
    var t = els.empty.querySelector('.empty-title');
    var d = els.empty.querySelector('.empty-desc');
    if (t) t.textContent = title;
    if (d) d.textContent = desc;
  }

  function hotelCard(item) {
    var card = document.createElement('article');
    card.className = 'hotel-item';

    if (item.photo) {
      var img = document.createElement('img');
      img.className = 'hotel-photo';
      img.src = item.photo;
      img.alt = item.name || '酒店图片';
      img.loading = 'lazy';
      img.referrerPolicy = 'no-referrer';
      img.addEventListener('error', function () { img.remove(); });
      card.appendChild(img);
    }

    var body = document.createElement('div');
    body.className = 'hotel-body';

    var name = document.createElement('h3');
    name.className = 'hotel-name';
    name.textContent = item.name || '未命名酒店';

    var address = document.createElement('p');
    address.className = 'hotel-address';
    address.textContent = item.address || '地址未提供';

    body.appendChild(name);
    body.appendChild(address);

    if (item.typecode) {
      var tag = document.createElement('span');
      tag.className = 'hotel-tag';
      tag.textContent = 'POI ' + item.typecode;
      body.appendChild(tag);
    }

    card.appendChild(body);
    return card;
  }

  function render(data) {
    var items = (data && data.items) || [];
    var raw = (data && data.raw) || '';
    var source = data && data.source;

    els.raw.textContent = raw;
    els.rawWrap.hidden = !raw;

    var sourceText = source === 'amap'
      ? '高德 POI 回退'
      : (source === 'hotel-mcp' ? '酒店 MCP' : '未知来源');

    if (!items.length) {
      els.summary.textContent = (data.city || '') + ' · ' + sourceText;
      showEmpty(
        '没有解析到酒店',
        raw ? '上游返回了内容但格式无法解析，请展开下方原始数据查看' : '换个城市或关键词再试试'
      );
      return;
    }

    els.summary.textContent =
      (data.city || '') + ' · ' + sourceText + ' · 共 ' + items.length + ' 家' +
      (data.nights ? ' · ' + data.nights + ' 晚' : '') +
      (source === 'amap' ? '（酒店 MCP 不可用，已自动回退）' : '');

    els.list.textContent = '';
    items.forEach(function (item) { els.list.appendChild(hotelCard(item)); });

    els.empty.hidden = true;
    els.list.hidden = false;
  }

  async function query() {
    if (loading) return;
    var city = els.city.value.trim();
    if (!city) {
      global.UI.toast('请填写城市', 'err');
      return;
    }
    var checkin = els.checkin.value;
    var checkout = els.checkout.value;
    if (checkin && checkout && checkout <= checkin) {
      global.UI.toast('离店日期需要晚于入住日期', 'err');
      return;
    }

    setLoading(true);
    els.summary.textContent = '正在查询 ' + city + ' 的酒店…';
    try {
      var data = await API.queryHotels({
        city: city,
        keyword: els.keyword.value.trim(),
        checkin: checkin,
        checkout: checkout
      });
      render(data || {});
      global.UI.toast('查询完成', 'ok');
    } catch (e) {
      showEmpty('查询失败', e.message);
      global.UI.toast('查询失败：' + e.message, 'err');
    } finally {
      setLoading(false);
    }
  }

  function init() {
    els = {
      city: $('hCity'), keyword: $('hKeyword'),
      checkin: $('hCheckin'), checkout: $('hCheckout'),
      btn: $('btnQueryHotels'),
      summary: $('hotelSummary'), empty: $('hotelEmpty'),
      list: $('hotelList'),
      rawWrap: $('hotelRawWrap'), raw: $('hotelRaw')
    };

    if (!els.checkin.value) els.checkin.value = localDate(1);
    if (!els.checkout.value) els.checkout.value = localDate(2);

    els.btn.addEventListener('click', query);
    [els.city, els.keyword, els.checkin, els.checkout].forEach(function (el) {
      el.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); query(); }
      });
    });
  }

  global.HotelMode = { init: init };
})(window);
