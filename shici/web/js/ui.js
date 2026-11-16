// 界面小工具：创建元素、图标、提示、浮层、数字滚动等。

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function h(tag, attrs, ...kids) {
  const el = tag === "svg" || attrs?.svg ? document.createElementNS("http://www.w3.org/2000/svg", tag) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false || k === "svg") continue;
    if (k === "class") el.setAttribute("class", v);
    else if (k === "text") el.textContent = v;
    else if (k === "html") el.innerHTML = v;
    else if (k === "style" && typeof v === "object") for (const [p, val] of Object.entries(v)) el.style.setProperty(p, val);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(kid));
  return el;
}

// 用新内容替换元素的全部子节点（和 h 一样接受嵌套数组，忽略 null / false）
export function fill(el, ...kids) {
  el.replaceChildren(...kids.flat(Infinity).filter((k) => k != null && k !== false));
  return el;
}

const I = (d, extra = "") => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" ${extra}>${d}</svg>`;
export const icons = {
  speaker: I('<path d="M4 9.5v5h3.5L12 18V6L7.5 9.5H4z"/><path d="M15.5 9a4 4 0 0 1 0 6"/><path d="M18 6.5a7.5 7.5 0 0 1 0 11"/>'),
  close: I('<path d="M6 6l12 12M18 6L6 18"/>'),
  search: I('<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4 4"/>'),
  upload: I('<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>'),
  moon: I('<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>'),
  sun: I('<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/>'),
  undo: I('<path d="M9 7L4 12l5 5"/><path d="M4 12h10a6 6 0 0 1 0 12"/>', 'viewBox="0 0 24 26"'),
};
export const icon = (name, attrs = {}) => h("span", { class: "ico", html: icons[name], style: { display: "inline-grid" }, ...attrs });

export const reduced = () => document.documentElement.dataset.motion === "reduced" || matchMedia("(prefers-reduced-motion: reduce)").matches;
export const ms = (n) => (reduced() ? 0 : n);
export const wait = (n) => new Promise((r) => setTimeout(r, ms(n)));
export const EASE = "cubic-bezier(.22,1,.36,1)";

export function toast(msg, life = 2600) {
  const el = h("div", { class: "toast", text: msg });
  $("#toasts").append(el);
  setTimeout(() => exit(el, [{ opacity: 0, transform: "translate3d(0, 8px, 0)" }], 320).then(() => el.remove()), life);
}

// 退场动画。入场用的 CSS 动画带 fill-mode: both，会一直压着元素的最终状态，
// 所以退场不能靠加类名触发过渡（那样会直接消失），这里用脚本动画从“当前样子”过渡到 to。
export function exit(el, to, dur, easing = "cubic-bezier(.4, 0, .9, .6)") {
  const d = ms(dur);
  const cs = getComputedStyle(el);
  const from = { opacity: cs.opacity, transform: cs.transform === "none" ? "none" : cs.transform };
  el.style.animation = "none";
  if (!d || !el.animate) return Promise.resolve();
  const anim = el.animate([from, ...to], { duration: d, easing, fill: "forwards" });
  return anim.finished.catch(() => {});
}

// 入场动画先暂停，等内容排好版、画出第一帧之后再开始计时，免得打开时第一帧跳一大截
function startWhenPainted(...els) {
  els.forEach((el) => (el.style.animationPlayState = "paused"));
  requestAnimationFrame(() => requestAnimationFrame(() => els.forEach((el) => (el.style.animationPlayState = "running"))));
}

export const fail = (e) => toast(e?.message || String(e), 4200);

// 抽屉 / 弹窗。build(close) 返回内容元素；按 Esc 或点遮罩关闭最上面一层。
const layers = [];
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && layers.length) { e.stopPropagation(); e.preventDefault(); layers[layers.length - 1](); }
}, true);
export function openLayer(kind, build, opts = {}) {
  const layer = $("#layer");
  const scrim = h("div", { class: "scrim" });
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    layers.splice(layers.indexOf(close), 1);
    scrim.style.pointerEvents = box.style.pointerEvents = "none";
    const out = kind === "drawer"
      ? exit(box, [{ transform: "translate3d(100%, 0, 0)" }], 380, "cubic-bezier(.55, 0, .75, .25)")
      : exit(box, [{ opacity: 0, transform: "translate(-50%, calc(-50% + 14px)) scale(.985)" }], 240);
    exit(scrim, [{ opacity: 0 }], kind === "drawer" ? 380 : 240, "ease-out");
    out.then(() => { scrim.remove(); box.remove(); opts.onClose?.(); });
  };
  const box = h("div", { class: kind, role: "dialog", "aria-modal": "true", tabindex: -1, style: opts.width ? { "--w": opts.width } : null }, build(close));
  // 每多开一层就整体往上叠：后打开的（比如抽屉里点“删除”弹出的确认框）一定在最上面，它的遮罩也会盖住下面的抽屉。
  // 不能只靠同一个 z-index 加上元素先后顺序——不同浏览器内核处理带 will-change 的元素时结果不一样。
  const depth = layers.length;
  scrim.style.zIndex = String(100 + depth * 10);
  box.style.zIndex = String(101 + depth * 10);
  scrim.addEventListener("click", close);
  layers.push(close);
  layer.append(scrim, box);
  startWhenPainted(scrim, box);
  setTimeout(() => {
    const el = box.querySelector("[autofocus]") || box;
    // 按钮是程序替用户聚焦的：不画键盘焦点框（启动时还没点过鼠标，浏览器会把它当成键盘操作画一圈蓝框）。
    // 用户之后按了键（比如 Tab）再显示，方便键盘操作
    if (el.tagName === "BUTTON") {
      el.dataset.quietFocus = "";
      const loud = (e) => { if (e.key !== "Enter" && e.key !== " ") { delete el.dataset.quietFocus; removeEventListener("keydown", loud, true); } };
      addEventListener("keydown", loud, true);
    }
    el.focus?.({ preventScroll: true });
  }, 60);
  return { close, box };
}
// 确认框：返回 Promise<boolean>
export function ask(title, text, { ok = "确定", danger = false } = {}) {
  return new Promise((resolve) => {
    let answer = false;
    openLayer("modal", (close) => [
      h("div", { class: "modal-head" }, h("h3", { class: "h3", style: { "font-size": "22px" }, text: title })),
      h("div", { class: "modal-body" }, h("p", { class: "mute", text })),
      h("div", { class: "modal-foot" }, h("button", { class: "btn ghost sm", onclick: close }, "取消"),
        h("button", { class: "btn sm" + (danger ? " danger" : ""), autofocus: true, onclick: () => { answer = true; close(); } }, ok)),
    ], { width: "440px", onClose: () => resolve(answer) });
  });
}
export const layerOpen = () => $("#layer").childElementCount > 0;

export function countUp(el, to, { dur = 1100, fmt = (v) => Math.round(v).toLocaleString("en-US") } = {}) {
  if (reduced() || !isFinite(to)) { el.textContent = fmt(to); return; }
  const t0 = performance.now();
  const step = (t) => {
    const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 4);
    el.textContent = fmt(to * e);
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// 鼠标悬停提示：元素上写 data-tip="文字"
let tipEl;
export function bindTips(root) {
  if (!tipEl) { tipEl = h("div", { class: "tip" }); document.body.append(tipEl); }
  root.addEventListener("mousemove", (e) => {
    const t = e.target.closest?.("[data-tip]");
    if (!t) return tipEl.classList.remove("show");
    tipEl.innerHTML = t.dataset.tip;
    tipEl.style.left = Math.max(70, Math.min(innerWidth - 70, e.clientX)) + "px";
    tipEl.style.top = e.clientY + "px";
    tipEl.classList.add("show");
  });
  root.addEventListener("mouseleave", () => tipEl.classList.remove("show"));
}
export const hideTip = () => tipEl?.classList.remove("show");

// 把单词拆成逐字母升起的动画
export function letters(text) {
  let n = 0;
  return [...text].map((c) => c === " " ? " " : h("span", { class: "ch" }, h("i", { style: { "--n": n++ }, text: c })));
}

// “vt. 放弃, 抛弃\nn. 放任” → 带词性标签的几行。没有任何词性标签时整块去掉标签列（父元素加 plain 类）。
export function defLines(definition, max = 6) {
  const lines = (definition || "").split("\n").map((s) => s.trim()).filter(Boolean).slice(0, max);
  if (!lines.length) return [h("p", { class: "mute", text: "还没有释义，可以在词库里补上。" })];
  return lines.map((ln, i) => {
    const m = ln.match(/^((?:[a-z]{1,5}\.)(?:\s*[/&]\s*[a-z]{1,5}\.)*|\[[^\]]{1,6}\])\s*(.+)$/i);
    return h("div", { class: "def rise", style: { "--i": i } }, h("span", { class: "pos", text: m ? m[1].replace(/\s/g, "") : "" }), h("span", { text: m ? m[2] : ln }));
  });
}
export function defBlock(definition, max = 6, attrs = {}) {
  const lines = defLines(definition, max);
  const plain = !lines.some((el) => el.querySelector?.(".pos")?.textContent);
  return h("div", { ...attrs, class: `defs ${attrs.class || ""}${plain ? " plain" : ""}` }, lines);
}

export function exampleEl(ex, term, lang = "en") {
  const p = h("p", { lang: lang === "ja" ? "ja" : null });
  const hit = (start, len) => { p.append(ex.en.slice(0, start), h("mark", { text: ex.en.slice(start, start + len) }), ex.en.slice(start + len)); };
  if (lang === "ja") {
    // 动词、形容词会变形：从完整词形开始，逐字去掉词尾，直到在句子里找到
    let stem = term.replace(/[()（）～〜]/g, ""), at = ex.en.indexOf(stem);
    while (at < 0 && stem.length > 1) { stem = stem.slice(0, -1); at = ex.en.indexOf(stem); }
    if (at >= 0 && (stem.length > 1 || /[\u3400-\u9fff]/.test(stem))) hit(at, stem.length); else p.append(ex.en);
  } else {
    const stem = term.length > 4 ? term.slice(0, -2) : term;
    const re = new RegExp("\\b(" + stem.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "[a-z]*)", "gi");
    let last = 0, m;
    while ((m = re.exec(ex.en))) { p.append(ex.en.slice(last, m.index), h("mark", { text: m[1] })); last = m.index + m[1].length; }
    p.append(ex.en.slice(last));
  }
  // 例句朗读：点小喇叭读整句（第一次要联网取，之后存在本机）
  const say = h("button", { class: "ex-say", type: "button", title: "朗读例句", "aria-label": "朗读例句", html: icons.speaker });
  say.addEventListener("click", async (e) => {
    e.stopPropagation();
    say.classList.add("playing");
    const { speak } = await import("./api.js");
    await speak(ex.en, lang, "sentence");
    setTimeout(() => say.classList.remove("playing"), ms(1400));
  });
  p.append(" ", say);
  // 机器翻译的译文后面标一个小小的「机翻」
  const tr = ex.zh ? h("p", { lang: /[\u3040-\u30ff]/.test(ex.zh) ? "ja" : null }, ex.zh, ex.mt ? h("span", { class: "mt-tag", title: "这句译文是机器翻译的，仅供参考", text: "机翻" }) : null) : null;
  return h("div", { class: "ex" }, p, tr);
}

export function fmtDue(ts, now) {
  if (!ts) return "—";
  const d = (ts - now) / 86400;
  if (d <= 0) return "到期";
  if (d < 1) return d * 24 < 1 ? Math.max(1, Math.round(d * 1440)) + " 分钟" : Math.round(d * 24) + " 小时";
  if (d < 30.5) return Math.round(d) + " 天";
  if (d < 365) return (d / 30.4).toFixed(1).replace(/\.0$/, "") + " 个月";
  return (d / 365).toFixed(1).replace(/\.0$/, "") + " 年";
}
export const pct = (v, digits = 0) => (v == null ? "—" : (v * 100).toFixed(digits) + "%");
export const STATUS = { new: "未学", learning: "学习中", young: "复习中", mature: "已掌握", suspended: "已搁置" };
export const debounce = (fn, t = 220) => { let id; return (...a) => { clearTimeout(id); id = setTimeout(() => fn(...a), t); }; };

// 网页现在用的是哪张显卡（从 WebGL 读出来，比如 “NVIDIA GeForce RTX 4060 Ti”）
export function gpuRenderer() {
  try {
    const gl = document.createElement("canvas").getContext("webgl");
    const ext = gl && gl.getExtension("WEBGL_debug_renderer_info");
    let r = gl ? gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER) : "";
    gl?.getExtension("WEBGL_lose_context")?.loseContext();
    const m = r.match(/^ANGLE \((.*)\)$/);            // ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Ti (0x00002803) Direct3D11 vs_5_0 ps_5_0, D3D11)
    if (m) r = m[1].split(", ").length >= 2 ? m[1].split(", ")[1] : m[1];
    return r.replace(/\s*\(0x[0-9a-f]+\)/i, "").replace(/\s+(Direct3D\d+|OpenGL).*$/i, "").replace(/\/PCIe.*$/i, "").trim() || "未知";
  } catch { return "未知"; }
}

