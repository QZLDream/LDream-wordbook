// 启动、路由、顶部导航。
import { api } from "./api.js";
import { applyFonts } from "./fonts.js";
import { $, $$, h, fail, ms, layerOpen, toast, icons, openLayer, gpuRenderer, closeTopLayer, fitTerms } from "./ui.js";
import * as sfx from "./sfx.js";

const routes = {
  home: () => import("./pages/home.js"),
  review: () => import("./pages/review.js"),
  library: () => import("./pages/library.js"),
  stats: () => import("./pages/stats.js"),
  settings: () => import("./pages/settings.js"),
};

export const app = { settings: {}, info: {}, keyHandler: null, backHook: null };  // backHook：页面自己处理返回键（比如退出多选）

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
  if (key !== wantLook) {
    wantLook = key; swapLook(look);
    // 窗口底色跟着换：偶尔有一帧来不及画、或者拉大窗口露出新区域时，露出来的是当前主题的颜色，而不是启动时那个主题的
    api("look", { dark, palette }).catch(() => {});
    if (window.ShiciAndroid) requestAnimationFrame(() => setTimeout(() => syncBars(dark), ms(420)));
  } else if (!swapping) look();
  applyFonts(s, app.info.user_fonts || []);
  sfx.configure(s);
  app.lookReady = true;
}

// 安卓版：手机顶部状态栏、底部导航条的颜色跟着顶栏和底部标签栏换
function cssHex(c) {
  const m = c.match(/^rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)/) || c.match(/^color\(srgb ([\d.]+) ([\d.]+) ([\d.]+)/);
  if (!m) return null;
  const k = c.startsWith("color(") ? 255 : 1;
  return "#" + m.slice(1, 4).map((v) => Math.round(+v * k).toString(16).padStart(2, "0")).join("");
}
function syncBars(dark) {
  const bg = (sel) => cssHex(getComputedStyle($(sel) || document.body).backgroundColor) || cssHex(getComputedStyle(document.body).backgroundColor);
  const top = bg(".nav"), bottom = bg("#tabs");
  if (top && bottom) try { window.ShiciAndroid.setBars(top, bottom, dark); } catch { /* 旧版外壳没有这个方法 */ }
}
// 长单词自动缩小到一行：页面里新出现的单词、窗口大小变化时都量一次
let fitT = 0;
const refit = () => { clearTimeout(fitT); fitT = setTimeout(() => requestAnimationFrame(() => fitTerms()), 30); };
new MutationObserver((ms) => { if (ms.some((m) => [...m.addedNodes].some((n) => n.nodeType === 1 && (n.matches(".term") || n.querySelector?.(".term"))))) refit(); })
  .observe(document.body, { childList: true, subtree: true });
addEventListener("resize", refit);
document.fonts?.ready.then(refit);
// 安卓返回键：先关最上面的弹窗/抽屉，再回到“今日”；已经在“今日”时返回 false，由外壳把程序退到后台
window.__shiciBack = () => {
  if (closeTopLayer()) return true;
  if (app.backHook) { app.backHook(); return true; }
  if (!/^#\/home\b/.test(location.hash) && location.hash) { location.hash = "#/home"; return true; }
  return false;
};

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
  // 手机上底部还有标签栏，滚动区域在标签栏上面就被裁掉了：被裁掉（或被盖住）的开关不能单独成层，否则会浮到标签栏上面
  const top = document.querySelector(".nav")?.getBoundingClientRect().bottom || 0;
  const tabsTop = document.querySelector("#tabs")?.getBoundingClientRect().top ?? innerHeight;
  const bottom = tabsTop > innerHeight / 2 ? Math.min(innerHeight, tabsTop) : innerHeight;
  const live = [...document.querySelectorAll(".toggle")].filter((el) => {
    const r = el.getBoundingClientRect();
    const clip = el.closest(".scroll, .page-pad, .library, .home, .rv-stage, .sheet-body, .drawer")?.getBoundingClientRect();
    return r.width && r.top >= Math.max(top, clip?.top ?? 0) && r.bottom <= Math.min(bottom, clip?.bottom ?? innerHeight);
  });
  const css = document.createElement("style");
  css.textContent = live.map((el, i) => {
    el.style.viewTransitionName = "live-toggle-" + i;
    return `::view-transition-old(live-toggle-${i}){display:none}::view-transition-new(live-toggle-${i}){animation:none}`;
  }).join("");
  document.head.append(css);
  // 新外观如果用到还没载入的字体，等它载入完再开始淡化（最多等 0.4 秒），不然文字会先用别的字体画出来、淡到一半再跳一下
  const t = (swapping = document.startViewTransition(async () => {
    change();
    void document.body.offsetHeight;
    await Promise.race([document.fonts.ready, new Promise((r) => setTimeout(r, 400))]);
  }));
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

// 换页：旧页淡出 240ms 后再放新页。
// 连续快速点导航时要保证同一时间只有一页在屏幕上：
//   - 还在淡出的旧页：新页等它淡完再进来（以前新页会直接叠上去，两页重影，看起来像闪屏）；
//   - 还没加载完的上一页：直接撤掉，不让它和新页叠在一起。
let current = null, seq = 0, pending = null, leaveDone = Promise.resolve();
async function route() {
  const [, name = "home", query = ""] = location.hash.match(/^#\/(\w+)\??(.*)$/) || [];
  if (!routes[name]) return (location.hash = "#/home");
  const my = ++seq;
  moveInk(name);
  const view = $("#view");
  if (pending) { pending.remove(); pending = null; }
  const old = current;
  current = null;
  app.keyHandler = null; app.backHook = null;
  if (old) {
    old.cleanup?.();
    old.el.classList.add("leaving");
    leaveDone = new Promise((r) => setTimeout(() => { old.el.remove(); r(); }, ms(240)));
  }
  await leaveDone;
  if (my !== seq) return;
  const el = h("section", { class: "page" });
  pending = el;
  view.append(el);
  try {
    const mod = await routes[name]();
    const cleanup = await mod.mount(el, Object.fromEntries(new URLSearchParams(query)));
    if (my !== seq) { cleanup?.(); el.remove(); return; }
    pending = null;
    current = { el, cleanup };
  } catch (e) {
    if (my !== seq) { el.remove(); return; }
    console.error(e);
    pending = null;
    el.append(h("div", { class: "page-pad" }, h("p", { class: "label", text: "ERROR" }), h("p", { class: "h3", style: { "margin-top": "12px" }, text: e.message })));
    current = { el };
  }
}

// 链接和图片不能被拖出窗口（拖出去会变成一个网址小方块，没有意义）
document.addEventListener("dragstart", (e) => { if (e.target.closest?.("a, img, svg")) e.preventDefault(); });
// 文件或链接拖到导入框以外的地方松手时，窗口会直接打开那个文件、整个程序界面被换掉：拦下来
for (const t of ["dragover", "drop"]) document.addEventListener(t, (e) => { if (!e.target.closest?.(".drop")) e.preventDefault(); });

document.addEventListener("keydown", (e) => {
  if (layerOpen()) return;
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
  if (app.keyHandler?.(e, typing)) e.preventDefault();
});

document.addEventListener("shici-toast", (e) => toast(e.detail, 9000));

// 刚换了画面渲染方式或显卡：请用户确认画面正常。看不见这个窗口（画面坏了）就没法点，15 秒后自动换回并重启
function confirmRender() {
  let left = 15, kept = false, timer = 0;
  const count = h("b", { text: String(left) });
  const revert = async () => {
    clearInterval(timer);
    try { await api("settings_set", { render: "auto", gpu: "auto" }); await api("restart"); } catch (e) { fail(e); }
  };
  openLayer("modal", (close) => [
    h("div", { class: "modal-head" }, h("div", {}, h("span", { class: "label", text: "DISPLAY · 画面" }),
      h("h3", { class: "h2", style: { "margin-top": "10px" }, text: "画面设置已更改" }))),
    h("div", { class: "modal-body" }, h("p", { class: "note" }, "画面显示正常吗？", count, " 秒后没有确认，会自动换回原来的方式并重启。")),
    h("div", { class: "modal-foot" },
      h("button", { class: "btn ghost sm", onclick: () => { kept = true; close(); revert(); } }, "换回去"),
      h("button", { class: "btn sm", autofocus: true, onclick: () => { kept = true; clearInterval(timer); api("render_confirm").catch(() => {}); close(); toast("已保留新的渲染方式"); } }, "正常，保留")),
  ], { width: "460px", onClose: () => { if (!kept) { kept = true; clearInterval(timer); api("render_confirm").catch(() => {}); } } });
  timer = setInterval(() => { left -= 1; count.textContent = String(left); if (left <= 0) revert(); }, 1000);
}

// 局域网同步：从别的设备合并进来新进度时，首页 / 统计页重新画一下，并轻轻提示一声
let syncSeen = Math.floor(Date.now() / 1000) - 1;
async function watchSync() {
  if (app.settings.lan_sync && !document.hidden) {
    try {
      const s = await api("sync_status");
      if (s.merged_at > syncSeen && s.merged_changes) {
        const name = (location.hash.match(/^#\/(\w+)/) || [])[1] || "home";
        if ((name === "home" || name === "stats") && !layerOpen()) route();
        refreshNav();
        if (name !== "review") toast(`已和「${s.merged_from}」同步了学习进度`);
      }
      syncSeen = Math.max(syncSeen, s.merged_at || 0);
    } catch { /* 下次再看 */ }
  }
  setTimeout(watchSync, 4000);
}

async function boot() {
  const now = new Date();
  $("#navDate").textContent = `${now.getFullYear()}.${String(now.getMonth() + 1).padStart(2, "0")}.${String(now.getDate()).padStart(2, "0")} ${["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"][now.getDay()]}`;
  try {
    app.info = await api("bootstrap");
    window.__shiciDesktop = !!app.info.desktop;
    if (app.info.android) document.documentElement.dataset.shell = "android";
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
  if (app.info.can_restart) {
    // 界面真正画出来了：告诉桌面程序这次的画面设置没问题（没报告就说明闪退或白屏，下次启动会自动换回）
    requestAnimationFrame(() => requestAnimationFrame(() => api("display_ok", { renderer: gpuRenderer().replace(/^未知$/, "") }).catch(() => {})));
  }
  if (app.info.display_reverted) toast("上次的画面设置（渲染方式 / 显卡）没能正常打开程序，已自动换回「自动」。", 7000);
  if (app.info.render_trial) confirmRender();
  // 内置的四套字体提前载入。朱橙用衬线体、简约白用无衬线体，不提前载入的话，
  // 每次打开程序后第一次换主题（或第一次遇到日语词）时字体才开始读，文字会先用系统字体画一下再换过来，看起来像闪了一下
  setTimeout(() => {
    for (const f of ['700 1em "Shici Serif"', '700 1em "Shici Serif JP"', '500 1em "Shici Sans"', '500 1em "Shici Mono"']) document.fonts.load(f, "词あa").catch(() => {});
  }, 1200);
  // 自动检查更新：启动几秒后在后台问一次，有新版本才提示
  if (app.settings?.update_check) setTimeout(() => import("./update.js").then((m) => m.checkUpdate(false)), 4000);
  setTimeout(watchSync, 4000);
}
boot();
