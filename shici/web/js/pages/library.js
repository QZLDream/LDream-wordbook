// 词库：词书、我的词表、单词列表、单词详情、添加单词、导入词表。
import { api, speak } from "../api.js";
import { h, $, fill, icons, defBlock, exampleEl, toast, fail, openLayer, ask, fmtDue, pct, STATUS, debounce, bindTips, wordExtras } from "../ui.js";
import { app, refreshNav } from "../app.js";
import { curveChart } from "../charts.js";

const FILTERS = [["all", "全部"], ["new", "未学"], ["learning", "学习中"], ["young", "复习中"], ["mature", "已掌握"], ["suspended", "已搁置"]];
const PAGE = 60;

export async function mount(root) {
  const S = { q: "", filters: new Set(), source: null, sort: "due", offset: 0, total: 0, now: Date.now() / 1000,
              selecting: false, sel: new Set(), last: -1 };
  const filterParam = () => (S.filters.size ? [...S.filters] : "all");
  const booksEl = h("div", { class: "books scroll" });
  let booksShown = false;
  const wordsEl = h("div", { class: "words scroll" });
  const headEl = h("div", { class: "words-head rise", style: { "--i": 3 } }, ["单词", "读音", "释义", "状态", "下次复习"].map((t) => h("span", { class: "label", text: t })));
  // 列表右边有滚动条，会比表头窄一截；量出滚动条宽度补到表头和排序按钮上，
  // 让表头的线、每一行（包括悬停高亮）和排序按钮右端对齐
  const alignHead = () => { headEl.style.marginRight = sortSeg.style.marginRight = Math.max(0, wordsEl.offsetWidth - wordsEl.clientWidth) + "px"; };
  const ro = new ResizeObserver(alignHead);
  ro.observe(wordsEl);
  const titleEl = h("h2", { class: "h2", text: "全部单词" });
  const countEl = h("span", { class: "label" });
  // 筛选标签可以同时选几个（比如“未学 + 学习中”）；点“全部”清空
  const chips = h("div", { class: "chips" }, FILTERS.map(([k, t]) => h("button", { class: "chip" + (k === "all" ? " on" : ""), "data-f": k, text: t,
    onclick: () => {
      if (k === "all") S.filters.clear(); else if (S.filters.has(k)) S.filters.delete(k); else S.filters.add(k);
      [...chips.children].forEach((c) => c.classList.toggle("on", c.dataset.f === "all" ? !S.filters.size : S.filters.has(c.dataset.f)));
      loadWords(true);
    } })));
  const search = h("input", { class: "field", type: "search", placeholder: "搜索单词", "aria-label": "搜索单词" });
  search.addEventListener("input", debounce(() => { S.q = search.value; loadWords(true); }));
  const sortSeg = h("div", { class: "seg" }, [["due", "到期"], ["term", "字母"], ["added", "最近添加"]].map(([k, t]) =>
    h("button", { class: k === "due" ? "on" : "", text: t, onclick: (e) => { S.sort = k; [...sortSeg.children].forEach((b) => b.classList.toggle("on", b === e.target)); loadWords(true); } })));

  // ---- 多选：勾选一批词，一起优先学 / 搁置 / 恢复 / 重新学 / 删除 ----
  const multiBtn = h("button", { class: "chip multi", title: "勾选多个词一起操作（按住 Shift 点击可以连选）", onclick: () => setSelecting(!S.selecting) }, h("i"), h("span", { text: "多选" }));
  const cntEl = h("b", { text: "0" });
  const bulkBtns = {};
  const bulkBtn = (key, text, cls) => (bulkBtns[key] = h("button", { class: cls || "", text, onclick: () => bulk(key) }));
  const allBtn = h("button", { text: "全选", onclick: () => selectAll() });
  const bulkbar = h("div", { class: "bulkbar", "data-sfx": "bar" },
    h("span", { class: "cnt" }, "已选", cntEl, "个"), allBtn, h("span", { class: "sepv" }),
    bulkBtn("prioritize", "优先学"), bulkBtn("suspend", "搁置"), bulkBtn("resume", "恢复"), bulkBtn("reset", "重新学"), bulkBtn("delete", "删除", "warn"),
    h("span", { class: "sepv" }), h("button", { text: "完成", onclick: () => setSelecting(false) }));
  let mainEl;
  function setSelecting(on) {
    S.selecting = on; S.last = -1;
    if (!on) S.sel.clear();
    mainEl.classList.toggle("selecting", on);
    multiBtn.classList.toggle("on", on);
    multiBtn.lastChild.textContent = on ? "退出多选" : "多选";
    paintSel();
  }
  function paintSel() {
    cntEl.textContent = S.sel.size.toLocaleString("en-US");
    for (const b of Object.values(bulkBtns)) b.disabled = !S.sel.size;
    allBtn.textContent = S.total && S.sel.size >= S.total ? "全不选" : `全选 ${S.total.toLocaleString("en-US")} 个`;
    for (const r of wordsEl.querySelectorAll(".word-row")) r.classList.toggle("picked", S.sel.has(+r.dataset.id));
  }
  function pick(row, e) {
    const rows = [...wordsEl.querySelectorAll(".word-row")], i = rows.indexOf(row), id = +row.dataset.id;
    if (e.shiftKey && S.last >= 0 && S.last < rows.length) {      // Shift 连选：从上次点的那一行到这一行
      const on = !S.sel.has(id), [a, b] = [Math.min(S.last, i), Math.max(S.last, i)];
      for (let k = a; k <= b; k++) on ? S.sel.add(+rows[k].dataset.id) : S.sel.delete(+rows[k].dataset.id);
    } else if (S.sel.has(id)) S.sel.delete(id); else S.sel.add(id);
    S.last = i;
    paintSel();
  }
  async function selectAll() {
    try {
      if (S.total && S.sel.size >= S.total) S.sel.clear();
      else S.sel = new Set((await api("item_ids", { q: S.q, filter: filterParam(), source: S.source })).ids);   // 包括还没滚动加载出来的
      paintSel();
    } catch (e) { fail(e); }
  }
  async function bulk(action) {
    const n = S.sel.size, ids = [...S.sel];
    if (!n) return;
    const sure = { reset: ["重新学这 " + n + " 个词？", "它们的学习记录会清零，当作新词重新出现。", { ok: "重新学" }],
                   delete: ["删除这 " + n + " 个词？", "这些词和它们的学习记录会从词库里删掉，不能恢复。", { ok: "删除", danger: true }] }[action];
    if (sure && !(await ask(...sure))) return;
    try {
      await api("items_bulk", { ids, action });
      toast({ prioritize: `${n} 个词已排到新词最前面`, suspend: `已搁置 ${n} 个词，不会再出现在复习里`, resume: `已恢复 ${n} 个词`,
              reset: `${n} 个词已重置为新词`, delete: `已删除 ${n} 个词` }[action]);
      S.sel.clear(); S.last = -1;
      await reload();
    } catch (e) { fail(e); }
  }

  root.append(h("div", { class: "library" },
    h("aside", { class: "lib-side" },
      h("div", { class: "rise" }, h("span", { class: "label", html: "<b>02</b> / LIBRARY<span class=\"sep\">·</span>词库" })),
      h("div", { class: "acts rise", style: { "--i": 1 } },
        h("button", { class: "btn sm", onclick: () => addWordModal(reload) }, "＋ 添加单词"),
        h("button", { class: "btn ghost sm", onclick: () => importModal(reload) }, "导入词表")),
      booksEl),
    h("div", { class: "lib-main" },
      h("div", { class: "lib-head rise", style: { "--i": 1 } }, h("div", {}, countEl, titleEl), multiBtn),
      h("div", { class: "lib-tools rise", style: { "--i": 2 } }, h("div", { class: "search" }, h("span", { html: icons.search }), search), chips, sortSeg),
      headEl,
      wordsEl, bulkbar)));
  mainEl = root.querySelector(".lib-main");
  app.keyHandler = (e, typing) => {
    if (!S.selecting) return false;
    if (e.key === "Escape") { setSelecting(false); return true; }
    if (!typing && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") { selectAll(); return true; }
    return false;
  };

  async function loadBooks() {
    const d = await api("books");
    const row = (b, src, isBook) => {
      const p = b.in_plan ? b.learned / b.in_plan : 0;
      const el = h("div", { class: "book" + (S.source === src ? " sel" : ""), onclick: () => select(src, b.title) },
        h("div", { class: "t" }, h("span", { text: b.title, title: b.title }), isBook && b.subtitle !== b.title ? h("small", { text: b.subtitle }) : null),
        h("div", { class: "m", text: b.enabled === false ? `${b.count.toLocaleString("en-US")} 词` : `已学 ${b.learned} / ${b.in_plan.toLocaleString("en-US")}` }),
        h("button", { class: "plan" + (b.enabled !== false && isBook ? " on" : ""), text: b.enabled !== false ? (isBook ? "计划中" : "移出") : "加入计划",
          title: b.enabled !== false ? "点击移出学习计划（学过的词会保留）" : "加入学习计划",
          onclick: (e) => { e.stopPropagation(); toggle(b, src, isBook, e.target); } }),
        h("div", { class: "bar" }, h("i")));
      requestAnimationFrame(() => el.style.setProperty("--p", p));
      return el;
    };
    const en = d.books.filter((b) => b.lang === "en"), ja = d.books.filter((b) => b.lang === "ja");
    fill(booksEl, 
      h("div", { class: "book" + (S.source === null ? " sel" : ""), onclick: () => select(null, "全部单词") }, h("div", { class: "t", text: "全部单词" }), h("div", { class: "m", text: "词库里的所有词" })),
      d.lists.length ? [h("h4", { class: "label", text: "我的词表" }), d.lists.map((b) => row(b, b.id, false))] : null,
      h("h4", { class: "label", text: "英语词书" }), en.map((b) => row(b, "book:" + b.id, true)),
      h("h4", { class: "label", text: "日语词书 · JLPT" }), ja.map((b) => row(b, "book:" + b.id, true)));
    // 第一次进入词库时，侧栏的词书和右边的单词行一样依次浮现；之后刷新（加入/移出计划）不再重播
    if (!booksShown) {
      booksShown = true;
      [...booksEl.children].forEach((el, i) => {
        el.classList.add("rise");
        el.style.setProperty("--i", Math.min(i + 2, 14));
        el.style.animationDuration = ".6s";
        const done = (e) => {
          if (e.target !== el) return;
          el.removeEventListener("animationend", done);
          el.classList.remove("rise"); el.style.removeProperty("--i"); el.style.animationDuration = "";
        };
        el.addEventListener("animationend", done);
      });
    }
  }

  async function toggle(b, src, isBook, btn) {
    btn.disabled = true;
    try {
      if (b.enabled === false) {
        const r = await api("book_enable", { id: b.id });
        toast(`《${b.title}》已加入计划，新增 ${r.added} 词`);
      } else {
        const r = await api("source_remove", { id: src });
        toast(`已移出《${b.title}》：删除 ${r.removed} 个没学过的词${r.kept ? `，保留 ${r.kept} 个学过的` : ""}`);
        if (S.source === src) { S.source = null; titleEl.textContent = "全部单词"; }
      }
      await reload();
    } catch (e) { fail(e); btn.disabled = false; }
  }

  function select(src, title) {
    S.source = src;
    titleEl.textContent = title;
    [...booksEl.querySelectorAll(".book")].forEach((el) => el.classList.remove("sel"));
    loadBooks();
    loadWords(true);
  }

  async function loadWords(reset) {
    if (reset) { S.offset = 0; wordsEl.scrollTop = 0; }
    const d = await api("items", { q: S.q, filter: filterParam(), source: S.source, sort: S.sort, offset: S.offset, limit: PAGE });
    S.total = d.total; S.now = Date.now() / 1000;
    countEl.textContent = `${d.total.toLocaleString("en-US")} WORDS`;
    const rows = d.items.map((it, i) => h("button", { class: "word-row rise" + (S.sel.has(it.id) ? " picked" : ""), "data-id": it.id,
      style: { "--i": Math.min(i, 14), "--d": "0ms", "animation-duration": ".5s" }, onclick: (e) => (S.selecting ? pick(e.currentTarget, e) : detail(it.id)) },
      h("i", { class: "ck" }), h("span", { class: "w", lang: it.lang, text: it.term }), h("span", { class: "r", text: it.reading }), h("span", { class: "d", text: it.definition }),
      h("span", { class: "s" }, h("i", { class: "dot " + it.status }), STATUS[it.status]),
      h("span", { class: "due", text: it.status === "new" || it.status === "suspended" ? "—" : fmtDue(it.due, S.now) })));
    if (reset) fill(wordsEl, rows); else { $(".more", wordsEl)?.remove(); wordsEl.append(...rows); }
    S.offset += d.items.length;
    if (S.selecting) paintSel();
    if (!d.total) {
      fill(wordsEl, h("div", { class: "empty" }, h("p", { class: "h3", text: S.q || S.filters.size ? "没有符合条件的词" : "这里还没有词" }),
        h("p", { text: S.q || S.filters.size ? "换个搜索词或筛选条件试试。" : "在左边把一本词书加入计划，或者添加、导入自己的词。" })));
    } else if (S.offset < d.total) {
      wordsEl.append(h("button", { class: "btn ghost sm more", onclick: () => loadWords(false) }, `再显示 ${Math.min(PAGE, d.total - S.offset)} 个`));
    }
  }

  async function reload() { await Promise.all([loadBooks(), loadWords(true)]); refreshNav(); }
  const detail = (id) => itemDrawer(id, () => { loadBooks(); loadWords(true); refreshNav(); });
  await reload();
  alignHead();
  return () => ro.disconnect();
}

// ------------------------------------------------------------------ 单词详情
export async function itemDrawer(id, onChange) {
  let it;
  try { it = await api("item", { id }); } catch (e) { return fail(e); }
  let dirty = false;
  const save = async (patch, msg) => { try { it = await api("item_update", { id, ...patch }); dirty = true; if (msg) toast(msg); render(); } catch (e) { fail(e); } };
  const body = h("div", { class: "drawer-body scroll" });
  const foot = h("div", { class: "drawer-foot" });
  const layer = openLayer("drawer", (close) => [
    h("div", { class: "drawer-head" }, h("span", { class: "label", text: "WORD · 单词详情" }), h("button", { class: "icon-btn", "aria-label": "关闭", html: icons.close, onclick: close })),
    body, foot], { onClose: () => dirty && onChange?.() });
  bindTips(layer.box);

  function render() {
    const c = it.card, now = Date.now() / 1000;
    const def = h("textarea", { class: "field", rows: 3, placeholder: "留空则使用内置词典的释义" });
    def.value = it.custom_definition ? it.definition : "";
    const note = h("textarea", { class: "field", rows: 2, placeholder: "写一句帮自己记住它的话…" });
    note.value = it.note;
    const exEn = h("input", { class: "field", placeholder: "例句（原文）" }), exZh = h("input", { class: "field", placeholder: "译文（可不填）", style: { "margin-top": "8px" } });
    const kv = (k, v) => h("div", {}, h("span", { class: "label", text: k }), h("span", { class: "num", text: v }));
    fill(body, 
      h("span", { class: "label", style: { display: "flex", gap: "8px", "align-items": "center", "margin-top": "14px" } }, h("i", { class: "dot " + it.status }), STATUS[it.status], it.sources.length ? " · " + it.sources.join(" / ") : ""),
      h("h2", { class: "term", lang: it.lang, text: it.term }),
      h("div", { class: "reading" }, it.reading ? (it.lang === "ja" ? it.reading : `/${it.reading}/`) : "",
        h("button", { class: "icon-btn", "aria-label": "朗读", html: icons.speaker, onclick: () => speak(it.term, it.lang) })),
      h("section", {}, h("span", { class: "label", text: "DEFINITION · 释义" }), defBlock(it.definition, 12, { style: { "max-height": "none" } }),
        it.auto_def ? h("p", { class: "auto-def", text: "这条中文释义是程序自动匹配的，仅供参考。" }) : null),
      wordExtras(it) ? h("section", {}, h("span", { class: "label", text: "WORD FAMILY · 词根与近反义" }), wordExtras(it)) : null,
      c ? h("section", {}, h("span", { class: "label", text: "MEMORY · 记忆状态" }),
        h("div", { class: "kv" }, kv("现在还记得", pct(c.recall)), kv("稳定度", c.stability < 10 ? c.stability.toFixed(1) + " 天" : Math.round(c.stability) + " 天"),
          kv("下次复习", fmtDue(c.due, now)), kv("复习 / 遗忘", `${c.reps} / ${c.lapses}`)),
        h("div", { class: "chart", style: { padding: "18px 0 0" } }, curveChart(c.curve, { retention: c.retention, height: 200, width: 490,
          marks: [{ t: c.elapsed_days, label: "现在", accent: true }, ...(c.due_days > c.elapsed_days + c.span * 0.06 ? [{ t: c.due_days, label: "下次复习" }] : [])] })),
        it.logs.length ? h("div", { style: { "margin-top": "14px" } }, h("span", { class: "label", style: { display: "block", "margin-bottom": "10px" }, text: "最近的评分（新 → 旧）" }),
          h("div", { class: "hist" }, it.logs.map((l) => h("i", { class: "r" + l.rating, "data-tip": `${new Date(l.ts * 1000).toLocaleDateString("zh-CN")}<br>${["", "忘记", "模糊", "认识", "太简单"][l.rating]}${l.mode === "spell" ? " · 拼写" : ""}` })))) : null) : null,
      h("section", {}, h("span", { class: "label", text: "EXAMPLES · 例句" }),
        it.examples.length ? it.examples.map((ex, i) => {
          const el = exampleEl(ex, it.term, it.lang);
          if (i < it.my_examples.length) el.append(h("button", { class: "link", style: { "margin-top": "4px" }, text: "删除这条", onclick: () => save({ examples: it.my_examples.filter((_, j) => j !== i) }, "例句已删除") }));
          return el;
        }) : h("p", { class: "mute small", text: "暂时没有例句。" }),
        h("div", { style: { "margin-top": "12px" } }, exEn, exZh,
          h("button", { class: "btn ghost sm", style: { "margin-top": "10px" }, onclick: () => exEn.value.trim() ? save({ examples: [...it.my_examples, { en: exEn.value, zh: exZh.value }] }, "例句已添加") : exEn.focus() }, "添加例句"))),
      h("section", {}, h("span", { class: "label", text: "MEMO · 助记" }), note),
      h("section", {}, h("span", { class: "label", text: "CUSTOM · 自定义释义" }), def,
        h("button", { class: "btn sm", style: { "margin-top": "12px" }, onclick: () => save({ note: note.value, definition: def.value }, "已保存") }, "保存助记和释义")));
    fill(foot, 
      h("button", { class: "btn ghost sm", onclick: () => save({ suspended: !it.suspended }, it.suspended ? "已恢复，会重新出现在复习里" : "已搁置，不会再出现在复习里") }, it.suspended ? "恢复学习" : "搁置（已经很熟）"),
      c ? h("button", { class: "btn ghost sm", onclick: async () => (await ask("重新学这个词？", "它的学习记录会清零，当作新词重新出现。", { ok: "重新学" })) && save({ reset: true }, "已重置为新词") }, "重新学") : null,
      h("button", { class: "btn danger sm", style: { "margin-left": "auto" }, onclick: async () => {
        if (!(await ask(`删除「${it.term}」？`, "这个词和它的学习记录会从词库里删掉，不能恢复。", { ok: "删除", danger: true }))) return;
        try { await api("item_delete", { ids: [id] }); dirty = true; toast("已删除"); layer.close(); } catch (e) { fail(e); } } }, "删除"));
  }
  render();
}

// ------------------------------------------------------------------ 添加单词
function addWordModal(onDone) {
  let lang = "auto", added = 0;
  const term = h("input", { class: "big-input", placeholder: "输入单词", autofocus: true, autocomplete: "off", spellcheck: "false" });
  const reading = h("input", { class: "field", placeholder: "音标或假名（可不填）" });
  const def = h("textarea", { class: "field", rows: 3, placeholder: "释义。词典里有的词会自动填上，可以改。" });
  const note = h("input", { class: "field", placeholder: "助记（可不填）" });
  const sugg = h("div", { class: "sugg" });
  const status = h("span", { class: "label grow" });
  let auto = { def: "", reading: "" };
  const lookup = debounce(async () => {
    const t = term.value.trim();
    if (!t) { fill(sugg, ); status.textContent = ""; return; }
    try {
      const r = await api("lookup", { term: t, lang });
      if (term.value.trim() !== t) return;
      const e = r.entry && r.entry.word.toLowerCase() === t.toLowerCase() ? r.entry : null;
      if (def.value === auto.def) { def.value = auto.def = e?.translation || ""; }
      if (reading.value === auto.reading) { reading.value = auto.reading = e?.phonetic || ""; }
      status.textContent = r.exists ? "已经在词库里了" : e ? "词典里有这个词" : (r.entry ? `词典里有它的原形 ${r.entry.word}` : "词典里没有，请自己填释义");
      fill(sugg, ...r.suggest.filter((s) => s.word.toLowerCase() !== t.toLowerCase()).map((s) => h("button", { class: "chip", text: s.word, onclick: () => { term.value = s.word; lookup(); term.focus(); } })));
    } catch (e) { fail(e); }
  }, 180);
  term.addEventListener("input", lookup);
  const submit = async () => {
    try {
      const r = await api("add_word", { term: term.value, lang, reading: reading.value, definition: def.value, note: note.value });
      toast(r.added ? `已添加「${r.term}」` : `「${r.term}」已在词库里，已提到前面优先学`);
      added++;
      term.value = def.value = reading.value = note.value = ""; auto = { def: "", reading: "" };
      fill(sugg, ); status.textContent = ""; term.focus();
    } catch (e) { fail(e); }
  };
  const seg = h("div", { class: "seg" }, [["auto", "自动"], ["en", "英语"], ["ja", "日语"]].map(([k, t]) =>
    h("button", { class: k === "auto" ? "on" : "", text: t, onclick: (e) => { lang = k; [...seg.children].forEach((b) => b.classList.toggle("on", b === e.target)); lookup(); } })));
  openLayer("modal", (close) => {
    const form = h("form", { onsubmit: (e) => { e.preventDefault(); submit(); } },
      h("div", { class: "modal-head" }, h("div", {}, h("span", { class: "label", text: "ADD · 添加单词" }), h("h3", { class: "h2", style: { "margin-top": "10px" }, text: "加一个生词" })),
        h("button", { class: "icon-btn", type: "button", "aria-label": "关闭", html: icons.close, onclick: close })),
      h("div", { class: "modal-body" },
        h("div", { class: "form-row" }, term, sugg),
        h("div", { class: "form-row" }, h("span", { class: "label", text: "语言" }), seg),
        h("div", { class: "form-row" }, h("span", { class: "label", text: "读音" }), reading),
        h("div", { class: "form-row" }, h("span", { class: "label", text: "释义" }), def),
        h("div", { class: "form-row" }, h("span", { class: "label", text: "助记" }), note)),
      h("div", { class: "modal-foot" }, status, h("button", { class: "btn ghost sm", type: "button", onclick: close }, "完成"), h("button", { class: "btn sm", type: "submit" }, "添加", h("kbd", { text: "ENTER" }))));
    def.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } });
    return form;
  }, { onClose: () => added && onDone() });
}

// ------------------------------------------------------------------ 导入词表
function importModal(onDone) {
  let imported = false, preview = null, withMissing = false;
  const body = h("div", { class: "modal-body" });
  const foot = h("div", { class: "modal-foot" });
  const file = h("input", { type: "file", accept: ".txt,.csv,.tsv,.xlsx", style: { display: "none" } });
  const name = h("input", { class: "field", placeholder: "给这个词表起个名字" });

  const read = (f) => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result.split(",")[1] || ""); r.onerror = rej; r.readAsDataURL(f); });
  async function take(f) {
    if (!f) return;
    if (f.size > 8e6) return toast("文件太大了（上限 8 MB）");
    try {
      preview = await api("import_preview", { filename: f.name, data: await read(f) });
      if (!preview.total) return toast("没有在文件里找到单词");
      name.value = f.name.replace(/\.[^.]+$/, "");
      step2();
    } catch (e) { fail(e); }
  }
  file.addEventListener("change", () => take(file.files[0]));

  function step1() {
    const drop = h("div", { class: "drop", tabindex: 0, onclick: () => file.click(), onkeydown: (e) => e.key === "Enter" && file.click() },
      h("span", { html: icons.upload }), h("b", { text: "点击选择文件，或把文件拖到这里" }), h("span", { class: "small mute", text: "支持 .txt  .csv  .tsv  .xlsx" }));
    drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("over"));
    drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); take(e.dataTransfer.files[0]); });
    fill(body, drop, file,
      h("p", { class: "small mute", style: { "margin-top": "16px" }, html: "每行一个单词就可以，释义会从内置词典自动补上。<br>也可以写成“单词 + 释义”两列（用制表符、逗号或两个以上空格隔开），带表头的表格会自动识别列。" }));
    fill(foot, );
  }

  function step2() {
    const usable = () => preview.rows.filter((r) => r.ok || withMissing);  // 已在词库的词也算：会归到这个词表并提前学
    const btn = h("button", { class: "btn sm" });
    const refresh = () => { const n = usable().length; btn.textContent = `导入 ${n} 个词`; btn.disabled = !n; };
    const sum = (n, t) => h("span", {}, h("b", { class: "num", text: n }), t);
    const chk = h("button", { class: "toggle", role: "switch", "aria-checked": "false", "aria-label": "也导入缺释义的词",
      onclick: () => { withMissing = !withMissing; chk.setAttribute("aria-checked", withMissing); refresh(); } });
    fill(body, 
      h("div", { class: "sumline small mute" }, sum(preview.total, "个词"), sum(preview.found, "个有释义"), sum(preview.missing, "个缺释义"), sum(preview.existing, "个已在词库")),
      h("div", { class: "pv scroll" }, preview.rows.slice(0, 300).map((r) => h("div", { class: "pv-row" },
        h("b", { lang: r.lang, text: r.term }), h("span", { text: r.definition || r.dict || "—" }),
        h("span", { class: "tag" + (r.exists ? " dup" : r.ok ? "" : " miss"), text: r.exists ? "已在词库" : r.ok ? (r.definition ? "自带释义" : "词典") : "缺释义" }))),
        preview.total > 300 ? h("div", { class: "pv-row" }, h("span", { class: "mute", text: `…还有 ${preview.total - 300} 个` })) : null),
      preview.missing ? h("div", { class: "set-row", style: { padding: "6px 0 14px", border: 0 } },
        h("div", { class: "txt" }, h("b", { text: "也导入缺释义的词" }), h("span", { text: "导入后可以在词库里给它们补上释义。" })), chk) : null,
      h("div", { class: "form-row" }, h("span", { class: "label", text: "词表名称" }), name));
    btn.onclick = async () => {
      btn.disabled = true;
      try {
        const r = await api("import_commit", { name: name.value, rows: usable() });
        imported = true;
        toast(`「${r.name}」：新增 ${r.added} 个词${r.existed ? `，另有 ${r.existed} 个原来就在词库` : ""}，都会优先学`);
        layer.close();
      } catch (e) { fail(e); btn.disabled = false; }
    };
    fill(foot, h("button", { class: "link grow", type: "button", text: "换一个文件", onclick: step1 }), btn);
    refresh();
  }

  const layer = openLayer("modal", (close) => [
    h("div", { class: "modal-head" }, h("div", {}, h("span", { class: "label", text: "IMPORT · 导入词表" }), h("h3", { class: "h2", style: { "margin-top": "10px" }, text: "导入自己的词表" })),
      h("button", { class: "icon-btn", "aria-label": "关闭", html: icons.close, onclick: close })),
    body, foot], { width: "680px", onClose: () => imported && onDone() });
  step1();
}
