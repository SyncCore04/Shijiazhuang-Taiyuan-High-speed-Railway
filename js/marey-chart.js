/*!
 * marey-chart.js — 石太客专 + 阳大铁路 Marey 运行图（阶段4）
 * 版本：1.0.0
 *
 * 契约：docs/data-contract.md v1.0.0（只读 data/processed/*.json，不解析 CSV）
 * 依赖：无（原生 SVG + DOM）
 *
 * 公开接口
 *   const chart = MareyChart.initMareyChart(container, data, options)
 *   chart.setCurrentTime(absMinute)        // 只移动时间竖线，不重建图元
 *   chart.setVisibleTrains([trainId...])   // null = 全部可见；支持 train_id 或 train_no
 *   chart.setSelectedTrain(trainId|null)   // 选中高亮（与线路图联动）
 *   chart.setDomain(minAbs, maxAbs)     // 缩放到时间窗口（重绘刻度，不重算数据）
 *   chart.setOption(patch) / chart.resize() / chart.destroy()
 *   container.addEventListener('trainselect', e => e.detail)  // {trainId, trainNo, direction, trainType}
 *
 * 纯函数（Node 可直接 require 做单测）
 *   MareyChart.buildAxis(stations, options)
 *   MareyChart.buildSeries(train, axis, options)
 *   MareyChart.computeDomain(coverage, options)
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.MareyChart = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var VERSION = '1.0.0';
  var SVG_NS = 'http://www.w3.org/2000/svg';

  var DEFAULTS = {
    height: 640,
    margin: { top: 46, right: 28, bottom: 46, left: 122 },
    domain: null,            // [minAbs, maxAbs]；null = 按 coverage 自动取整到整点
    fontScale: 1,            // 字号倍率（录制/大屏时可放大，不影响布局几何）
    showLegend: true,        // 顶部图例（上/下行线型 + 可绘统计）
    tickMinutes: 60,         // 竖网格间隔
    labelMinutes: 120,       // 刻度文字间隔
    rowMinGap: 34,
    showBlocked: false,      // 阻断车默认不画（abs_minute 不单调）
    dimOpacity: 0.12,        // 被 setVisibleTrains 隐藏时的透明度（不参与绘制）
    colors: {
      up: '#c0392b',
      down: '#1f6fb2',
      blocked: '#8a8f98',
      grid: '#e6e8eb',
      axisText: '#4a4f57',
      highlightRow: '#fff4e0',
      cursor: '#d9480f'
    },
    dash: { up: 'none', down: '7 4', blocked: '2 4' },
    ariaLabel: '石太客专与阳大铁路列车运行图'
  };

  // ---------------------------------------------------------------------
  // 纯函数层
  // ---------------------------------------------------------------------

  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  function formatMinute(absMinute, opts) {
    var m = Math.round(absMinute);
    var day = Math.floor(m / 1440);
    var rem = ((m % 1440) + 1440) % 1440;
    var hh = Math.floor(rem / 60);
    var mm = rem % 60;
    var text = pad2(hh) + ':' + pad2(mm);
    if (day <= 0) return text;
    if (opts && opts.long) return '次日' + text;
    return '+' + day + 'd ' + text;
  }

  /**
   * 纵轴：由 stations[].place 生成。
   * - 主线按 sequence 排序；运行图取“东在上、西在下”（sequence 降序）。
   * - 支线站按 branch_of 挂到父站：位于父站以北（y 更小）插在其上方，否则插在下方。
   * - 只保留有停站记录或需高亮的行；父站被过滤但有子站保留时，父站降级为 minor 行。
   */
  function buildAxis(stations, options) {
    var opts = options || {};
    var list = (stations || []).filter(function (s) { return s && s.place; }).map(function (s) {
      return {
        name: s.name,
        place: s.place,
        records: (s.stats && s.stats.stop_records) || 0,
        highlight: !!s.is_highlighted
      };
    });

    var childrenOf = {};
    list.forEach(function (n) {
      if (n.place.branch_of) (childrenOf[n.place.branch_of] = childrenOf[n.place.branch_of] || []).push(n);
    });
    Object.keys(childrenOf).forEach(function (k) {
      childrenOf[k].sort(function (a, b) { return (a.place.branch_order || 0) - (b.place.branch_order || 0); });
    });

    var directKeep = function (n) { return n.records > 0 || n.highlight || opts.keepEmpty === true; };

    var rows = [];
    function push(n, major) {
      rows.push({
        key: n.name, names: [n.name], label: n.name,
        line: n.place.line, sequence: n.place.sequence,
        branch: !!n.place.branch_of,
        link: n.place.link,
        highlight: n.highlight, major: major,
        x: n.place.x, y: n.place.y
      });
    }
    function emit(n) {
      // 父站即使没有停站记录（不进纵轴），其支线子站仍要按位置插入
      var kids = childrenOf[n.name] || [];
      var before = kids.filter(function (k) { return k.place.y < n.place.y; });
      var after = kids.filter(function (k) { return k.place.y >= n.place.y; });
      before.forEach(emit);
      if (directKeep(n)) push(n, true);
      after.forEach(emit);
    }

    list.filter(function (n) { return n.place.sequence !== null && !n.place.branch_of; })
      .sort(function (a, b) { return b.place.sequence - a.place.sequence; })   // 东 → 西
      .forEach(emit);

    // 兜底：父站不在数据里的支线站，按 y 追加，避免丢站
    var placed = {};
    rows.forEach(function (r) { placed[r.names[0]] = true; });
    list.filter(function (n) { return n.place.branch_of && !placed[n.name]; })
      .sort(function (a, b) { return a.place.y - b.place.y; })
      .forEach(function (n) { if (directKeep(n)) push(n, true); });

    var rowOfStation = {};
    rows.forEach(function (row, idx) {
      row.index = idx;
      row.names.forEach(function (nm) { rowOfStation[nm] = idx; });
    });

    return { rows: rows, rowOfStation: rowOfStation, slotOfStation: rowOfStation };
  }

  /** 时间域：默认按 coverage 取整到整点，保证不截断末班车。 */
  function computeDomain(coverage, options) {
    var opts = options || {};
    if (opts.domain && opts.domain.length === 2) {
      return [Number(opts.domain[0]), Number(opts.domain[1])];
    }
    var min = coverage && typeof coverage.abs_minute_min === 'number' ? coverage.abs_minute_min : 0;
    var max = coverage && typeof coverage.abs_minute_max === 'number' ? coverage.abs_minute_max : 1440;
    var step = opts.domainStep || 60;
    var d0 = Math.max(0, Math.floor(min / step) * step);
    var d1 = Math.ceil(max / step) * step;
    if (d1 <= d0) d1 = d0 + step;
    return [d0, d1];
  }

  /**
   * 单车折线：只取通道内站点；遇到未映射站/缺时刻则断线，不跨缺口连线。
   * 返回 { segments: [ [{x,y}...] ... ] }，x 为 abs_minute，y 为行号。
   */
  function buildSeries(train, axis, options) {
    var opts = options || {};
    var segments = [];
    var current = [];
    var skipped = [];        // 未映射的站
    var missing = [];        // 缺时刻的站
    var backwards = false;

    function flush() {
      if (current.length >= 1) segments.push(current);
      current = [];
    }

    (train.stops || []).forEach(function (stop) {
      var rowIdx = axis.rowOfStation[stop.station];
      if (rowIdx === undefined) {
        skipped.push(stop.station);
        flush();                       // 通道外/未映射：断开，不伪造连接
        return;
      }
      var arr = stop.abs_minute ? stop.abs_minute.arr : null;
      var dep = stop.abs_minute ? stop.abs_minute.dep : null;
      if (arr === null && dep === null) {
        missing.push(stop.station);
        flush();
        return;
      }
      var pts = [];
      if (arr !== null) pts.push({ x: arr, y: rowIdx, kind: 'arr' });
      // 始发站只有 dep；通过站 arr==dep，只留一个点
      if (dep !== null && dep !== arr) pts.push({ x: dep, y: rowIdx, kind: 'dep' });

      if (current.length && pts.length && pts[0].x < current[current.length - 1].x - 1e-6) {
        backwards = true;              // 记录异常，但仍按原值画，不修正
      }
      pts.forEach(function (p) { current.push(p); });
    });
    flush();

    return {
      trainId: train.train_id,
      trainNo: train.train_no,
      direction: train.direction,
      trainType: train.train_type,
      usable: !!(train.validation && train.validation.usable_for_frontend),
      status: train.validation ? train.validation.status : 'unknown',
      flags: (train.validation && train.validation.flags) || [],
      segments: segments,
      skippedStations: skipped,
      missingStations: missing,
      hasBackwards: backwards,
      pointCount: segments.reduce(function (n, s) { return n + s.length; }, 0)
    };
  }

  function pathData(segment, xScale, yOf) {
    return segment.map(function (p, i) {
      return (i === 0 ? 'M' : 'L') + xScale(p.x).toFixed(2) + ' ' + yOf(p.y).toFixed(2);
    }).join(' ');
  }

  // ---------------------------------------------------------------------
  // DOM 渲染层
  // ---------------------------------------------------------------------

  function el(name, attrs) {
    var node = document.createElementNS(SVG_NS, name);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (attrs[k] !== null && attrs[k] !== undefined) node.setAttribute(k, attrs[k]);
      });
    }
    return node;
  }

  var clipSeq = 0;

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function initMareyChart(container, data, options) {
    if (!container) throw new Error('initMareyChart: container 不能为空');
    if (!data || !data.trains || !data.meta) throw new Error('initMareyChart: data 不符合契约（缺 meta/trains）');

    var opts = Object.assign({}, DEFAULTS, options || {});
    opts.margin = Object.assign({}, DEFAULTS.margin, (options && options.margin) || {});
    opts.colors = Object.assign({}, DEFAULTS.colors, (options && options.colors) || {});
    opts.dash = Object.assign({}, DEFAULTS.dash, (options && options.dash) || {});
    var fontScale = Number(opts.fontScale) > 0 ? Number(opts.fontScale) : 1;
    function fs(n) { return n * fontScale; }

    var axis = buildAxis(data.stations, opts);
    var domain = computeDomain(data.meta.coverage, opts);
    var series = data.trains
      .map(function (t) { return buildSeries(t, axis, opts); })
      .filter(function (s) { return opts.showBlocked || s.usable; });

    var trainNodes = {};
    var state = {
      currentTime: null,
      visible: null,          // null=全部
      selected: null,
      width: 0,
      height: opts.height,
      destroyed: false
    };

    var root = document.createElement('div');
    root.className = 'mc-root';
    root.style.position = 'relative';
    container.appendChild(root);

    var svg, gGrid, gSeries, gCursor, cursorLine, cursorLabel, cursorBg, xScale, yOf, cursorText;

    function layout() {
      state.width = Math.max(480, container.clientWidth || 960);
      state.height = opts.height;
    }

    function draw() {
      clear(root);
      trainNodes = {};
      svg = el('svg', {
        'class': 'mc-svg',
        viewBox: '0 0 ' + state.width + ' ' + state.height,
        width: '100%',
        height: state.height,
        role: 'img',
        'aria-label': opts.ariaLabel,
        preserveAspectRatio: 'xMidYMid meet'
      });

      var m = opts.margin;
      var plotW = state.width - m.left - m.right;
      var plotH = state.height - m.top - m.bottom;
      var d0 = domain[0], d1 = domain[1];
      xScale = function (v) { return m.left + (v - d0) / (d1 - d0) * plotW; };
      var rowCount = Math.max(1, axis.rows.length);
      var gap = rowCount > 1 ? plotH / (rowCount - 1) : 0;
      yOf = function (idx) { return m.top + idx * gap; };

      // 次日区域淡底，配合“次日 00:00”分隔线，避免读者误读日期
      if (d1 > 1440) {
        svg.appendChild(el('rect', {
          x: xScale(Math.max(d0, 1440)), y: m.top - 6,
          width: Math.max(0, xScale(d1) - xScale(Math.max(d0, 1440))),
          height: plotH + 6, fill: '#f3f5f8', 'class': 'mc-nextday-band'
        }));
      }

      // 背景：阳泉北行高亮
      var gBg = el('g', { 'class': 'mc-rows' });
      axis.rows.forEach(function (row) {
        if (row.highlight) {
          gBg.appendChild(el('rect', {
            x: m.left, y: yOf(row.index) - Math.min(gap / 2, 22),
            width: plotW, height: Math.min(gap, 44),
            fill: opts.colors.highlightRow, 'class': 'mc-row-highlight'
          }));
        }
        gBg.appendChild(el('line', {
          x1: m.left, x2: m.left + plotW, y1: yOf(row.index), y2: yOf(row.index),
          stroke: opts.colors.grid, 'stroke-width': 1, 'class': 'mc-row-line'
        }));
      });
      svg.appendChild(gBg);

      // 纵轴标签
      var gLabels = el('g', { 'class': 'mc-station-axis' });
      axis.rows.forEach(function (row) {
        var t = el('text', {
          x: m.left - 10, y: yOf(row.index) + 4,
          'text-anchor': 'end',
          'font-size': row.highlight ? fs(13) : fs(12),
          'font-weight': row.highlight ? 700 : 400,
          fill: row.highlight ? '#a2410a' : opts.colors.axisText,
          'class': 'mc-station-label' + (row.highlight ? ' mc-station-label--highlight' : '')
        });
        t.textContent = row.label;
        gLabels.appendChild(t);
        if (row.branch) {
          var b = el('text', {
            x: m.left - 10, y: yOf(row.index) + 16,
            'text-anchor': 'end', 'font-size': fs(9), fill: '#9aa0a8', 'class': 'mc-branch-tag'
          });
          b.textContent = row.link === 'connecting' ? '联络线' : '阳大支线';
          gLabels.appendChild(b);
        }
      });
      svg.appendChild(gLabels);

      // 时间网格 + 刻度
      var gAxis = el('g', { 'class': 'mc-time-axis' });
      var pxPerMinute = plotW / Math.max(1, d1 - d0);
      var candidates = [10, 15, 30, 60, 120, 180, 240, 360, 720];
      var labelStep = candidates[candidates.length - 1];
      for (var ci = 0; ci < candidates.length; ci++) {
        if (candidates[ci] * pxPerMinute >= 64) { labelStep = candidates[ci]; break; }
      }
      var tick = Math.max(10, Math.min(opts.tickMinutes, Math.round(labelStep / 2)));
      var first = Math.ceil(d0 / tick) * tick;
      for (var t = first; t <= d1 + 1e-6; t += tick) {
        var x = xScale(t);
        var isDay = t % 1440 === 0;
        gAxis.appendChild(el('line', {
          x1: x, x2: x, y1: m.top - 6, y2: m.top + plotH,
          stroke: isDay ? '#c9ccd2' : opts.colors.grid,
          'stroke-width': isDay ? 1.4 : 1,
          'stroke-dasharray': isDay ? 'none' : '2 4',
          'class': 'mc-time-line'
        }));
        if (t % labelStep === 0 || t === 1440) {
          var label = t === 1440 ? '次日 00:00' : formatMinute(t % 1440);
          var text = el('text', {
            x: x, y: m.top + plotH + 20, 'text-anchor': 'middle', 'font-size': fs(11),
            fill: isDay ? '#333' : '#7b818a',
            'font-weight': isDay ? 700 : 400, 'class': 'mc-time-label'
          });
          text.textContent = label;
          gAxis.appendChild(text);
        }
      }
      // 轴标题
      var axisTitle = el('text', {
        x: m.left, y: state.height - 6, 'text-anchor': 'start', 'font-size': fs(10), fill: '#9aa0a8'
      });
      axisTitle.textContent = '绝对分钟（0 = ' + (data.meta.coverage.service_date || '服务日') +
        ' 00:00）· 纵轴为示意站序，非公里数';
      gAxis.appendChild(axisTitle);
      svg.appendChild(gAxis);

      // 绘图区裁剪：缩放窗口时折线不得溢出到站名/边距区
      var clipId = 'mc-clip-' + (++clipSeq);
      var defs = el('defs');
      var clip = el('clipPath', { id: clipId });
      clip.appendChild(el('rect', {
        x: m.left - 1, y: m.top - 12, width: plotW + 2, height: plotH + 14
      }));
      defs.appendChild(clip);
      svg.appendChild(defs);

      // 车次折线
      gSeries = el('g', { 'class': 'mc-series-layer', 'clip-path': 'url(#' + clipId + ')' });
      series.forEach(function (s) {
        if (!s.segments.length) return;
        var color = s.usable ? (s.direction === 'down' ? opts.colors.down : opts.colors.up)
          : opts.colors.blocked;
        var dash = s.usable ? (opts.dash[s.direction] || 'none') : opts.dash.blocked;
        var d = s.segments.map(function (seg) { return pathData(seg, xScale, yOf); })
          .filter(function (x) { return x; }).join(' ');
        if (!d) return;

        // 每车一个 <g>：透明加宽命中区 + 可见细线。细线本身只有 1px，直接点很难命中。
        var g = el('g', {
          'class': 'mc-train mc-train--' + (s.direction || 'unknown') + (s.usable ? '' : ' mc-train--blocked'),
          'data-train-id': s.trainId,
          'data-train-no': s.trainNo,
          tabindex: 0,
          role: 'button',
          'aria-label': s.trainNo + ' ' + (s.direction === 'up' ? '上行' : s.direction === 'down' ? '下行' : '方向未知')
        });
        var hit = el('path', {
          d: d, fill: 'none', stroke: 'transparent', 'stroke-width': 10,
          'pointer-events': 'stroke', 'class': 'mc-series-hit'
        });
        var path = el('path', {
          d: d,
          fill: 'none',
          stroke: color,
          'stroke-width': s.usable ? 1.15 : 1,
          'stroke-dasharray': dash,
          'stroke-linejoin': 'round',
          'stroke-linecap': 'round',
          opacity: s.usable ? 0.62 : 0.45,
          'class': 'mc-series mc-series--' + (s.direction || 'unknown') + (s.usable ? '' : ' mc-series--blocked'),
          'pointer-events': 'none'
        });
        var title = el('title');
        title.textContent = s.trainNo + '（' + s.trainType + '，' +
          (s.direction === 'up' ? '上行' : s.direction === 'down' ? '下行' : '方向未知') + '）' +
          (s.skippedStations.length ? '｜通道外站 ' + s.skippedStations.length + ' 个未绘' : '') +
          (s.usable ? '' : '｜数据待核，不参与绘制');
        g.appendChild(title);
        g.appendChild(hit);
        g.appendChild(path);
        if (state.selected === s.trainId) g.classList.add('mc-train--selected');
        trainNodes[s.trainId] = g;
        g.addEventListener('click', function () { emit(s); });
        g.addEventListener('keydown', function (ev) {
          if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); emit(s); }
        });
        gSeries.appendChild(g);
      });
      svg.appendChild(gSeries);

      // 当前时间竖线（单独图层，更新时只改 transform）
      gCursor = el('g', { 'class': 'mc-cursor', opacity: 0 });
      cursorLine = el('line', {
        x1: 0, x2: 0, y1: m.top - 10, y2: m.top + plotH,
        stroke: opts.colors.cursor, 'stroke-width': 1.6
      });
      cursorBg = el('rect', { x: -31, y: m.top - 34, width: 62, height: 18, rx: 3, fill: opts.colors.cursor });
      cursorText = el('text', {
        x: 0, y: m.top - 21, 'text-anchor': 'middle', 'font-size': fs(11), fill: '#fff', 'font-weight': 600
      });
      gCursor.appendChild(cursorLine);
      gCursor.appendChild(cursorBg);
      gCursor.appendChild(cursorText);
      svg.appendChild(gCursor);

      // 图例（颜色 + 线型双编码）
      if (opts.showLegend) {
        var gLegend = el('g', { 'class': 'mc-legend', transform: 'translate(' + m.left + ',18)' });
        var items = [
          { label: '上行 up（实线）', color: opts.colors.up, dash: 'none', x: 0 },
          { label: '下行 down（虚线）', color: opts.colors.down, dash: opts.dash.down, x: 148 }
        ];
        items.forEach(function (it) {
          gLegend.appendChild(el('line', {
            x1: it.x, x2: it.x + 26, y1: 0, y2: 0, stroke: it.color, 'stroke-width': 2,
            'stroke-dasharray': it.dash
          }));
          var t2 = el('text', { x: it.x + 32, y: 4, 'font-size': fs(11), fill: '#4a4f57' });
          t2.textContent = it.label;
          gLegend.appendChild(t2);
        });
        var info = el('text', { x: 320, y: 4, 'font-size': fs(11), fill: '#9aa0a8' });
        info.textContent = '共 ' + series.length + ' 车可绘' +
          (data.stats && data.stats.blocked_trains ? '｜' + data.stats.blocked_trains + ' 车因数据待核未绘制' : '');
        gLegend.appendChild(info);
        svg.appendChild(gLegend);
      }

      root.appendChild(svg);
      applyVisibility();
      if (state.currentTime !== null) setCurrentTime(state.currentTime);
    }

    function emit(s) {
      var evt;
      try {
        evt = new CustomEvent('trainselect', {
          bubbles: true,
          detail: {
            trainId: s.trainId, trainNo: s.trainNo, direction: s.direction,
            trainType: s.trainType, usable: s.usable, status: s.status
          }
        });
      } catch (e) {
        evt = document.createEvent('CustomEvent');
        evt.initCustomEvent('trainselect', true, false, {
          trainId: s.trainId, trainNo: s.trainNo, direction: s.direction,
          trainType: s.trainType, usable: s.usable, status: s.status
        });
      }
      container.dispatchEvent(evt);
    }

    function applyVisibility() {
      if (!gSeries) return;
      var set = state.visible === null ? null : new Set(state.visible);
      Array.prototype.forEach.call(gSeries.childNodes, function (node) {
        var id = node.getAttribute('data-train-id');
        var no = node.getAttribute('data-train-no');
        var show = !set || set.has(id) || set.has(no);
        node.style.display = show ? '' : 'none';
        node.setAttribute('aria-hidden', show ? 'false' : 'true');
      });
    }

    function setCurrentTime(absMinute) {
      if (state.destroyed || !gCursor) return;
      state.currentTime = absMinute;
      var v = Number(absMinute);
      if (!isFinite(v) || v < domain[0] || v > domain[1]) {
        gCursor.setAttribute('opacity', 0);
        return;
      }
      var x = xScale(v);
      gCursor.setAttribute('opacity', 1);
      cursorLine.setAttribute('transform', 'translate(' + x.toFixed(2) + ',0)');
      cursorBg.setAttribute('transform', 'translate(' + x.toFixed(2) + ',0)');
      cursorText.setAttribute('transform', 'translate(' + x.toFixed(2) + ',0)');
      cursorText.textContent = formatMinute(v, { long: true });
    }

    function setSelectedTrain(trainId) {
      state.selected = trainId || null;
      Object.keys(trainNodes).forEach(function (id) {
        trainNodes[id].classList.toggle('mc-train--selected', state.selected === id);
      });
    }

    function setVisibleTrains(ids) {
      state.visible = ids === null || ids === undefined ? null : Array.prototype.slice.call(ids);
      applyVisibility();
    }

    function resize() {
      if (state.destroyed) return;
      layout();
      draw();
    }

    function setDomain(minAbs, maxAbs) {
      if (!(isFinite(minAbs) && isFinite(maxAbs)) || maxAbs <= minAbs) {
        throw new Error('setDomain: 需要 (min, max) 且 max > min');
      }
      domain = [Number(minAbs), Number(maxAbs)];
      draw();
    }

    function setOption(patch) {
      Object.assign(opts, patch || {});
      if (patch && patch.domain) domain = computeDomain(data.meta.coverage, opts);
      draw();
    }

    function destroy() {
      state.destroyed = true;
      if (observer) observer.disconnect();
      clear(root);
      if (root.parentNode) root.parentNode.removeChild(root);
    }

    layout();
    draw();

    var observer = null;
    if (typeof ResizeObserver !== 'undefined') {
      var timer = null;
      observer = new ResizeObserver(function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          if (!state.destroyed && Math.abs((container.clientWidth || 0) - state.width) > 24) resize();
        }, 120);
      });
      observer.observe(container);
    }

    return {
      version: VERSION,
      setCurrentTime: setCurrentTime,
      setVisibleTrains: setVisibleTrains,
      setSelectedTrain: setSelectedTrain,
      setOption: setOption,
      setDomain: setDomain,
      resize: resize,
      destroy: destroy,
      // 调试/测试用
      getLayout: function () {
        return { axis: axis, domain: domain.slice(), series: series, width: state.width, height: state.height };
      }
    };
  }

  return {
    version: VERSION,
    initMareyChart: initMareyChart,
    buildAxis: buildAxis,
    buildSeries: buildSeries,
    computeDomain: computeDomain,
    formatMinute: formatMinute
  };
});
