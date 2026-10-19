/*!
 * player.js — 统一时间控制器（阶段6）
 * 版本：1.0.0
 *
 * 职责：只维护时间状态并推进时钟，不碰任何视图 DOM、不加载数据。
 * 视图通过回调接收 absMinute，由外部自行调用 marey.setCurrentTime / diagram.setLineTime。
 *
 * 用法
 *   const p = Player.createPlayer({
 *     min: 0, max: 2700, initial: 600,
 *     minutesPerSecond: 2,          // 1x：1 秒现实时间 = 2 模拟分钟
 *     onTimeChange: (t, meta) => { ... }   // meta = {playing, speed, reason}
 *   });
 *   p.play(); p.pause(); p.toggle(); p.seek(720); p.step(+1); p.setSpeed(5);
 *   p.getState(); p.destroy();
 *
 * 键盘（全局，输入控件聚焦时自动让行）
 *   Space        播放 / 暂停
 *   ← / →        −1 / +1 分钟
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.Player = factory();
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var VERSION = '1.0.0';

  var DEFAULTS = {
    min: 0,
    max: 1440,
    initial: null,
    speeds: [0.5, 1, 2, 5],
    speed: 1,
    minutesPerSecond: 2,   // 1x 换算常量：唯一来源，散落在 UI 里的都算错
    keyboard: true,
    maxFrameSeconds: 0.25  // 单帧最大推进（切标签页回来不跳）
  };

  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }

  function createPlayer(options) {
    var opts = Object.assign({}, DEFAULTS, options || {});
    if (!(opts.max > opts.min)) throw new Error('createPlayer: max 必须大于 min');

    var state = {
      time: clamp(opts.initial === null ? opts.min : Number(opts.initial), opts.min, opts.max),
      playing: false,
      speed: opts.speeds.indexOf(opts.speed) !== -1 ? opts.speed : 1,
      min: opts.min,
      max: opts.max,
      destroyed: false
    };
    var rafId = null;
    var lastTs = null;

    function notify(reason) {
      if (typeof opts.onTimeChange === 'function') {
        opts.onTimeChange(state.time, {
          playing: state.playing, speed: state.speed, reason: reason || 'tick'
        });
      }
    }

    function frame(ts) {
      if (!state.playing || state.destroyed) return;
      if (lastTs === null) {           // 首帧只记时间戳，不推进
        lastTs = ts;
        rafId = requestAnimationFrame(frame);
        return;
      }
      var dt = (ts - lastTs) / 1000;
      lastTs = ts;
      if (dt > opts.maxFrameSeconds) dt = opts.maxFrameSeconds;   // 切标签页回来不跳
      if (dt < 0) dt = 0;

      var next = state.time + dt * opts.minutesPerSecond * state.speed;
      if (next >= state.max) {
        state.time = state.max;
        state.playing = false;
        rafId = null;
        lastTs = null;
        notify('boundary');
        return;
      }
      state.time = next;
      notify('tick');
      rafId = requestAnimationFrame(frame);
    }

    function play() {
      if (state.destroyed || state.playing) return;
      if (state.time >= state.max) state.time = state.min;   // 播完再按播放 = 从头开始
      state.playing = true;
      lastTs = null;
      rafId = requestAnimationFrame(frame);
      notify('play');
    }

    function pause() {
      if (!state.playing) return;
      state.playing = false;
      if (rafId !== null) cancelAnimationFrame(rafId);
      rafId = null;
      lastTs = null;
      notify('pause');
    }

    function toggle() { state.playing ? pause() : play(); }

    function seek(t, reason) {
      if (state.destroyed) return;
      var v = Number(t);
      if (!isFinite(v)) return;
      var clamped = clamp(v, state.min, state.max);
      if (clamped >= state.max && state.playing) pause();   // 拖到终点即停
      state.time = clamped;
      notify(reason || 'seek');
    }

    function step(delta) {
      seek(state.time + Number(delta || 0), 'step');
    }

    function setSpeed(s) {
      var v = Number(s);
      if (opts.speeds.indexOf(v) === -1) throw new Error('setSpeed: 不支持的倍速 ' + s);
      state.speed = v;
      notify('speed');
    }

    function setRange(min, max) {
      if (!(max > min)) throw new Error('setRange: max 必须大于 min');
      state.min = min; state.max = max;
      state.time = clamp(state.time, min, max);
      notify('range');
    }

    function isEditable(target) {
      if (!target || !target.closest) return false;
      return !!target.closest('input, textarea, select, button, [contenteditable="true"]');
    }

    function onKeyDown(ev) {
      if (state.destroyed || !opts.keyboard) return;
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
      if (isEditable(ev.target)) return;      // 输入框/按钮/选择器聚焦时让行
      if (ev.code === 'Space' || ev.key === ' ') {
        ev.preventDefault();
        toggle();
      } else if (ev.key === 'ArrowLeft') {
        ev.preventDefault();
        step(-1);
      } else if (ev.key === 'ArrowRight') {
        ev.preventDefault();
        step(1);
      }
    }

    function onVisibility() {
      if (!state.playing) return;
      lastTs = null;   // 回到前台重新计时，避免一帧跳几分钟
    }

    if (opts.keyboard) document.addEventListener('keydown', onKeyDown);
    document.addEventListener('visibilitychange', onVisibility);

    function destroy() {
      pause();
      state.destroyed = true;
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('visibilitychange', onVisibility);
    }

    return {
      version: VERSION,
      play: play,
      pause: pause,
      toggle: toggle,
      seek: seek,
      step: step,
      setSpeed: setSpeed,
      setRange: setRange,
      destroy: destroy,
      getState: function () {
        return {
          time: state.time, playing: state.playing, speed: state.speed,
          min: state.min, max: state.max
        };
      }
    };
  }

  return {
    version: VERSION,
    createPlayer: createPlayer,
    DEFAULTS: DEFAULTS
  };
});
