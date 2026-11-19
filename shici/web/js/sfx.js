// 按键音效：全部用 Web Audio 现场合成，不带音频文件。默认关闭，在设置里打开和选择音色。
// 每个音色由“一个带音高滑落的主体音 + 几个泛音 + 一小段滤过的噪声瞬态”组成；
// 不同操作（翻牌、忘记、认识、完成…）只是改变音高、力度和敲击次数。

let ctx = null, master = null, noiseBuf = null;
const state = { on: false, set: "wood", vol: 0.6 };

export const SETS = {
  wood:  { name: "木质", body: { f: 196, to: 150, dur: 0.11, gain: 0.55, type: "sine" }, harm: [{ mul: 2.76, gain: 0.12, dur: 0.05 }], noise: { gain: 0.22, f: 1400, q: 1.2, dur: 0.018, type: "bandpass" } },
  felt:  { name: "毛毡", body: { f: 98, to: 72, dur: 0.17, gain: 0.72, type: "sine" }, harm: [{ mul: 2.0, gain: 0.08, dur: 0.07 }], noise: { gain: 0.1, f: 320, q: 0.7, dur: 0.04, type: "lowpass" } },
  stone: { name: "石子", body: { f: 300, to: 268, dur: 0.07, gain: 0.5, type: "triangle" }, harm: [{ mul: 1.52, gain: 0.26, dur: 0.05 }], noise: { gain: 0.42, f: 2600, q: 2, dur: 0.012, type: "bandpass" } },
  keys:  { name: "键盘", body: { f: 128, to: 104, dur: 0.07, gain: 0.5, type: "sine" }, harm: [], noise: { gain: 0.38, f: 900, q: 0.8, dur: 0.03, type: "lowpass" } },
  glass: { name: "玻璃", body: { f: 880, to: 880, dur: 0.32, gain: 0.22, type: "sine" }, harm: [{ mul: 1.5, gain: 0.1, dur: 0.26 }, { mul: 2.01, gain: 0.05, dur: 0.18 }], noise: { gain: 0.05, f: 5000, q: 3, dur: 0.008, type: "bandpass" } },
};

// 每个事件是一串敲击：[延迟秒, 音高倍数, 力度倍数, 时值倍数]
const EVENTS = {
  tap:    [[0, 1, 0.5, 0.8]],
  toggle: [[0, 1.06, 0.5, 0.7]],
  flip:   [[0, 1.12, 0.75, 1]],
  again:  [[0, 0.84, 0.9, 1.1], [0.09, 0.7, 0.75, 1.3]],
  hard:   [[0, 0.94, 0.85, 1]],
  good:   [[0, 1.19, 0.9, 1]],
  easy:   [[0, 1.19, 0.8, 1], [0.07, 1.5, 0.8, 1.1]],
  ok:     [[0, 1.19, 0.8, 1], [0.08, 1.5, 0.85, 1.2]],
  error:  [[0, 0.8, 0.9, 1.1], [0.1, 0.8, 0.7, 1.1]],
  done:   [[0, 1, 0.8, 1.2], [0.13, 1.26, 0.8, 1.2], [0.26, 1.5, 0.9, 1.9]],
};

export function configure(s) {
  state.on = !!s.sfx;
  state.haptic = !!s.haptic && !!window.ShiciAndroid?.vibrate;
  state.set = SETS[s.sfx_set] ? s.sfx_set : "wood";
  state.vol = Math.max(0, Math.min(1, (s.sfx_volume ?? 60) / 100));
  if (master) master.gain.value = state.vol;
}

function noise(c) {
  if (noiseBuf && noiseBuf.sampleRate === c.sampleRate) return noiseBuf;
  const buf = c.createBuffer(1, Math.floor(c.sampleRate * 0.25), c.sampleRate), d = buf.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  return (noiseBuf = buf);
}

function strike(c, out, def, t, mul, vel, len) {
  const tone = (f, to, dur, gain, type) => {
    const o = c.createOscillator(), g = c.createGain();
    o.type = type || "sine";
    o.frequency.setValueAtTime(f * mul, t);
    if (to !== f) o.frequency.exponentialRampToValueAtTime(to * mul, t + dur * len * 0.7);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain * vel, t + 0.004);       // 4ms 起音，避免爆音
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur * len);
    o.connect(g).connect(out);
    o.start(t); o.stop(t + dur * len + 0.02);
  };
  const b = def.body;
  tone(b.f, b.to, b.dur, b.gain, b.type);
  for (const hm of def.harm) tone(b.f * hm.mul, b.to * hm.mul, hm.dur, hm.gain, "sine");
  if (def.noise.gain > 0) {
    const n = def.noise, src = c.createBufferSource(), flt = c.createBiquadFilter(), g = c.createGain();
    src.buffer = noise(c);
    flt.type = n.type; flt.frequency.value = n.f * Math.sqrt(mul); flt.Q.value = n.q;
    g.gain.setValueAtTime(n.gain * vel, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + n.dur * len);
    src.connect(flt).connect(g).connect(out);
    src.start(t); src.stop(t + n.dur * len + 0.02);
  }
}

// 把一个事件画进任意 AudioContext（也用于自动化测试里的离线渲染）
export function schedule(c, out, event, set, t0) {
  const def = SETS[set] || SETS.wood;
  for (const [dt, mul, vel, len] of EVENTS[event] || EVENTS.tap) strike(c, out, def, t0 + dt, mul, vel, len);
}

let preview = null; // 当前试听声音的音量节点
// 震动反馈（安卓版）：用手机的震动马达，和声音分开开关。不同操作震感不同（见 MainActivity.vibrate）
export function buzz(event) {
  try { window.ShiciAndroid.vibrate(event); } catch { /* 旧版外壳没有这个方法 */ }
}

export function play(event, { set, force } = {}) {
  if (state.haptic && !force) buzz(event);
  if (!state.on && !force) return;
  try {
    if (!ctx) {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      master = ctx.createGain();
      master.gain.value = state.vol;
      master.connect(ctx.destination);
    }
    if (ctx.state === "suspended") ctx.resume();
    const now = ctx.currentTime;
    // 试听（设置里点音色、试听按钮、拖音量）：先把上一次还没响完的试听快速收掉，不让两种音色叠在一起
    if (force) {
      if (preview) { preview.gain.cancelScheduledValues(now); preview.gain.setValueAtTime(preview.gain.value, now); preview.gain.linearRampToValueAtTime(0, now + 0.04); }
      preview = ctx.createGain();
      preview.connect(master);
      schedule(ctx, preview, event, set || state.set, now + 0.045);
      return;
    }
    schedule(ctx, master, event, set || state.set, now + 0.005);
  } catch { /* 没有音频设备时静默 */ }
}

// 普通按钮、标签、开关的点击音。评分、翻牌等有自己声音的元素标了 data-sfx="none"。
document.addEventListener("pointerdown", (e) => {
  if (!state.on && !state.haptic) return;
  const el = e.target.closest?.("button, a, .book, .book-pick, [role=switch], .drop");
  if (!el || el.disabled || el.closest("[data-sfx=none]")) return;
  play(el.matches("[role=switch]") ? "toggle" : "tap");
}, true);
