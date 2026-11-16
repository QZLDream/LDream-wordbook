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
  // 和「最近一次要求的外观」比，而不是和页面上的 data-theme 比：
  // 换肤动画要等下一帧截好旧画面才真正改 data-theme，这期间后台的保存结果先回来的话，
  // 读 data-theme 会以为还没换、再触发一次换肤，把正在播的淡入淡出跳过（看起来就是“有时候没动画、直接闪过去”）
  const key = theme + "/" + palette;
  if (key !== wantLook) { wantLook = key; swapLook(look); } else if (!swapping) look();
  applyFonts(s, app.info.user_fonts || []);
  sfx.configure(s);
  app.lookReady = true;
}

// 换主题或明暗：整屏一起淡入淡出。
// 各元素自己的颜色过渡时长不同，背景渐变又没法过渡，直接切会出现导航栏和页面一先一后变色。
// 这里先关掉所有过渡，让新外观一步到位，再由视图过渡把新旧两张画面整体交叉淡化。
let swapping = null, wantLook = null;
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
let themeSeq = 0;
async function toggleTheme() {
  const theme = isDarkMode() ? "light" : "dark";  // 以设置为准：动画进行中 data-theme 可能还是旧的
  const my = ++themeSeq;
  applySettings({ ...app.settings, theme });
  document.dispatchEvent(new CustomEvent("shici-settings")); // 设置页的开关立刻跟着动，不等保存完成
  try {
    const r = await api("settings_set", { theme });
    // 连点时，前一次的保存结果可能在后一次点击之后才回来：只认最后一次，不然会先跳回去再跳回来（闪屏）
    if (my === themeSeq) applySettings(r.settings);
  } catch (e) { fail(e); }
  if (my === themeSeq) document.dispatchEvent(new CustomEvent("shici-settings"));
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
  // 自动检查更新：启动几秒后在后台问一次，有新版本才提示
  if (app.settings?.update_check) setTimeout(() => import("./update.js").then((m) => m.checkUpdate(false)), 4000);
}
boot();
