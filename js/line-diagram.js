/*!
 * line-diagram.js — 石太客专 + 阳大铁路 线路示意与列车位置（阶段5）
 * 版本：1.0.0
 *
 * 契约：docs/data-contract.md v1.0.0（只读 data/processed/*.json）
 * 依赖：无（原生 SVG + DOM）
 *
 * 公开接口
 *   const d = LineDiagram.initLineDiagram(container, data, options)
 *   d.setLineTime(absMinute)          // 由外部时钟驱动，本模块不自己推进时间
 *   d.setVisibleTrains(ids|null)      // 支持 train_id / train_no
 *   d.setSelectedTrain(trainId|null)
 *   d.resize() / d.destroy() / d.getLayout() / d.getActiveTrains()
 *   container.addEventListener('trainselect', e => e.detail)
 *
 * 纯函数（Node 可直接 require 做单测）
 *   LineDiagram.buildLayout(stations, options)
 *   LineDiagram.buildLegs(train, layout, segments)
 *   LineDiagram.computePosition(pack, absMinute)
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.LineDiagram = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var VERSION = '1.0.0';
  var SVG_NS = 'http://www.w3.org/2000/svg';

  var DEFAULTS = {
    height: 400,
    viewWidth: 1000,
    padLeft: 52,
    padRight: 52,
    padTop: 40,
    padBottom: 34,
    fontScale: 1,           // 字号倍率（录制/大屏时可放大）
    sideOffset: 0,          // 车底沿行进方向左侧的法线偏移（复线上下行分侧；0=贴线）
    showCaption: true,      // 底部操作说明（录制时可关）
    showLabels: true,
    showBlocked: false,      // 阻断车不参与绘制（与 Marey 图口径一致）
    endBehavior: 'hold',     // 'hold' 停在终点 / 'hide' 到站即消失
    colors: {
      up: '#c0392b',
      down: '#1f6fb2',
      line: '#c3c8cf',
      branch: '#d3d7dc',
      station: '#6b7280',
      highlight: '#c2410c',
      text: '#4a4f57',
      muted: '#9aa0a8',
      selected: '#d9480f'
    }
  };

  // ---------------------------------------------------------------------
  // 纯函数层
  // ---------------------------------------------------------------------

  /**
   * 由 stations[].place 生成示意坐标。
   * 坐标为归一化值（x 西→东，y 北→南），在这里换算成 viewBox 像素。
   * 主线按 sequence 串成折线；支线按 branch_of 挂到父站，联络线用虚线。
   */
  function buildLayout(stations, options) {
    var opts = Object.assign({}, DEFAULTS, options || {});
    var fontScale = Number(opts.fontScale) > 0 ? Number(opts.fontScale) : 1;
    function fs(n) { return n * fontScale; }
    var W = opts.viewWidth, H = opts.height;
    var padL = opts.padLeft, padR = opts.padRight, padT = opts.padTop, padB = opts.padBottom;
    var toX = function (x) { return padL + x * (W - padL - padR); };
    var toY = function (y) { return padT + y * (H - padT - padB); };

    var nodes = [];
    var byStationId = {};
    var byStationName = {};
    var nameById = {};

    (stations || []).forEach(function (st) {
      if (!st || !st.station_id) return;
      nameById[st.station_id] = st.name;
      if (!st.place) return;
      var p = st.place;
      var node = {
        key: st.name,
        name: st.name,
        label: st.name,
        stationId: st.station_id,
        line: p.line,
        sequence: p.sequence,
        nx: p.x, ny: p.y,
        x: toX(p.x), y: toY(p.y),
        role: p.role,
        branchOf: p.branch_of,
        branchOrder: p.branch_order,
        link: p.link,
        labelPos: p.label || 'above',
        major: (st.stats && st.stats.stop_records > 0) || !!st.is_highlighted,
        highlight: !!st.is_highlighted
      };
      nodes.push(node);
      byStationId[st.station_id] = node;
      byStationName[st.name] = node;
    });

    var mainNodes = nodes.filter(function (n) { return n.sequence !== null && !n.branchOf; })
      .sort(function (a, b) { return a.sequence - b.sequence; });
    var branchNodes = nodes.filter(function (n) { return !!n.branchOf; })
      .sort(function (a, b) { return (a.branchOrder || 0) - (b.branchOrder || 0); });

    // ---- 轨道图：所有边都是横平竖直的折线，车底点沿边行走 ----
    var edges = [];
    var adj = {};
    function ensureAdj(name) { return (adj[name] = adj[name] || []); }
    function orthoGeometry(a, b) {
      if (a.x === b.x || a.y === b.y) return [{ x: a.x, y: a.y }, { x: b.x, y: b.y }];
      // 数据没对齐时兜底：先横后竖，保证不出现斜线
      return [{ x: a.x, y: a.y }, { x: b.x, y: a.y }, { x: b.x, y: b.y }];
    }
    function polyLength(geom) {
      var len = 0;
      for (var i = 1; i < geom.length; i++) len += Math.hypot(geom[i].x - geom[i - 1].x, geom[i].y - geom[i - 1].y);
      return len;
    }
    function addEdge(a, b, kind) {
      if (!a || !b || a.name === b.name) return;
      var geom = orthoGeometry(a, b);
      var length = polyLength(geom);
      edges.push({ a: a.name, b: b.name, kind: kind, geom: geom, length: length });
      ensureAdj(a.name).push({ to: b.name, geom: geom, length: length });
      ensureAdj(b.name).push({ to: a.name, geom: geom.slice().reverse(), length: length });
    }
    mainNodes.forEach(function (n, i) { if (i > 0) addEdge(mainNodes[i - 1], n, 'main'); });
    // ---- 支线：同 branchOf 的站按 branch_order 串成链（父站 → order1 → order2 → …）----
    // catalog 的 branch_of 是“示意挂接”，若按它直接连边，昔阳→平定 会绕道阳泉东，
    // 车底在阳泉东—平定区间来回（徘徊）。实际线路是链：阳泉北—阳泉东—平定—昔阳。
    var branchGroups = {};
    branchNodes.forEach(function (n) {
      (branchGroups[n.branchOf] = branchGroups[n.branchOf] || []).push(n);
    });
    Object.keys(branchGroups).forEach(function (parentName) {
      var chain = branchGroups[parentName].slice().sort(function (a, b) {
        return (a.branchOrder || 0) - (b.branchOrder || 0);
      });
      var prevNode = byStationName[parentName];
      chain.forEach(function (n) {
        addEdge(prevNode, n, n.link === 'connecting' ? 'connecting' : 'regional');
        prevNode = n;
      });
    });

    var routeCache = {};
    function route(fromId, toId) {
      var a = byStationId[fromId];
      var b = byStationId[toId];
      if (!a || !b) return null;
      if (a.name === b.name) return { geom: [{ x: a.x, y: a.y }], length: 0 };
      var key = a.name + '|' + b.name;
      if (routeCache[key]) return routeCache[key];

      var prev = {};
      var seen = {};
      var queue = [a.name];
      seen[a.name] = true;
      while (queue.length) {
        var cur = queue.shift();
        if (cur === b.name) break;
        (adj[cur] || []).forEach(function (e) {
          if (seen[e.to]) return;
          seen[e.to] = true;
          prev[e.to] = { from: cur, edge: e };
          queue.push(e.to);
        });
      }
      if (!seen[b.name]) return null;

      var chain = [];
      var node = b.name;
      while (node !== a.name) {
        var step = prev[node];
        chain.unshift(step.edge);
        node = step.from;
      }
      var geom = [];
      chain.forEach(function (e) {
        e.geom.forEach(function (pt) {
          var last = geom[geom.length - 1];
          if (!last || last.x !== pt.x || last.y !== pt.y) geom.push({ x: pt.x, y: pt.y });
        });
      });
      var result = { geom: geom, length: polyLength(geom) };
      routeCache[key] = result;
      return result;
    }

    return {
      nodes: nodes,
      mainNodes: mainNodes,
      branchNodes: branchNodes,
      edges: edges,
      route: route,
      byStationId: byStationId,
      byStationName: byStationName,
      nameById: nameById,
      width: W,
      height: H
    };
  }

  /**
   * 单车可绘制区段：只取两端都在示意图上的 segment。
   * 区间是相邻站生成的，所以不会出现"跨过未映射站硬连"的情况。
   */
  function buildLegs(train, layout, segments) {
    var list = [];
    var skipped = 0;

    (segments || []).forEach(function (g) {
      if (g.segment_type !== 'run' && g.segment_type !== 'dwell') { skipped += 1; return; }
      var fromNode = layout.byStationId[g.from_station_id];
      var toNode = layout.byStationId[g.to_station_id];
      if (!fromNode || !toNode) { skipped += 1; return; }

      var start = g.segment_type === 'dwell' ? g.arrival_abs_minute : g.departure_abs_minute;
      var end = g.segment_type === 'dwell' ? g.departure_abs_minute : g.arrival_abs_minute;
      if (start === null || start === undefined || end === null || end === undefined) {
        skipped += 1;
        return;
      }
      if (end < start) { skipped += 1; return; }

      var path = layout.route(g.from_station_id, g.to_station_id);
      if (!path || !path.geom.length) { skipped += 1; return; }

      list.push({
        segmentId: g.segment_id,
        type: g.segment_type,
        detour: !!g.__detour,
        start: start,
        end: end,
        fromNode: fromNode,
        toNode: toNode,
        path: path.geom,
        pathLength: path.length,
        fromStation: layout.nameById[g.from_station_id] || fromNode.name,
        toStation: layout.nameById[g.to_station_id] || toNode.name
      });
    });

    list.sort(function (a, b) { return a.start - b.start; });

    var terminalNode = layout.byStationName[train.terminal] || null;
    var last = list[list.length - 1] || null;
    var terminalInCorridor = !!(terminalNode && last && last.toNode === terminalNode);

    return {
      legs: list,
      skippedSegments: skipped,
      firstStart: list.length ? list[0].start : null,
      lastEnd: list.length ? last.end : null,
      terminalInCorridor: terminalInCorridor
    };
  }

  /** 沿折线走 dist 像素后的点；用于让车底点严格贴着轨道。 */
  function pointAlong(geom, dist) {
    if (!geom || !geom.length) return { x: 0, y: 0 };
    if (geom.length === 1 || dist <= 0) return { x: geom[0].x, y: geom[0].y };
    var remain = dist;
    for (var i = 1; i < geom.length; i++) {
      var dx = geom[i].x - geom[i - 1].x;
      var dy = geom[i].y - geom[i - 1].y;
      var seg = Math.hypot(dx, dy);
      if (remain <= seg || i === geom.length - 1) {
        var f = seg > 0 ? Math.min(1, Math.max(0, remain / seg)) : 0;
        return { x: geom[i - 1].x + dx * f, y: geom[i - 1].y + dy * f };
      }
      remain -= seg;
    }
    return { x: geom[geom.length - 1].x, y: geom[geom.length - 1].y };
  }

  /**
   * 位置状态机（纯函数）：
   *   off_corridor 不在通道 / pending 未发车 / between 离开通道中 / moving 运行 / stopped 停站 / terminal 终到 / left 已离开通道
   */
  function computePosition(pack, absMinute) {
    if (!pack || !pack.legs.length) return { state: 'off_corridor', x: null, y: null };
    var t = Number(absMinute);
    if (!isFinite(t)) return { state: 'off_corridor', x: null, y: null };
    if (t < pack.legs[0].start) return { state: 'pending', x: null, y: null };

    for (var i = 0; i < pack.legs.length; i++) {
      var leg = pack.legs[i];
      if (t < leg.start) {
        // 处于两段之间：说明中间经过通道外站点，不应画在这条线上
        return { state: 'between', x: null, y: null };
      }
      if (t <= leg.end) {
        if (leg.type === 'dwell' || leg.end === leg.start) {
          return {
            state: 'stopped', x: leg.fromNode.x, y: leg.fromNode.y,
            legIndex: i, segmentId: leg.segmentId,
            station: leg.fromStation
          };
        }
        // 绕行区间（该车实际经由骨架外线路）：不显示车底，避免在逻辑线上被同向快车穿越
        if (leg.detour) return { state: 'detour', x: null, y: null };
        var p = (t - leg.start) / (leg.end - leg.start);
        p = Math.max(0, Math.min(1, p));
        var pt = pointAlong(leg.path, p * leg.pathLength);
        // 行进方向左侧法线（中国铁路靠左行车）：供上下行分侧绘制，对向车不再重叠相穿
        var g0 = leg.path[0], g1 = leg.path[leg.path.length - 1];
        var ddx = g1.x - g0.x, ddy = g1.y - g0.y, dl = Math.hypot(ddx, ddy) || 1;
        return {
          state: 'moving',
          x: pt.x, y: pt.y,
          nx: ddy / dl, ny: -ddx / dl,
          legIndex: i, segmentId: leg.segmentId, progress: p,
          fromStation: leg.fromStation, toStation: leg.toStation
        };
      }
    }

    var last = pack.legs[pack.legs.length - 1];
    if (pack.terminalInCorridor) {
      return { state: 'terminal', x: last.toNode.x, y: last.toNode.y, station: last.toStation };
    }
    return { state: 'left', x: null, y: null };
  }

  // ---------------------------------------------------------------------
  // DOM 层
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

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function initLineDiagram(container, data, options) {
    if (!container) throw new Error('initLineDiagram: container 不能为空');
    if (!data || !data.trains || !data.stations) throw new Error('initLineDiagram: data 不符合契约');

    var opts = Object.assign({}, DEFAULTS, options || {});
    opts.colors = Object.assign({}, DEFAULTS.colors, (options && options.colors) || {});
    var fontScale = Number(opts.fontScale) > 0 ? Number(opts.fontScale) : 1;
    function fs(n) { return n * fontScale; }

    var layout = buildLayout(data.stations, opts);
    var segmentsByTrain = {};
    (data.segments || []).forEach(function (g) {
      (segmentsByTrain[g.train_id] = segmentsByTrain[g.train_id] || []).push(g);
    });

    // ---- 绕行段标记：走石太老线的普速车（停“太原(南)+石家庄北”但不停任何客专
    // 中途站 阳泉北/井陉北），其 太原↔石家庄北 区间实际在骨架外的老线上绕行。
    // 按真实时刻画在客专路径上会被同向快车反复穿越（“追尾”），标记 detour：
    // 该区间不显示车底，仅显示其在骨架站的停站（待避/停靠画面不受影响）。
    var oldLineTrain = {};
    (data.trains || []).forEach(function (t) {
      var names = {};
      (t.stops || []).forEach(function (s) { names[s.station] = true; });
      if (names['石家庄北'] && !names['阳泉北'] && !names['井陉北']) {
        oldLineTrain[t.train_id] = true;
      }
    });
    (data.segments || []).forEach(function (g) {
      if (g.segment_type !== 'run' || !oldLineTrain[g.train_id]) return;
      var f = (g.from_station_id || '').replace('st:', '');
      var to = (g.to_station_id || '').replace('st:', '');
      if ((f === '石家庄北' && (to === '太原' || to === '太原南')) ||
          (to === '石家庄北' && (f === '太原' || f === '太原南'))) {
        g.__detour = true;
      }
    });

    var trains = data.trains
      .filter(function (t) { return opts.showBlocked || (t.validation && t.validation.usable_for_frontend); })
      .map(function (t) {
      var pack = buildLegs(t, layout, segmentsByTrain[t.train_id] || []);
      return {
        trainId: t.train_id, trainNo: t.train_no, direction: t.direction,
        trainType: t.train_type,
        usable: !!(t.validation && t.validation.usable_for_frontend),
        status: t.validation ? t.validation.status : 'unknown',
        pack: pack
      };
    });

    var state = {
      time: null,
      visible: null,
      selected: null,
      width: opts.viewWidth,
      destroyed: false,
      active: []
    };

    var root = document.createElement('div');
    root.className = 'ld-root';
    container.appendChild(root);

    var svg, gTrains, trainNodes = {};

    function draw() {
      clear(root);
      trainNodes = {};
      var W = opts.viewWidth, H = opts.height;

      svg = el('svg', {
        'class': 'ld-svg',
        viewBox: '0 0 ' + W + ' ' + H,
        width: '100%',
        height: H,
        role: 'img',
        'aria-label': '石太客专与阳大铁路线路示意图',
        preserveAspectRatio: 'xMidYMid meet'
      });

      // 轨道：主线 → 支线 → 联络线（全部横平竖直）
      ['main', 'regional', 'connecting'].forEach(function (kind) {
        layout.edges.filter(function (e) { return e.kind === kind; }).forEach(function (e) {
          var d = e.geom.map(function (pt, i) {
            return (i === 0 ? 'M' : 'L') + pt.x.toFixed(1) + ' ' + pt.y.toFixed(1);
          }).join(' ');
          var connecting = kind === 'connecting';
          svg.appendChild(el('path', {
            d: d, fill: 'none',
            stroke: kind === 'main' ? opts.colors.line : (connecting ? '#b9bec6' : opts.colors.branch),
            'stroke-width': kind === 'main' ? 7 : (connecting ? 3 : 5),
            'stroke-dasharray': connecting ? '7 5' : 'none',
            'stroke-linecap': 'butt', 'stroke-linejoin': 'miter',
            'class': 'ld-track ld-track--' + kind + (connecting ? ' ld-link ld-link--connecting' : '')
          }));
        });
      });

      // 车站
      var gStations = el('g', { 'class': 'ld-stations' });
      layout.nodes.forEach(function (node) {
        var g = el('g', {
          'class': 'ld-station' + (node.major ? '' : ' ld-station--minor') +
                   (node.highlight ? ' ld-station--highlight' : ''),
          'data-station': node.name
        });
        if (!node.major) {
          g.appendChild(el('circle', {
            cx: node.x, cy: node.y, r: 3,
            fill: '#fff', stroke: opts.colors.line, 'stroke-width': 2
          }));
          if (opts.showLabels) {
            var minorLabel = el('text', {
              x: node.line === 'yangda' ? node.x - 11 : node.x,
              y: node.line === 'yangda' ? node.y + 3 : node.y + 16,
              'text-anchor': node.line === 'yangda' ? 'end' : 'middle',
              'font-size': fs(9.5), fill: '#a6acb4', 'class': 'ld-station-label ld-station-label--minor'
            });
            minorLabel.textContent = node.label;
            g.appendChild(minorLabel);
          }
          var t = el('title');
          t.textContent = node.label + '（车站骨架站，本批无停站）';
          g.appendChild(t);
          gStations.appendChild(g);
          return;
        }
        if (node.highlight) {
          g.appendChild(el('circle', {
            cx: node.x, cy: node.y, r: 13, fill: 'rgba(194,65,12,.10)',
            stroke: 'rgba(194,65,12,.35)', 'stroke-width': 1, 'class': 'ld-halo'
          }));
        }
        g.appendChild(el('circle', {
          cx: node.x, cy: node.y, r: node.highlight ? 7.5 : 5.5,
          fill: '#fff',
          stroke: node.highlight ? opts.colors.highlight : opts.colors.station,
          'stroke-width': node.highlight ? 3 : 2
        }));
        if (opts.showLabels) {
          var pos = node.labelPos;
          var lx = node.x, ly = node.y - 13, anchor = 'middle';
          if (pos === 'below') { ly = node.y + 23; }
          else if (pos === 'left') { lx = node.x - 13; ly = node.y + 4; anchor = 'end'; }
          else if (pos === 'right') { lx = node.x + 13; ly = node.y + 4; anchor = 'start'; }
          var label = el('text', {
            x: lx, y: ly, 'text-anchor': anchor,
            'font-size': node.highlight ? fs(13) : fs(12),
            'font-weight': node.highlight ? 700 : 500,
            fill: node.highlight ? opts.colors.highlight : opts.colors.text,
            'class': 'ld-station-label'
          });
          label.textContent = node.label;
          g.appendChild(label);
        }
        gStations.appendChild(g);
      });
      svg.appendChild(gStations);

      // 图例
      var gLegend = el('g', { 'class': 'ld-legend', transform: 'translate(24,26)' });
      gLegend.appendChild(el('circle', { cx: 0, cy: 0, r: 5, fill: opts.colors.up }));
      var l1 = el('text', { x: 10, y: 4, 'font-size': fs(11), fill: opts.colors.text });
      l1.textContent = '上行 up（圆点）';
      gLegend.appendChild(l1);
      gLegend.appendChild(el('rect', {
        x: 128, y: -5, width: 10, height: 10, fill: opts.colors.down,
        transform: 'rotate(45 133 0)'
      }));
      var l2 = el('text', { x: 146, y: 4, 'font-size': fs(11), fill: opts.colors.text });
      l2.textContent = '下行 down（菱形）';
      gLegend.appendChild(l2);
      gLegend.appendChild(el('line', {
        x1: 280, x2: 306, y1: 0, y2: 0, stroke: '#b9bec6',
        'stroke-width': 3, 'stroke-dasharray': '7 5'
      }));
      var l3 = el('text', { x: 312, y: 4, 'font-size': fs(11), fill: opts.colors.text });
      l3.textContent = '联络线（虚线）';
      gLegend.appendChild(l3);
      var note = el('text', { x: 420, y: 4, 'font-size': fs(11), fill: opts.colors.muted });
      note.textContent = '横平竖直示意（上北下南），非地理比例';
      gLegend.appendChild(note);
      svg.appendChild(gLegend);

      // 列车
      gTrains = el('g', { 'class': 'ld-trains' });
      trains.forEach(function (tr) {
        if (!tr.pack.legs.length) return;
        var g = el('g', {
          'class': 'ld-train ld-train--' + (tr.direction || 'unknown'),
          'data-train-id': tr.trainId,
          'data-train-no': tr.trainNo,
          tabindex: 0,
          role: 'button',
          'aria-label': tr.trainNo + ' ' + (tr.direction === 'up' ? '上行' : tr.direction === 'down' ? '下行' : '方向未知'),
          style: 'display:none'
        });
        var title = el('title');
        title.textContent = tr.trainNo + '（' + tr.trainType + '，' +
          (tr.direction === 'up' ? '上行' : tr.direction === 'down' ? '下行' : '方向未知') + '）';
        g.appendChild(title);
        g.appendChild(el('circle', { r: 13, cx: 0, cy: 0, fill: 'transparent', 'class': 'ld-hit' }));
        g.appendChild(el('circle', {
          r: 9.5, cx: 0, cy: 0, fill: 'none', stroke: opts.colors.selected,
          'stroke-width': 1.6, 'stroke-dasharray': '3 3', 'class': 'ld-selected-ring', opacity: 0
        }));
        if (tr.direction === 'down') {
          g.appendChild(el('rect', {
            x: -4.4, y: -4.4, width: 8.8, height: 8.8,
            transform: 'rotate(45)', fill: opts.colors.down,
            stroke: '#fff', 'stroke-width': 1.4, 'class': 'ld-marker'
          }));
        } else {
          g.appendChild(el('circle', {
            r: 5, cx: 0, cy: 0, fill: opts.colors.up,
            stroke: '#fff', 'stroke-width': 1.4, 'class': 'ld-marker'
          }));
        }
        var lbl = el('text', {
          x: 9, y: -8, 'font-size': fs(9.5),
          fill: tr.direction === 'down' ? opts.colors.down : opts.colors.up,
          'paint-order': 'stroke', stroke: '#fff', 'stroke-width': 3,
          'stroke-linejoin': 'round', 'class': 'ld-train-label'
        });
        lbl.textContent = tr.trainNo;
        g.appendChild(lbl);
        g.addEventListener('click', function () { emit(tr); });
        g.addEventListener('keydown', function (ev) {
          if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); emit(tr); }
        });
        gTrains.appendChild(g);
        trainNodes[tr.trainId] = g;
      });
      svg.appendChild(gTrains);

      // 空状态提示
      if (opts.showCaption) {
        var empty = el('text', {
          x: opts.viewWidth / 2, y: opts.height - 16,
          'text-anchor': 'middle', 'font-size': fs(11), fill: opts.colors.muted,
          'class': 'ld-caption'
        });
        empty.textContent = '圆点/菱形出现即表示该车此刻在通道内；未发车、已终到、已离开通道的车不显示位置';
        svg.appendChild(empty);
      }

      root.appendChild(svg);

      if (state.time !== null) setLineTime(state.time);
      if (state.selected) setSelectedTrain(state.selected);
    }

    function emit(tr) {
      var detail = {
        trainId: tr.trainId, trainNo: tr.trainNo, direction: tr.direction,
        trainType: tr.trainType, usable: tr.usable, status: tr.status
      };
      var evt;
      try {
        evt = new CustomEvent('trainselect', { bubbles: true, detail: detail });
      } catch (e) {
        evt = document.createEvent('CustomEvent');
        evt.initCustomEvent('trainselect', true, false, detail);
      }
      container.dispatchEvent(evt);
    }

    function isEnabled(tr) {
      if (state.visible === null) return true;
      return state.visible.indexOf(tr.trainId) !== -1 || state.visible.indexOf(tr.trainNo) !== -1;
    }

    function setLineTime(absMinute) {
      if (state.destroyed) return;
      state.time = absMinute;

      var items = [];
      trains.forEach(function (tr) {
        var g = trainNodes[tr.trainId];
        if (!g) return;
        var pos = computePosition(tr.pack, absMinute);
        var visibleByState = pos.state === 'moving' || pos.state === 'stopped' ||
          (pos.state === 'terminal' && opts.endBehavior === 'hold');
        var show = visibleByState && isEnabled(tr);
        if (!show) {
          g.style.display = 'none';
          g.setAttribute('aria-hidden', 'true');
          return;
        }
        items.push({ tr: tr, g: g, pos: pos });
      });

      // 同一行内标签错层，避免多个车次标签叠在一起（只错开标签，不动标记位置）
      items.sort(function (a, b) { return (a.pos.y - b.pos.y) || (a.pos.x - b.pos.x); });
      var rowTiers = {};
      items.forEach(function (it) {
        var key = Math.round(it.pos.y / 36);   // 按纵向分带错层，移动中的车也能错开
        var arr = rowTiers[key] || (rowTiers[key] = [-1e9, -1e9, -1e9, -1e9]);
        var tier = -1;
        for (var k = 0; k < arr.length; k++) {
          if (it.pos.x - arr[k] >= 46) { tier = k; break; }
        }
        if (tier === -1) tier = arr.indexOf(Math.min.apply(null, arr));
        arr[tier] = it.pos.x;
        var label = it.g.querySelector('.ld-train-label');
        if (label) {
          label.setAttribute('y', -9 - tier * 11);
          // 终到车停在终点不常驻标签，避免多车堆在端点；选中/悬停时由 CSS 恢复
          label.setAttribute('opacity', it.pos.state === 'terminal' ? 0 : 1);
        }
      });

      items.forEach(function (it) {
        var g = it.g, pos = it.pos;
        var side = (pos.nx || pos.ny) ? (opts.sideOffset || 0) : 0;   // 仅行进中的车分侧
        g.style.display = '';
        g.setAttribute('aria-hidden', 'false');
        g.setAttribute('transform', 'translate(' + (pos.x + (pos.nx || 0) * side).toFixed(2) + ',' +
          (pos.y + (pos.ny || 0) * side).toFixed(2) + ')');
        g.setAttribute('opacity', pos.state === 'terminal' ? 0.5 : 1);
        g.setAttribute('data-state', pos.state);
      });

      state.active = items.map(function (it) {
        var pos = it.pos;
        return {
          trainId: it.tr.trainId, trainNo: it.tr.trainNo, direction: it.tr.direction,
          state: pos.state,
          station: pos.station || null,
          fromStation: pos.fromStation || null,
          toStation: pos.toStation || null,
          progress: typeof pos.progress === 'number' ? pos.progress : null
        };
      });
    }

    function setVisibleTrains(ids) {
      state.visible = ids === null || ids === undefined ? null : Array.prototype.slice.call(ids);
      if (state.time !== null) setLineTime(state.time);
    }

    function setSelectedTrain(trainId) {
      state.selected = trainId || null;
      Object.keys(trainNodes).forEach(function (id) {
        var ring = trainNodes[id].querySelector('.ld-selected-ring');
        if (ring) ring.setAttribute('opacity', state.selected === id ? 1 : 0);
      });
    }

    function resize() { if (!state.destroyed) draw(); }

    function destroy() {
      state.destroyed = true;
      clear(root);
      if (root.parentNode) root.parentNode.removeChild(root);
    }

    draw();

    return {
      version: VERSION,
      setLineTime: setLineTime,
      setVisibleTrains: setVisibleTrains,
      setSelectedTrain: setSelectedTrain,
      resize: resize,
      destroy: destroy,
      getLayout: function () { return layout; },
      getActiveTrains: function () { return state.active.slice(); },
      getTrainStates: function () {
        return trains.map(function (tr) {
          var pos = computePosition(tr.pack, state.time);
          return { trainNo: tr.trainNo, state: pos.state };
        });
      }
    };
  }

  return {
    version: VERSION,
    initLineDiagram: initLineDiagram,
    buildLayout: buildLayout,
    buildLegs: buildLegs,
    computePosition: computePosition,
    DEFAULTS: DEFAULTS
  };
});
