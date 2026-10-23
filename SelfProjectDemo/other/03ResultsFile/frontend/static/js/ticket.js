/* ============================================================
   车票查询模式：POST /api/ticket/query（JSON）→ 渲染车次表格
   数据来自 12306 MCP；解析失败时仍展示原始返回
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
    els.btn.querySelector('.btn-label').textContent = on ? '查询中…' : '查询车票';
  }

  function showEmpty(title, desc) {
    els.empty.hidden = false;
    els.tableWrap.hidden = true;
    var t = els.empty.querySelector('.empty-title');
    var d = els.empty.querySelector('.empty-desc');
    if (t) t.textContent = title;
    if (d) d.textContent = desc;
  }

  function seatNode(seat) {
    var line = document.createElement('div');
    line.className = 'seat-line ' + (seat.available ? 'is-ok' : 'is-none');

    var name = document.createElement('span');
    name.className = 'seat-name';
    name.textContent = seat.name || '席别';

    var status = document.createElement('span');
    status.className = 'seat-status';
    status.textContent = seat.status || '';

    line.appendChild(name);
    line.appendChild(status);

    if (seat.price != null) {
      var price = document.createElement('span');
      price.className = 'seat-price';
      price.textContent = '¥' + seat.price;
      line.appendChild(price);
    }
    return line;
  }

  function render(data) {
    var items = (data && data.items) || [];
    var raw = (data && data.raw) || '';

    els.raw.textContent = raw;
    els.rawWrap.hidden = !raw;

    if (!items.length) {
      els.summary.textContent = (data.date || '') +
        ' · ' + (data.from_station || '') + ' → ' + (data.to_station || '');
      showEmpty(
        '没有解析到车次',
        raw ? '上游返回了内容但格式无法解析，请展开下方原始数据查看' : '换个日期或城市再试试'
      );
      return;
    }

    els.summary.textContent =
      (data.date || '') + ' · ' +
      (data.from_station || '') + ' → ' + (data.to_station || '') +
      ' · 共 ' + items.length + ' 趟车次';

    els.rows.textContent = '';
    items.forEach(function (item) {
      var tr = document.createElement('tr');

      var tdTrain = document.createElement('td');
      tdTrain.className = 'train-code';
      tdTrain.textContent = item.train || '';

      var tdRoute = document.createElement('td');
      tdRoute.textContent = (item.from_station || '') + ' → ' + (item.to_station || '');

      var tdTime = document.createElement('td');
      tdTime.className = 'train-time';
      tdTime.textContent = (item.depart || '') + ' - ' + (item.arrive || '');

      var tdDuration = document.createElement('td');
      tdDuration.textContent = item.duration || '';

      var tdSeat = document.createElement('td');
      var seats = item.seats || [];
      if (!seats.length) {
        tdSeat.textContent = '—';
      } else {
        seats.forEach(function (s) { tdSeat.appendChild(seatNode(s)); });
      }

      tr.appendChild(tdTrain);
      tr.appendChild(tdRoute);
      tr.appendChild(tdTime);
      tr.appendChild(tdDuration);
      tr.appendChild(tdSeat);
      els.rows.appendChild(tr);
    });

    els.empty.hidden = true;
    els.tableWrap.hidden = false;
  }

  async function query() {
    if (loading) return;
    var from = els.from.value.trim();
    var to = els.to.value.trim();
    var date = els.date.value;
    if (!from || !to) {
      global.UI.toast('请填写出发城市和到达城市', 'err');
      return;
    }
    if (!date) {
      global.UI.toast('请选择出发日期', 'err');
      return;
    }

    setLoading(true);
    els.summary.textContent = '正在查询 ' + from + ' → ' + to + '…';
    try {
      var data = await API.queryTickets({
        date: date,
        from_station: from,
        to_station: to,
        train_flags: els.flags.value
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
      from: $('tFrom'), to: $('tTo'), date: $('tDate'), flags: $('tFlags'),
      btn: $('btnQueryTickets'),
      summary: $('ticketSummary'), empty: $('ticketEmpty'),
      tableWrap: $('ticketTableWrap'), rows: $('ticketRows'),
      rawWrap: $('ticketRawWrap'), raw: $('ticketRaw')
    };

    if (!els.date.value) els.date.value = localDate(1);
    els.btn.addEventListener('click', query);
    [els.from, els.to, els.date, els.flags].forEach(function (el) {
      el.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); query(); }
      });
    });
  }

  global.TicketMode = { init: init };
})(window);
