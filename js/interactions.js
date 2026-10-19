/*!
 * interactions.js — 筛选规则与车次详情（阶段7）
 * 版本：1.0.0
 *
 * 只做纯逻辑与详情渲染：
 *   - 不修改源 JSON（所有函数返回新数组/新 DOM）
 *   - 不持有播放时间，不暂停/重置播放器
 *   - 不复制第二套筛选：两个视图拿同一个 ids 数组
 *
 * API
 *   Interactions.typeOptions(trains)        -> [{value,label,count}]
 *   Interactions.stationOptions(trains)     -> [{value,label,stops,passes}]
 *   Interactions.applyFilters(trains, f)    -> trains[]
 *   Interactions.filtersSummary(f)          -> "上行 · 高铁 · 在阳泉北停站"
 *   Interactions.renderDetail(el, train, data)
 *   Interactions.renderEmpty(el, title, hint)
 *   Interactions.formatAbs(absMinute)       -> "10:05" / "次日 01:20"
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.Interactions = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var VERSION = '1.0.0';
  var DIRECTION_LABEL = { up: '上行', down: '下行', unknown: '方向未知' };
  var STOP_KIND_LABEL = { origin: '始发', terminal: '终到', stop: '停站', pass: '通过' };

  function formatAbs(absMinute) {
    if (absMinute === null || absMinute === undefined) return '未知';
    var m = Math.round(absMinute);
    var day = Math.floor(m / 1440);
    var rem = ((m % 1440) + 1440) % 1440;
    var hh = Math.floor(rem / 60), mm = rem % 60;
    var t = (hh < 10 ? '0' : '') + hh + ':' + (mm < 10 ? '0' : '') + mm;
    return day > 0 ? '次日 ' + t : t;
  }

  /** 车型选项：只从数据里取，不硬编码。 */
  function typeOptions(trains) {
    var map = {};
    (trains || []).forEach(function (t) {
      if (!t.train_type) return;
      map[t.train_type] = (map[t.train_type] || 0) + 1;
    });
    return Object.keys(map).sort(function (a, b) { return map[b] - map[a]; })
      .map(function (k) { return { value: k, label: k, count: map[k] }; });
  }

  /** 车站选项：只列本批确实有停站记录的车站，并给出停站/通过车数。 */
  function stationOptions(trains) {
    var map = {};
    (trains || []).forEach(function (t) {
      (t.stops || []).forEach(function (s) {
        if (!map[s.station]) map[s.station] = { value: s.station, label: s.station, stops: 0, passes: 0 };
        if (s.stop_kind === 'pass' || s.is_stop === false) map[s.station].passes += 1;
        else map[s.station].stops += 1;
      });
    });
    return Object.keys(map).sort(function (a, b) {
      var d = map[b].stops - map[a].stops;
      return d !== 0 ? d : a.localeCompare(b);
    }).map(function (k) { return map[k]; });
  }

  function matchDirection(train, dir) {
    return dir === 'all' || !dir || train.direction === dir;
  }

  function matchType(train, type) {
    return type === 'all' || !type || train.train_type === type;
  }

  function matchStation(train, station, mode) {
    if (!station || station === 'all') return true;
    return (train.stops || []).some(function (s) {
      if (s.station !== station) return false;
      if (mode === 'pass') return s.stop_kind === 'pass' || s.is_stop === false;
      if (mode === 'either') return true;
      return s.stop_kind !== 'pass' && s.is_stop !== false;   // 默认：停站
    });
  }

  /** 纯函数：不改入参，不改 train。 */
  function applyFilters(trains, filters) {
    var f = filters || {};
    return (trains || []).filter(function (t) {
      return matchDirection(t, f.direction) && matchType(t, f.trainType) &&
        matchStation(t, f.station, f.stationMode);
    });
  }

  function filtersSummary(f) {
    var parts = [];
    parts.push(!f.direction || f.direction === 'all' ? '全部方向' : DIRECTION_LABEL[f.direction]);
    parts.push(!f.trainType || f.trainType === 'all' ? '全部车型' : f.trainType);
    if (f.station && f.station !== 'all') {
      var mode = f.stationMode === 'pass' ? '通过' : f.stationMode === 'either' ? '经停或通过' : '停站';
      parts.push('在' + f.station + mode);
    } else {
      parts.push('全部车站');
    }
    return parts.join(' · ');
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function missingText(stop, key) {
    if (key === 'arr' && stop.arr_time === null && stop.stop_kind === 'origin') return '始发';
    if (key === 'dep' && stop.dep_time === null && stop.stop_kind === 'terminal') return '终到';
    return '未知';
  }

  function renderEmpty(container, title, hint) {
    container.innerHTML = '';
    var box = el('div', 'detail-empty');
    box.appendChild(el('strong', null, title));
    if (hint) box.appendChild(el('div', 'detail-empty-hint', hint));
    container.appendChild(box);
  }

  /**
   * 车次详情：站序/到达/出发/日期/站型/备注。
   * 缺失值一律显示「未知」或规则性说明，绝不显示 00:00 / 0。
   */
  function renderDetail(container, train, data) {
    container.innerHTML = '';
    if (!train) { renderEmpty(container, '未选择车次', '点击任一视图中的车次查看时刻表'); return; }

    var head = el('div', 'detail-head');
    var title = el('div', 'detail-title');
    title.appendChild(el('strong', null, train.train_no));
    title.appendChild(el('span', 'detail-sub',
      (DIRECTION_LABEL[train.direction] || '方向未知') + ' · ' + train.train_type));
    head.appendChild(title);

    var statusText = train.validation.status === 'validated' ? '已校验'
      : train.validation.status === 'validated_with_notes' ? '已校验（带待核）' : '待复核';
    var badge = el('span', 'detail-badge' + (train.validation.usable_for_frontend ? '' : ' detail-badge--warn'), statusText);
    head.appendChild(badge);
    container.appendChild(head);

    var facts = el('dl', 'detail-facts');
    function fact(k, v) {
      facts.appendChild(el('dt', null, k));
      facts.appendChild(el('dd', null, v));
    }
    fact('始发 → 终到', train.origin + ' → ' + train.terminal);
    fact('停站数', String(train.station_count));
    fact('全程时长', train.duration_minutes === null ? '不可用（跨日未定）' : train.duration_minutes + ' 分钟');
    fact('跨日', train.has_day_offset ? '有（含次日时刻）' : '无');
    fact('数据来源', train.source_refs && train.source_refs.length
      ? train.source_refs[0].url : '见 provenance（采集页未记 URL）');
    container.appendChild(facts);

    var warnings = (data && data.warnings ? data.warnings : []).filter(function (w) {
      if (w.train_id === train.train_id) return true;
      if (!w.train_no) return false;
      return w.train_no.split(',').map(function (x) { return x.trim(); }).indexOf(train.train_no) !== -1;
    });
    if (warnings.length) {
      var wbox = el('div', 'detail-warnings');
      wbox.appendChild(el('div', 'detail-section-title', '待核 / 冲突（' + warnings.length + '）'));
      var ul = el('ul');
      warnings.forEach(function (w) {
        var li = el('li');
        li.appendChild(el('code', null, w.code));
        li.appendChild(document.createTextNode(' ' + w.message));
        ul.appendChild(li);
      });
      wbox.appendChild(ul);
      container.appendChild(wbox);
    }

    var tableWrap = el('div', 'detail-table-wrap');
    var table = el('table', 'detail-table');
    var thead = el('thead');
    var hr = el('tr');
    ['站序', '车站', '到达', '出发', '日期', '站型'].forEach(function (h) { hr.appendChild(el('th', null, h)); });
    thead.appendChild(hr);
    table.appendChild(thead);

    var tbody = el('tbody');
    (train.stops || []).forEach(function (s) {
      var tr = el('tr', s.stop_kind === 'pass' ? 'is-pass' : null);
      tr.appendChild(el('td', null, String(s.station_order)));
      var nameTd = el('td', 'station-cell');
      nameTd.textContent = s.station;
      if (s.remark) nameTd.title = s.remark;
      tr.appendChild(nameTd);

      var arrTd = el('td', null, s.arr_time === null ? missingText(s, 'arr') : s.arr_time);
      if (s.arr_time === null) arrTd.className = 'is-missing';
      tr.appendChild(arrTd);

      var depTd = el('td', null, s.dep_time === null ? missingText(s, 'dep') : s.dep_time);
      if (s.dep_time === null) depTd.className = 'is-missing';
      tr.appendChild(depTd);

      tr.appendChild(el('td', null, s.day_offset > 0 ? '+' + s.day_offset + ' 天' : '当日'));
      tr.appendChild(el('td', null, STOP_KIND_LABEL[s.stop_kind] || s.stop_kind));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    container.appendChild(tableWrap);

    if (train.remarks && train.remarks.length) {
      var rbox = el('div', 'detail-remarks');
      rbox.appendChild(el('div', 'detail-section-title', '备注'));
      train.remarks.forEach(function (r) { rbox.appendChild(el('p', null, r)); });
      container.appendChild(rbox);
    }
  }

  return {
    version: VERSION,
    typeOptions: typeOptions,
    stationOptions: stationOptions,
    applyFilters: applyFilters,
    filtersSummary: filtersSummary,
    renderDetail: renderDetail,
    renderEmpty: renderEmpty,
    formatAbs: formatAbs,
    DIRECTION_LABEL: DIRECTION_LABEL,
    STOP_KIND_LABEL: STOP_KIND_LABEL
  };
});
