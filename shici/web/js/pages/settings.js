// 设置：学习量、发音、外观、音效、数据（含进度密钥）。
import { api, speak } from "../api.js";
import { h, fill, icons, toast, fail, ask, openLayer, gpuRenderer } from "../ui.js";
import { app, applySettings, refreshNav, isDarkMode } from "../app.js";
import * as sfx from "../sfx.js";
import { family } from "../fonts.js";
import { openLink, openNetdisk, checkUpdate } from "../update.js";

export async function mount(root) {
  const s = { ...app.settings };
  const syncs = [];   // 设置在别处被改动（比如导航栏的暗色开关）时，刷新这里的控件
  const set = async (patch, quiet) => {
    try {
      const r = await api("settings_set", patch);
      Object.assign(s, r.settings);
      applySettings(r.settings);
      syncs.forEach((fn) => fn());
      refreshNav();
      if (!quiet) toast("已保存");
    } catch (e) { fail(e); }
  };
  const askRestart = async () => {
    if (await ask("重启程序吗？", "这项设置要重启才生效。正在背的进度都已经保存了。", { ok: "立即重启" })) api("restart").catch(fail);
  };
  const gpuName = h("span", { class: "path", text: gpuRenderer() });
  const row = (title, desc, ctl, cls = "") => h("div", { class: "set-row " + cls }, h("div", { class: "txt" }, h("b", { text: title }), desc ? h("span", { text: desc }) : null), h("div", { class: "ctl" }, ctl));
  const seg = (key, opts, after, quiet) => {
    // quiet：点了会自己出声的选项（音色），不再叠加通用的点击音
    const el = h("div", { class: "seg", "data-sfx": quiet ? "none" : null }, opts.map(([k, t]) => h("button", { "data-k": k, text: t,
      onclick: async () => { await set({ [key]: k }, true); after?.(k); } })));
    const sync = () => [...el.children].forEach((b) => b.classList.toggle("on", b.dataset.k === s[key]));
    syncs.push(sync); sync();
    return el;
  };
  const toggle = (get, onChange, label) => {
    const el = h("button", { class: "toggle", role: "switch", "aria-label": label, onclick: () => onChange(el.getAttribute("aria-checked") !== "true") });
    const sync = () => el.setAttribute("aria-checked", String(!!get()));
    syncs.push(sync); sync();
    return el;
  };
  const flag = (key, label) => toggle(() => s[key], (v) => set({ [key]: v }, true), label);
  const slider = (key, min, max, step, fmt, scale = 1, after) => {
    const val = h("span", { class: "val", text: fmt(s[key]) });
    const el = h("input", { type: "range", min, max, step, value: s[key] * scale, "aria-label": key });
    const paint = () => el.style.setProperty("--fill", ((el.value - min) / (max - min)) * 100 + "%");
    el.addEventListener("input", () => { val.textContent = fmt(el.value / scale); paint(); });
    el.addEventListener("change", async () => { await set({ [key]: el.value / scale }, true); after?.(); });
    paint();
    return [el, val];
  };
  const group = (i, label, ...rows) => h("div", { class: "set-group rise", style: { "--i": i } }, h("span", { class: "label", text: label }), rows);
  const act = (label, fn, cls = "ghost") => h("button", { class: `btn sm ${cls}`, onclick: fn }, label);
  const isDark = () => isDarkMode(s);

  // 音效相关的几行，关闭时变灰
  const sfxRows = [
    row("音色", "前几种偏低沉；选一下就能听到。", seg("sfx_set", Object.entries(sfx.SETS).map(([k, v]) => [k, v.name]), (k) => sfx.play("good", { set: k, force: true }), true), "sub"),
    row("音量", null, slider("sfx_volume", 0, 100, 5, (v) => `${Math.round(v)}%`, 1, () => sfx.play("good", { force: true })), "sub"),
    row("试听", "不同操作的声音略有区别：答得越好音越高。", [["翻牌", "flip"], ["忘记", "again"], ["认识", "good"], ["完成", "done"]].map(([t, ev]) =>
      h("button", { class: "btn ghost sm", "data-sfx": "none", onclick: () => sfx.play(ev, { force: true }) }, t)), "sub"),
  ];
  const paintSfx = () => sfxRows.forEach((r) => r.classList.toggle("off", !s.sfx));
  syncs.push(paintSfx);

  // ---- 字体：两个下拉框（标题和单词 / 正文）、导入字体、已导入的列表、预览 ----
  const fontsBox = h("div");
  let fontData = { user: app.info.user_fonts || [], system: [] };
  const fileInput = h("input", { type: "file", accept: ".ttf,.otf,.woff,.woff2", style: { display: "none" } });
  fileInput.addEventListener("change", async () => {
    const f = fileInput.files[0];
    fileInput.value = "";
    if (!f) return;
    if (f.size > 40 * 1024 * 1024) return toast("字体文件太大了（上限 40 MB）");
    try {
      const data = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1] || ""); r.onerror = rej; r.readAsDataURL(f); });
      const r = await api("font_import", { filename: f.name, data });
      fontData.user = app.info.user_fonts = r.user;
      toast(`已导入「${r.font.name}」，可以在上面的列表里选用`);
      renderFonts();
    } catch (e) { fail(e); }
  });
  const fontSelect = (key) => {
    const opt = (value, text) => h("option", { value, text, selected: (s[key] || "") === value ? true : null });
    const sel = h("select", { class: "select", "aria-label": key },
      opt("", "跟随配色（默认）"),
      h("optgroup", { label: "内置" }, opt("builtin:serif", "衬线 · 思源宋体"), opt("builtin:sans", "无衬线 · Inter / 系统黑体")),
      fontData.user.length ? h("optgroup", { label: "导入的字体" }, fontData.user.map((f) => opt("user:" + f.id, f.name))) : null,
      fontData.system.length ? h("optgroup", { label: "系统字体" }, fontData.system.map((n) => opt("system:" + n, n))) : null);
    sel.addEventListener("change", async () => { await set({ [key]: sel.value }); renderFonts(); });
    return sel;
  };
  function renderFonts() {
    const fam = (key, slot) => family(s[key], fontData.user, slot) || (slot === "title" ? "var(--serif)" : "var(--sans)");
    fill(fontsBox,
      row("标题和单词", "首页大标题、复习时的单词、各页标题。", fontSelect("font_title")),
      row("正文", "释义、例句、按钮和说明文字。", fontSelect("font_body")),
      row("导入字体", "支持 .ttf  .otf  .woff  .woff2。导入的字体会出现在上面两个列表里，文件存在数据文件夹的 fonts 里。" +
        (app.info.desktop ? "" : "（在浏览器里打开时看不到系统字体，可以导入字体文件。）"), act("导入字体文件…", () => fileInput.click())),
      fontData.user.length ? h("div", { class: "font-list" }, fontData.user.map((f) => h("div", { class: "font-item" },
        h("span", { class: "fname", style: { "font-family": `"ShiciUser-${f.id}", var(--sans)` }, text: f.name }),
        h("span", { class: "fmeta", text: `${f.format.toUpperCase()} · ${(f.size / 1048576).toFixed(1)} MB` }),
        h("button", { class: "link", text: "删除", onclick: async () => {
          if (!(await ask(`删除字体「${f.name}」？`, "正在使用它的地方会换回默认字体。", { ok: "删除", danger: true }))) return;
          try {
            const r = await api("font_delete", { id: f.id });
            fontData.user = app.info.user_fonts = r.user;
            Object.assign(s, r.settings); applySettings(r.settings); renderFonts(); toast("已删除");
          } catch (e) { fail(e); }
        } })))) : null,
      h("div", { class: "font-preview" },
        h("span", { class: "label", text: "PREVIEW · 预览" }),
        h("p", { class: "fp-title", style: { "font-family": fam("font_title", "title") }, text: "小梦的词书 serendipity 勉強" }),
        h("p", { class: "fp-body", style: { "font-family": fam("font_body", "body") }, text: "n. 意外发现珍奇事物的本领 · It was pure serendipity that we met. · 毎日日本語を勉強しています。" })),
      fileInput);
  }
  renderFonts();
  api("fonts").then((d) => { fontData = d; app.info.user_fonts = d.user; renderFonts(); }).catch(() => {});

  root.append(h("div", { class: "page-pad scroll", style: { height: "100%" } }, h("div", { class: "settings" },
    h("div", { class: "page-head" }, h("div", { class: "rise" }, h("span", { class: "label", html: "<b>04</b> / SETTINGS<span class=\"sep\">·</span>设置" }), h("h2", { class: "h2", text: "按自己的节奏来" }))),
    group(1, "STUDY · 学习",
      row("每天新词", "每天最多学多少个没见过的词。新词越多，之后每天要复习的也越多。", slider("new_per_day", 0, 100, 5, (v) => `${Math.round(v)} 个`)),
      row("每天复习上限", "到期的词太多时，每天最多复习这么多，剩下的顺延。", slider("review_per_day", 50, 1000, 50, (v) => `${Math.round(v)} 个`)),
      row("期望保持率", "复习时希望还记得的概率。调高记得更牢，但复习更频繁；一般 85%~92% 比较省力。", slider("retention", 70, 97, 1, (v) => `${Math.round(v * 100)}%`, 100)),
      row("新词顺序", "自己添加和导入的词总是排在词书前面。", seg("order", [["freq", "常用词优先"], ["random", "随机"], ["alpha", "字母顺序"]])),
      row("一天从几点开始", "熬夜到凌晨时，这个时间之前都算作前一天。", slider("day_start", 0, 8, 1, (v) => `${Math.round(v)}:00`))),
    group(2, "VOICE · 发音",
      row("自动朗读", "单词出现时自动读一遍。关掉后，显示答案时才读。", flag("autoplay", "自动朗读")),
      row("发音来源", "内置语音：程序自带的合成语音，词书里的英语和日语单词都有，不用联网，也不用给系统装语音包。在线真人：有道词典的发音，听过一次就存在本机。系统语音：Windows 自带的朗读，需要装了对应语言的语音。选中的来源没有某个词时，会自动换下一种。",
        seg("voice", [["builtin", "内置语音"], ["online", "在线真人"], ["system", "系统语音"]])),
      row("联网补充", "内置语音包里没有的词（比如自己加的生词）联网取一次发音并存下来，之后离线也能读。", flag("online_fallback", "联网补充")),
      row("在线发音口音", null, seg("accent", [["us", "美音"], ["uk", "英音"]])),
      row("试听", null, [act("英语 · vocabulary", () => speak("vocabulary", "en")), act("日语 · 勉強", () => speak("勉強", "ja"))])),
    group(2.5, "DICTIONARY · 词典",
      row("英语单词的释义", "英中：中文释义（ECDICT 英汉词典）。日英：日语释义（EJDict 英和辞典），例句也优先显示日语译文。没有日语释义的词仍显示中文。",
        seg("gloss_en", [["zh", "英中"], ["ja", "日英"]])),
      row("日语单词的释义", "中日：中文释义（主要来自维基词典，少数是程序自动匹配的，会标出来）。英日：英文释义（JMdict），例句显示英文译文。",
        seg("gloss_ja", [["zh", "中日"], ["en", "英日"]])),
      row("词根记忆", "英语单词显示词根拆分和同根词，比如 transport = trans-（穿过）+ port（运送）。只收词源对得上的拆法，大约三成考试词汇有。在复习时的释义下面和词库的单词详情里显示。",
        flag("show_roots", "词根记忆")),
      row("近义词、反义词", "英语单词显示常用的近义词和反义词（来自维基词典和 WordNet），显示位置同上。", flag("show_related", "近义词、反义词")),
      row("专业领域释义", "显示「[计] 专有权」「[医] …」这类计算机、医学、经济等专业用法。默认不显示。", flag("show_domain", "专业领域释义"))),
    group(3, "LOOK · 外观",
      row("暗色模式", "也可以随时点右上角的月亮 / 太阳图标切换。", toggle(isDark, (v) => set({ theme: v ? "dark" : "light" }, true), "暗色模式")),
      row("跟随系统明暗", "打开后，系统切到深色时自动变暗。", toggle(() => s.theme === "auto", (v) => set({ theme: v ? "auto" : (isDark() ? "dark" : "light") }, true), "跟随系统明暗")),
      row("主题", "简约白是柔和的白底、圆角卡片和无衬线字体；朱橙是纸白配朱红线条和斜切色块。两种都可以配暗色模式。", seg("palette", [["vermilion", "朱橙"], ["silver", "简约白"]])),
      row("动画", "觉得动画多或者电脑比较慢，可以减弱。", seg("motion", [["full", "完整"], ["reduced", "减弱"]])),
      row("显示例句", "复习时在右侧显示例句。", flag("show_examples", "显示例句")),
      ...(app.info.can_restart && app.info.platform === "win32" ? [
        row("画面渲染方式",
          "自动：N 卡、A 卡用 OpenGL，其他显卡用 D3D11。如果偶尔整个窗口空白闪一下（开着 Wallpaper Engine 这类动态壁纸时更容易出现），可以手动换另一种试试。改完要重启，重启后会让你确认画面是否正常，不确认 15 秒后自动换回；万一打不开，下次启动也会自动换回。",
          seg("render", [["auto", "自动"], ["d3d11", "D3D11"], ["opengl", "OpenGL"]], askRestart)),
        row("渲染显卡",
          "双显卡电脑上用哪张显卡画界面：高性能是独立显卡，省电是核显。和 Windows「设置 → 显示 → 图形」里给程序选显卡是同一个设置，选回「自动」会恢复原样。只有一张显卡的电脑选哪个都一样。台式机的显示器一般插在独显上，选「省电」可能打不开，程序会自动换回。改完要重启。",
          seg("gpu", [["auto", "自动"], ["high", "高性能"], ["low", "省电"]], askRestart)),
        row("当前使用", null, gpuName)] : []),
      ),
    group(3.5, "FONT · 字体", fontsBox),
    group(4, "SOUND · 音效",
      row("按键音效", "显示答案、评分、点按钮时给一点声音反馈。", toggle(() => s.sfx, async (v) => { await set({ sfx: v }, true); if (v) sfx.play("good", { force: true }); }, "按键音效")),
      sfxRows),
    group(5, "DATA · 数据",
      row("进度文件", "把学习进度存成一个文件（.xmdb）。换设备时把文件拷过去（U 盘、网盘、聊天软件都行），在新设备上导入就能接着背。两边都有进度时会合并，不会丢。",
        [act("导出进度文件", () => exportFile()), act("导入…", () => importProgress())]),
      row("进度密钥", "不方便传文件时，也可以把进度变成一串文字复制过去（学得越多越长）。", act("生成密钥", () => exportKey())),
      row("数据位置", null, h("span", { class: "path", text: app.info.data_dir || "" })),
      row("打开数据文件夹", "学习记录都在这个文件夹的 user.db 里，复制它也是完整备份。", act("打开文件夹", async () => {
        try { const r = await api("open_data_dir"); if (!r.opened) { await copyText(r.path); toast("路径已复制：" + r.path, 5000); } } catch (e) { fail(e); } })),
      row("备份", "在数据文件夹的 backups 里存一份当前的学习记录。", act("立即备份", async () => { try { toast("已备份到 " + (await api("backup")).path, 5000); } catch (e) { fail(e); } })),
      row("导出", "把词库和学习进度导出成 CSV 表格（Excel 可以直接打开）。", act("导出 CSV", async () => { try { toast("已导出到 " + (await api("export")).path, 5000); } catch (e) { fail(e); } })),
      row("清空学习记录", "词库保留，所有学习进度归零。清空前会自动备份一次。", act("清空…", async () => {
        if (!(await ask("清空全部学习记录？", "所有单词都会回到“未学”，统计也会清零。清空前会自动备份，可以从备份文件恢复。", { ok: "清空", danger: true }))) return;
        try { const r = await api("reset_progress", { confirm: "RESET" }); refreshNav(); toast("已清空。备份在 " + r.path, 6000); } catch (e) { fail(e); } }, "danger"))),
    group(5.5, "UPDATE · 更新",
      row("自动检查更新", "每次打开程序时联网看一下 GitHub 上有没有新版本。只读取版本号，不上传任何数据。", flag("update_check", "自动检查更新")),
      row("检查更新", `当前版本 v${app.info.version || ""}。也可以去 GitHub 或百度网盘直接下载最新版。`, act("立即检查", () => checkUpdate(true)))),
    group(6, "ABOUT · 关于",
      h("div", { class: "about-logo", role: "img", "aria-label": "L.Dream" }),
      h("div", { class: "about-links" },
        h("button", { class: "btn ghost sm", onclick: () => openLink(app.info.links.github) }, "GitHub 项目主页"),
        h("button", { class: "btn ghost sm", onclick: () => openLink(app.info.links.bilibili) }, "B 站 · 千醉_LDream"),
        h("button", { class: "btn ghost sm", onclick: () => openNetdisk() }, `百度网盘（提取码 ${app.info.links?.netdisk_code || "2922"}）`)),
      h("div", { class: "credits", style: { "padding-top": "6px" }, html:
        `<b>${app.info.app || "小梦的词书"}</b> v${app.info.version || ""} · MIT 许可证开源<br>` +
        "记忆算法：<b>FSRS</b>（open-spaced-repetition/py-fsrs，MIT）<br>" +
        "英语词典：<b>ECDICT</b>（MIT）　例句：<b>Tatoeba</b>（CC BY 2.0 FR）、<b>WordNet 3.0</b>（Princeton University）<br>" +
        "日语词表：<b>JLPT 词表</b>（Jonathan Waller, tanos.co.uk，CC BY）　日语释义：<b>JMdict</b>（EDRDG，CC BY-SA 4.0）、<b>维基词典</b>（CC BY-SA 4.0）<br>" +
        "英日释义：<b>EJDict-hand</b>（公有领域）　部分例句译文为机器翻译：<b>opus-mt-en-zh</b>（Helsinki-NLP，CC BY 4.0）<br>" +
        "内置语音：英语 <b>Piper · LJ Speech</b>（公有领域数据集）　日语 <b>Open JTalk · HTS voice “Mei”</b>（名古屋工业大学，CC BY 3.0）<br>" +
        "字体：Noto Serif SC / Noto Serif JP、Inter、JetBrains Mono（SIL OFL 1.1）" })))));

  const onOutside = () => { Object.assign(s, app.settings); syncs.forEach((fn) => fn()); };
  document.addEventListener("shici-settings", onOutside);
  return () => document.removeEventListener("shici-settings", onOutside);
}

// 复制到剪贴板：桌面版交给后台（最可靠），否则用浏览器接口
async function copyText(text, fallbackEl) {
  try { if ((await api("clipboard_copy", { text })).copied) return true; } catch { /* 往下试 */ }
  try { await navigator.clipboard.writeText(text); return true; } catch { /* 往下试 */ }
  if (fallbackEl) { fallbackEl.focus(); fallbackEl.select(); try { return document.execCommand("copy"); } catch { return false; } }
  return false;
}

async function exportKey() {
  let r;
  try { r = await api("progress_export"); } catch (e) { return fail(e); }
  const box = h("textarea", { class: "keybox scroll", readonly: true, spellcheck: "false", "aria-label": "进度密钥" });
  box.value = r.key;
  const fact = (k, v) => h("div", {}, h("span", { class: "label", text: k }), h("span", { class: "num", text: v }));
  openLayer("modal", (close) => [
    h("div", { class: "modal-head" }, h("div", {}, h("span", { class: "label", text: "PROGRESS KEY · 进度密钥" }), h("h3", { class: "h2", style: { "margin-top": "10px" }, text: "带着进度走" })),
      h("button", { class: "icon-btn", "aria-label": "关闭", html: icons.close, onclick: close })),
    h("div", { class: "modal-body" },
      h("div", { class: "keyfacts" }, fact("学过的词", r.words.toLocaleString("en-US")), fact("复习记录", r.logs.toLocaleString("en-US") + " 条"), fact("密钥长度", r.chars.toLocaleString("en-US") + " 字符")),
      box,
      h("p", { class: "note", html: "把整串密钥复制到新设备，在「设置 → 进度文件 → 导入… → 改用进度密钥」里粘贴。<br>密钥太长不好复制的话，用「导出进度文件」更方便。密钥里就是进度本身（学过的词、记忆状态、复习记录、自己加的词和助记），不经过任何服务器，所以学得越多，密钥越长。它不是密码：谁拿到这串文字都能导入这份进度，别贴到公开的地方。" })),
    h("div", { class: "modal-foot" }, h("button", { class: "btn ghost sm", onclick: close }, "关闭"),
      h("button", { class: "btn sm", autofocus: true, onclick: async () => toast((await copyText(r.key, box)) ? "密钥已复制，可以去新设备粘贴了" : "没能自动复制，请在框里全选后按 Ctrl+C", 4200) }, "复制密钥")),
  ], { width: "640px" });
}

// 导出进度文件：生成后交给浏览器下载。桌面版会弹出“另存为”窗口（见 desktop.py），浏览器里就是普通下载。
async function exportFile() {
  let r;
  try { r = await api("progress_export", { as_file: true }); } catch (e) { return fail(e); }
  const bytes = Uint8Array.from(atob(r.data), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
  const a = h("a", { href: url, download: r.filename, style: { display: "none" } });
  document.body.append(a);
  a.click();
  setTimeout(() => { a.remove(); URL.revokeObjectURL(url); }, 60000);
  const size = r.bytes < 1048576 ? Math.max(1, Math.round(r.bytes / 1024)) + " KB" : (r.bytes / 1048576).toFixed(1) + " MB";
  toast(app.info.desktop ? `进度文件已生成（${r.words} 个词，${size}），选一个地方保存就行` : `进度文件已下载：${r.filename}（${size}）`, 5000);
}

// 导入进度：默认选文件（也可以把文件拖进来），也能切换成粘贴密钥
function importProgress(mode = "file") {
  const box = h("textarea", { class: "keybox scroll", placeholder: "在这里粘贴进度密钥（以 XMCS1. 开头，Ctrl+V）", spellcheck: "false", "aria-label": "粘贴进度密钥" });
  const picker = h("input", { type: "file", accept: ".xmdb,.txt", style: { display: "none" } });
  const drop = h("div", { class: "drop", tabindex: 0, onclick: () => picker.click(), onkeydown: (e) => e.key === "Enter" && picker.click() },
    h("span", { html: icons.upload }), h("b", { text: "点击选择进度文件，或把文件拖到这里" }), h("span", { class: "small mute", text: "小梦的词书-进度-….xmdb" }));
  let payload = null;  // {file} 或 {key}
  const readFile = async (f) => {
    if (!f) return;
    if (f.size > 60 * 1024 * 1024) return toast("文件太大了，不像是进度文件");
    const data = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1] || ""); r.onerror = rej; r.readAsDataURL(f); });
    payload = { file: data };
    fill(drop, h("span", { html: icons.upload }), h("b", { text: f.name }), h("span", { class: "small mute", text: "正在识别…" }));
    inspect();
  };
  picker.addEventListener("change", () => { readFile(picker.files[0]); picker.value = ""; });
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); readFile(e.dataTransfer.files[0]); });
  const input = h("div", {});
  const info = h("div", {}), foot = h("div", { class: "modal-foot" });
  const day = (ts) => { const d = new Date(ts * 1000); return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const fact = (k, v) => h("div", {}, h("span", { class: "label", text: k }), h("span", { class: "num", text: v }));
  let layer;
  const switchLink = () => h("button", { class: "link grow", onclick: () => { mode = mode === "file" ? "key" : "file"; start(); } },
    mode === "file" ? "没有文件？改用进度密钥" : "改用进度文件");
  const start = () => {
    payload = null;
    fill(input, mode === "file" ? [drop, picker] : box);
    fill(drop, h("span", { html: icons.upload }), h("b", { text: "点击选择进度文件，或把文件拖到这里" }), h("span", { class: "small mute", text: "小梦的词书-进度-….xmdb" }));
    fill(info);
    fill(foot, switchLink(), mode === "key" ? h("button", { class: "btn sm", onclick: () => { payload = { key: box.value }; inspect(); } }, "识别密钥") : null);
    if (mode === "key") setTimeout(() => box.focus(), 50);
  };
  async function inspect() {
    if (mode === "key" && !box.value.trim()) return box.focus();
    let r;
    try { r = await api("progress_inspect", payload); } catch (e) { if (mode === "file") start(); return fail(e); }
    if (mode === "file") drop.lastChild.textContent = "识别成功";
    fill(info,
      h("div", { class: "keyfacts", style: { "margin-top": "18px" } }, fact("学过的词", r.words.toLocaleString("en-US")), fact("复习记录", r.logs.toLocaleString("en-US") + " 条"), fact("生成时间", day(r.exported_at))),
      h("p", { class: "note", text: (r.books.length ? `计划里的词书：${r.books.join("、")}。` : "") +
        (r.local_words ? `这台设备上已经学过 ${r.local_words} 个词：导入后两边会合并，每个词以最近复习过的那一边为准，复习记录取并集，不会丢。` : "这台设备上还没有学习记录，导入后就和原来的设备一样了。") + "导入前会自动备份一次。" }));
    fill(foot, h("button", { class: "link grow", onclick: start }, mode === "file" ? "换一个文件" : "换一串密钥"),
      h("button", { class: "btn sm", onclick: async (e) => {
        e.target.disabled = true;
        try {
          const res = await api("progress_import", payload);
          applySettings((await api("bootstrap")).settings);
          refreshNav();
          toast(`已继承进度：更新 ${res.updated} 个词，新增 ${res.logs_added} 条复习记录` + (res.kept ? `，${res.kept} 个词保留了本机更新的进度` : ""), 6000);
          layer.close();
          document.dispatchEvent(new CustomEvent("shici-settings"));
        } catch (err) { fail(err); e.target.disabled = false; }
      } }, "继承进度"));
  }
  box.addEventListener("input", () => {  // 改了密钥就要重新识别
    fill(info);
    fill(foot, switchLink(), h("button", { class: "btn sm", onclick: () => { payload = { key: box.value }; inspect(); } }, "识别密钥"));
  });
  layer = openLayer("modal", (close) => [
    h("div", { class: "modal-head" }, h("div", {}, h("span", { class: "label", text: "PROGRESS · 导入进度" }), h("h3", { class: "h2", style: { "margin-top": "10px" }, text: "接着上次背" })),
      h("button", { class: "icon-btn", "aria-label": "关闭", html: icons.close, onclick: close })),
    h("div", { class: "modal-body" }, input, info), foot,
  ], { width: "640px" });
  start();
}
