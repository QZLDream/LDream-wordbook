// 启动、路由、顶部导航。
import { api } from "./api.js";
import { applyFonts } from "./fonts.js";
import { $, $$, h, fail, ms, layerOpen, toast, icons } from "./ui.js";
import * as sfx from "./sfx.js";

const routes = {
  home: () => import("./pages/home.js"),
  review: () => import("./pages/review.js"),
  library: () => import("./pages/library.js"),
  stats: () => import("./pages/stats.js"),
  settings: () => import("./pages/settings.js"),
};

export const app = { settings: {}, info: {}, keyHandler: null };

// 按设置算出应该是亮还是暗。页面上的 data-theme 在换肤动画开始后才改，所以开关的状态要以这里为准
export const isDarkMode = (s = app.settings) => s.theme === "dark" || (s.theme === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);

export function applySettings(s) {
  app.settings = s;
  const dark = isDarkMode(s);
  const root = document.documentElement;
  const theme = dark ? "dark" : "light", palette = s.palette === "silver" ? "silver" : "vermilion";
  root.dataset.motion = s.motion === "reduced" ? "reduced" : "full";
  const look = () => {
    root.dataset.theme = theme; root.dataset.palette = palette;
    const btn = $("#themeBtn");
    if (btn) btn.innerHTML = dark ? icons.sun : icons.moon;
  };
  if (root.dataset.theme !== theme || root.dataset.palette !== palette) swapLook(look); else look();
  applyFonts(s, app.info.user_fonts || []);
  sfx.configure(s);
  app.lookReady = true;
}

// 换主题或明暗：整屏一起淡入淡出。
// 各元素自己的颜色过渡时长不同，背景渐变又没法过渡，直接切会出现导航栏和页面一先一后变色。
// 这里先关掉所有过渡，让新外观一步到位，再由视图过渡把新旧两张画面整体交叉淡化。
let swapping = null;
function swapLook(change) {
  const root = document.documentElement;
  if (!app.lookReady || !document.startViewTransition || root.dataset.motion === "reduced") { change(); return; }
  swapping?.skipTransition();
  root.classList.add("look-swap");
  // 开关单独成层、不参与整屏淡化：它保留自己的滑动和变色动画，看起来和以前一样顺
  // 旧画面里的开关直接隐藏，新画面是实时的，所以开关自己的过渡照常播放
  // 只挑完整露在导航栏下方的开关，被导航栏盖住一半的若单独成层会浮到导航栏上面
  const top = document.querySelector(".nav")?.getBoundingClientRect().bottom || 0;
  const live = [...document.querySelectorAll(".toggle")].filter((el) => {
    const r = el.getBoundingClientRect();
    return r.width && r.top >= top && r.bottom <= innerHeight;
  });
  const css = document.createElement("style");
  css.textContent = live.map((el, i) => {
    el.style.viewTransitionName = "live-toggle-" + i;
    return `::view-transition-old(live-toggle-${i}){display:none}::view-transition-new(live-toggle-${i}){animation:none}`;
  }).join("");
  document.head.append(css);
  const t = (swapping = document.startViewTransition(change));
  t.finished.finally(() => {
    live.forEach((el) => (el.style.viewTransitionName = ""));
    css.remove();
    if (swapping === t) { swapping = null; root.classList.remove("look-swap"); }
  });
}

// 导航栏右上角的暗色开关：在亮色和暗色之间切换，并记住选择
async function toggleTheme() {
  const dark = document.documentElement.dataset.theme === "dark";
  applySettings({ ...app.settings, theme: dark ? "light" : "dark" });
  document.dispatchEvent(new CustomEvent("shici-settings")); // 设置页的开关立刻跟着动，不等保存完成
  try { applySettings((await api("settings_set", { theme: dark ? "light" : "dark" })).settings); } catch (e) { fail(e); }
  document.dispatchEvent(new CustomEvent("shici-settings"));
}

export async function refreshNav(counts) {
  try {
    const c = counts || (await api("home")).counts;
    const all = c.done + c.total;
    $("#navProgText").textContent = `${c.done} / ${all}`;
    $("#navProgBar").style.transform = `scaleX(${all ? c.done / all : 0})`;
  } catch { /* 导航进度拿不到不影响使用 */ }
}

function moveInk(name) {
  const on = $(`#tabs a[data-tab="${name}"]`);
  $$("#tabs a").forEach((a) => a.classList.toggle("on", a === on));
  const ink = $("#tabInk");
  if (!on) return (ink.style.width = "0");
  ink.style.width = on.offsetWidth - 36 + "px";
  ink.style.transform = `translateX(${on.offsetLeft + 18}px)`;
}

let current = null, seq = 0;
async function route() {
  const [, name = "home", query = ""] = location.hash.match(/^#\/(\w+)\??(.*)$/) || [];
  if (!routes[name]) return (location.hash = "#/home");
  const my = ++seq;
  moveInk(name);
  const view = $("#view");
  const old = current;
  current = null;
  app.keyHandler = null;
  if (old) {
    old.cleanup?.();
    old.el.classList.add("leaving");
    await new Promise((r) => setTimeout(r, ms(240)));
    old.el.remove();
  }
  if (my !== seq) return;
  const el = h("section", { class: "page" });
  view.append(el);
  try {
    const mod = await routes[name]();
    const cleanup = await mod.mount(el, Object.fromEntries(new URLSearchParams(query)));
    if (my !== seq) { cleanup?.(); el.remove(); return; }
    current = { el, cleanup };
  } catch (e) {
    console.error(e);
    el.append(h("div", { class: "page-pad" }, h("p", { class: "label", text: "ERROR" }), h("p", { class: "h3", style: { "margin-top": "12px" }, text: e.message })));
    current = { el };
  }
}

document.addEventListener("keydown", (e) => {
  if (layerOpen()) return;
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
  if (app.keyHandler?.(e, typing)) e.preventDefault();
});

document.addEventListener("shici-toast", (e) => toast(e.detail, 9000));

async function boot() {
  const now = new Date();
  $("#navDate").textContent = `${now.getFullYear()}.${String(now.getMonth() + 1).padStart(2, "0")}.${String(now.getDate()).padStart(2, "0")} ${["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"][now.getDay()]}`;
  try {
    app.info = await api("bootstrap");
    applySettings(app.info.settings);
  } catch (e) { fail(e); }
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => applySettings(app.settings));
  $("#themeBtn").addEventListener("click", toggleTheme);
  addEventListener("hashchange", route);
  addEventListener("resize", () => moveInk((location.hash.match(/^#\/(\w+)/) || [])[1] || "home"));
  if (!/^#\/\w+/.test(location.hash)) history.replaceState(null, "", "#/home");
  document.fonts?.ready.then(() => moveInk((location.hash.match(/^#\/(\w+)/) || [])[1] || "home"));
  route();
  refreshNav();
}
boot();
