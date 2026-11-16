// 图表：全部手写 SVG，不依赖第三方库。
// 约定：数据标记细、条形顶端 4px 圆角并贴着基线、网格和坐标轴淡化、文字用墨色而不是系列色，悬停显示数值。
import { h } from "./ui.js";

const S = (tag, attrs, ...kids) => h(tag, { svg: 1, ...attrs }, ...kids);
const css = (name) => `var(--${name})`;
const fmtDate = (iso) => { const [, m, d] = iso.split("-"); return `${+m}月${+d}日`; };

// FSRS 遗忘曲线公式（与后端一致）：R = (1 + f·t/S)^(-decay)
const DECAY = 0.1542, FACTOR = Math.pow(0.9, -1 / DECAY) - 1;
const recall = (t, s) => Math.pow(1 + FACTOR * t / s, -DECAY);

// 首页深色区的示意图：不复习会一路忘下去（虚线）；每次在保持率降到 90% 时复习，下一次就能隔得更久。
export function memoryIllustration() {
  // 示意图，不追求精确：粗线条、圆头，每次复习的“跳回顶部”做成圆角转折
  const W = 520, H = 250, days = 72, top = 22, bottom = H - 40, lo = 0.6;
  const x = (t) => (t / days) * W, y = (r) => top + (1 - (r - lo) / (1 - lo)) * (bottom - top);
  const reviews = [[0, 9], [9, 19], [28, 38], [66, 80]];  // [复习时间, 复习后的稳定度]：间隔 9 → 19 → 38 天
  const R = 11;                                            // 转折处的圆角半径（像素）
  const pts = (t0, s, t1) => { const out = []; for (let t = t0; t <= t1 + 1e-6; t += 0.4) out.push([x(t), y(recall(t - t0, s))]); return out; };
  const f = (v) => v.toFixed(1);
  let d = "";
  const dots = [];
  reviews.forEach(([t0, s], i) => {
    const t1 = reviews[i + 1]?.[0] ?? days;
    let seg = pts(t0, s, t1);
    if (i) {  // 从上一段的底部圆角拐上来，再圆角拐进这一段
      seg = seg.filter(([px]) => px >= x(t0) + R);
      d += `L${f(x(t0))} ${f(y(1) + R)}Q${f(x(t0))} ${f(y(1))} ${f(seg[0][0])} ${f(seg[0][1])}`;
      dots.push(S("circle", { cx: x(t0), cy: y(1) - 0.5, r: 6.5, fill: css("panel-accent"), stroke: css("panel"), "stroke-width": 3,
        style: { animation: `fade .6s ${[0, 1.25, 1.75, 2.75][i]}s both` } }));
    }
    const next = reviews[i + 1];
    if (next) seg = seg.filter(([px]) => px <= x(next[0]) - R);
    seg.forEach(([px, py], k) => (d += `${i === 0 && k === 0 ? "M" : "L"}${f(px)} ${f(py)}`));
    if (next) { const yEnd = y(recall(next[0] - t0, s)); d += `Q${f(x(next[0]))} ${f(yEnd)} ${f(x(next[0]))} ${f(yEnd - R)}`; }
  });
  let ghost = "";
  for (let t = 0; t <= days; t += 1) ghost += `${t ? "L" : "M"}${f(x(t))} ${f(y(recall(t, 9)))}`;
  const txt = { fill: css("on-panel-mute"), style: { font: "500 11.5px var(--mono)", "letter-spacing": ".08em" } };
  return S("svg", { viewBox: `-8 -8 ${W + 16} ${H + 8}`, role: "img", "aria-label": "遗忘曲线示意：每复习一次，下一次可以隔得更久" },
    S("line", { x1: 0, x2: W, y1: y(0.9), y2: y(0.9), stroke: css("panel-line"), "stroke-width": 1.5, "stroke-dasharray": "2 6", "stroke-linecap": "round" }),
    S("text", { x: W, y: y(0.9) + 18, "text-anchor": "end", ...txt }, "90%"),
    S("line", { x1: 0, x2: W, y1: bottom + 14, y2: bottom + 14, stroke: css("panel-line") }),
    S("path", { d: ghost, fill: "none", stroke: css("on-panel-mute"), "stroke-width": 2, "stroke-dasharray": "1 7", "stroke-linecap": "round", opacity: .75 }),
    S("text", { x: W, y: y(recall(days, 9)) + 20, "text-anchor": "end", ...txt }, "不复习"),
    S("path", { d, fill: "none", stroke: css("on-panel"), "stroke-width": 5, "stroke-linejoin": "round", "stroke-linecap": "round", pathLength: 1,
      style: { "stroke-dasharray": 1, "stroke-dashoffset": 1, animation: "slash 2.2s cubic-bezier(.65,0,.35,1) .8s both" } }),
    dots,
    ["今天", "9 天后", "28 天后", "66 天后"].map((t, i) => S("text", { x: x(reviews[i][0]), y: H - 6, "text-anchor": i ? "middle" : "start", ...txt }, t)),
  );
}

// 条形图。series: [{name, color, key}]；rows: [{label, tip, <key>: 数值…}]
export function barChart(rows, series, { height = 190, highlight = -1, every = 5 } = {}) {
  const W = 720, padL = 34, padB = 22, padT = 8, plotH = height - padB - padT, plotW = W - padL;
  const totals = rows.map((r) => series.reduce((a, s) => a + (r[s.key] || 0), 0));
  const max = Math.max(4, ...totals);
  const step = niceStep(max / 3), top = Math.ceil(max / step) * step;
  const bw = plotW / rows.length, w = Math.max(3, Math.min(22, bw - 4));
  const yv = (v) => padT + plotH - (v / top) * plotH;
  const svg = S("svg", { viewBox: `0 0 ${W} ${height}`, role: "img" });
  for (let v = 0; v <= top; v += step) {
    svg.append(S("line", { x1: padL, x2: W, y1: yv(v), y2: yv(v), stroke: css("line"), "stroke-width": 1 }),
      S("text", { x: padL - 8, y: yv(v) + 3.5, "text-anchor": "end" }, String(v)));
  }
  rows.forEach((r, i) => {
    const cx = padL + bw * i + bw / 2;
    const g = S("g", { class: "b", "data-tip": r.tip });
    g.append(S("rect", { class: "bar-hit", x: cx - bw / 2, y: padT, width: bw, height: plotH, fill: "transparent" }));
    let base = 0;
    series.forEach((s, si) => {
      const v = r[s.key] || 0;
      if (!v) return;
      const y1 = yv(base + v), hgt = Math.max(1.5, yv(base) - y1 - (base ? 2 : 0));
      const isTop = series.slice(si + 1).every((t) => !(r[t.key] || 0));
      const rad = isTop ? Math.min(4, w / 2, hgt) : 0;
      // 只有最上面一段的顶端是圆角；段与段之间留 2px 空隙
      g.append(S("path", { d: `M${cx - w / 2} ${y1 + hgt}V${y1 + rad}q0 ${-rad} ${rad} ${-rad}h${w - 2 * rad}q${rad} 0 ${rad} ${rad}V${y1 + hgt}z`,
        fill: i === highlight && series.length === 1 ? css("accent") : s.color,
        style: { "transform-origin": `0 ${yv(0)}px`, animation: `bar-up .9s cubic-bezier(.22,1,.36,1) ${i * 14}ms both` } }));
      base += v;
    });
    svg.append(g);
    if (i % every === 0 || i === rows.length - 1) svg.append(S("text", { x: cx, y: height - 5, "text-anchor": "middle" }, r.label));
  });
  return svg;
}
function niceStep(raw) {
  const p = Math.pow(10, Math.floor(Math.log10(Math.max(1, raw))));
  return [1, 2, 5, 10].map((m) => m * p).find((s) => s >= raw) || 10 * p;
}

// 单条遗忘曲线。points: [[天, 保持率]…]；marks: [{t, label, accent}]
export function curveChart(points, { retention = 0.9, marks = [], height = 200, width = 720, unit = "天" } = {}) {
  const W = width, padL = 40, padB = 24, padT = 12, plotH = height - padB - padT, plotW = W - padL - 10;
  const span = points[points.length - 1][0] || 1;
  const lo = Math.max(0, Math.floor(Math.min(retention, ...points.map((p) => p[1])) * 10 - 1) / 10);
  const x = (t) => padL + (t / span) * plotW, y = (r) => padT + (1 - (r - lo) / (1 - lo)) * plotH;
  const svg = S("svg", { viewBox: `0 0 ${W} ${height}`, role: "img" });
  for (let r = lo; r <= 1.0001; r += (1 - lo) > 0.45 ? 0.2 : 0.1) {
    svg.append(S("line", { x1: padL, x2: W - 10, y1: y(r), y2: y(r), stroke: css("line") }), S("text", { x: padL - 8, y: y(r) + 3.5, "text-anchor": "end" }, Math.round(r * 100) + "%"));
  }
  const ticks = niceStep(span / 5);
  for (let t = 0; t <= span + 1e-6; t += ticks) svg.append(S("text", { x: x(t), y: height - 5, "text-anchor": "middle" }, t ? `${+t.toFixed(1)} ${unit}` : "0"));
  svg.append(S("line", { x1: padL, x2: W - 10, y1: y(retention), y2: y(retention), stroke: css("accent"), "stroke-dasharray": "3 5", "stroke-width": 1.2 }),
    S("text", { x: W - 12, y: y(retention) - 6, "text-anchor": "end", style: { fill: css("accent") } }, `期望 ${Math.round(retention * 100)}%`));
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)} ${y(p[1]).toFixed(1)}`).join("");
  svg.append(S("path", { d: `${d}L${x(span)} ${y(lo)}L${x(0)} ${y(lo)}z`, fill: css("line"), style: { animation: "fade 1.2s .4s both" } }),
    S("path", { d, fill: "none", stroke: css("ink"), "stroke-width": 2, pathLength: 1, style: { "stroke-dasharray": 1, "stroke-dashoffset": 1, animation: "slash 1.6s cubic-bezier(.65,0,.35,1) .1s both" } }));
  const at = (t) => { const i = points.findIndex((p) => p[0] >= t); if (i <= 0) return points[0][1]; const [a, b] = [points[i - 1], points[i]]; return a[1] + (b[1] - a[1]) * (t - a[0]) / (b[0] - a[0] || 1); };
  marks.filter((m) => m.t <= span).forEach((m) => {
    const r = at(m.t);
    svg.append(S("g", { "data-tip": `${m.label}<br>${(r * 100).toFixed(0)}%`, style: { animation: "fade .6s 1.2s both" } },
      S("line", { x1: x(m.t), x2: x(m.t), y1: y(r), y2: y(lo), stroke: m.accent ? css("accent") : css("line-2"), "stroke-dasharray": "2 4" }),
      S("circle", { cx: x(m.t), cy: y(r), r: 12, fill: "transparent" }),
      S("circle", { cx: x(m.t), cy: y(r), r: 5, fill: m.accent ? css("accent") : css("ink"), stroke: css("card"), "stroke-width": 2 }),
      S("text", { x: Math.min(W - 60, x(m.t) + 10), y: y(r) - 10, style: { fill: css("ink-2") } }, m.label)));
  });
  return svg;
}

export function heatmap(days, todayIso) {
  const max = Math.max(1, ...days.map((d) => d.count));
  const level = (n) => (n === 0 ? 0 : Math.min(4, 1 + Math.floor((n / max) * 3.999 * 0.999)));
  const first = new Date(days[0].date + "T00:00:00");
  const pad = (first.getDay() + 6) % 7;  // 周一开头
  return h("div", { class: "heat" },
    Array.from({ length: pad }, () => h("i", { class: "pad" })),
    days.map((d, i) => h("i", { "data-l": level(d.count), class: d.date === todayIso ? "today" : null,
      "data-tip": `${fmtDate(d.date)}<br>${d.count} 次`, style: { animation: `fade .5s ${Math.floor(i / 7) * 16}ms both` } })));
}
export { fmtDate };
