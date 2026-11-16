// 复习：看词回忆 → 显示答案 → 忘记 / 模糊 / 认识。也负责拼写模式和自由拼写练习。
import { api, speak } from "../api.js";
import { h, $, fill, icons, letters, defBlock, exampleEl, toast, fail, ms, wait, EASE, reduced, countUp } from "../ui.js";
import { app, refreshNav } from "../app.js";
import * as sfx from "../sfx.js";

const RATES = [
  { r: 1, cls: "again", name: "忘记" },
  { r: 2, cls: "hard", name: "模糊" },
  { r: 3, cls: "good", name: "认识" },
];
const norm = (s) => (s || "").trim().toLowerCase().replace(/\s+/g, " ");

export async function mount(root, query) {
  const mode = ["spell", "practice"].includes(query.mode) ? query.mode : "recall";
  const S = { mode, card: null, counts: null, revealed: false, busy: true, done: false, shownAt: 0, stage: null, spell: null,
              session: { n: 0, right: 0, start: Date.now() }, practice: [], practiceTotal: 0 };

  const bar = h("i");
  const nums = { new: h("b", { class: "num", text: "0" }), learning: h("b", { class: "num", text: "0" }), review: h("b", { class: "num", text: "0" }) };
  const undoBtn = h("button", { class: "icon-btn", title: "撤销上一个 (Z)", "aria-label": "撤销", html: icons.undo, onclick: () => undo() });
  const host = h("div", { class: "rv-host" });
  const modeName = { recall: "REVIEW<span class=\"sep\">·</span>复习", spell: "SPELL<span class=\"sep\">·</span>拼写", practice: "PRACTICE<span class=\"sep\">·</span>自由拼写" }[mode];
  root.append(h("div", { class: "review" },
    h("div", { class: "rv-top" },
      h("div", { class: "rv-bar" }, bar),
      h("span", { class: "label", html: `<b>01</b> / ${modeName}` }),
      h("div", { class: "rv-counts" },
        mode === "practice" ? null : [["新词", "new"], ["学习中", "learning"], ["待复习", "review"]].map(([t, k]) => h("span", {}, h("span", { class: "label", text: t }), nums[k])),
        mode === "practice" ? null : undoBtn,
        h("a", { class: "icon-btn", href: "#/home", title: "退出 (Esc)", "aria-label": "退出", html: icons.close })),
    ),
    host));

  function updateTop() {
    const c = S.counts;
    if (mode === "practice") {
      bar.style.transform = `scaleX(${S.practiceTotal ? S.session.n / S.practiceTotal : 0})`;
      return;
    }
    if (!c) return;
    for (const k of Object.keys(nums)) {
      if (nums[k].textContent !== String(c[k])) {
        nums[k].textContent = c[k];
        nums[k].classList.add("bump");
        setTimeout(() => nums[k].classList.remove("bump"), 500);
      }
    }
    const all = c.done + c.total;
    bar.style.transform = `scaleX(${all ? c.done / all : 0})`;
    undoBtn.style.visibility = S.canUndo ? "visible" : "hidden";
    refreshNav(c);
  }

  const speakCard = () => S.card && speak(S.card.term, S.card.lang);

  // ---------------------------------------------------------------- 出牌
  async function show(card, back = false) {
    const old = S.stage;
    if (old) {
      old.classList.add("out");
      setTimeout(() => old.remove(), ms(300));
      await wait(210);
    }
    S.card = card; S.revealed = false; S.spell = null;
    if (!card) return showDone();
    const useSpell = mode !== "recall" && !card.is_new;
    const stage = useSpell ? buildSpell(card) : buildRecall(card);
    if (back) stage.classList.add("in-back");
    host.append(stage);
    S.stage = stage;
    S.shownAt = performance.now();
    S.busy = false;
    if (useSpell) S.spell.input.focus();
    else if (app.settings.autoplay) speakCard();
  }

  function tagText(card) {
    const src = card.sources?.[0] ? ` · ${card.sources[0]}` : "";
    if (card.is_new) return "NEW · 新词" + src;
    if (card.state !== 2) return "LEARNING · 学习中" + src;
    return `REVIEW · 第 ${card.reps + 1} 次` + src;
  }
  const isLong = (card) => card.term.length > (card.lang === "ja" ? 6 : 13);
  const readingText = (card) => (card.reading ? (card.lang === "ja" ? card.reading : `/${card.reading}/`) : "");

  function buildRecall(card) {
    const word = h("div", { class: "rv-word" },
      h("span", { class: "label rv-tag", text: tagText(card) }),
      h("h1", { class: "term" + (isLong(card) ? " long" : ""), lang: card.lang }, letters(card.term)),
      h("div", { class: "reading" }, readingText(card),
        h("button", { class: "icon-btn", title: "朗读 (R)", "aria-label": "朗读", html: icons.speaker, onclick: (e) => { e.stopPropagation(); speakCard(); } })));
    const examples = app.settings.show_examples ? card.examples.slice(0, 2) : [];
    const note = h("textarea", { class: "note-box", placeholder: "写一句帮自己记住它的话…", rows: 2 });
    note.value = card.note || "";
    note.addEventListener("change", () => api("item_update", { id: card.id, note: note.value }).then(() => { card.note = note.value; toast("助记已保存"); }).catch(fail));
    const iv = card.intervals;
    const stage = h("div", { class: "rv-stage" },
      h("div", { class: "rv-main", "data-sfx": "none", onclick: () => reveal() },
        word,
        h("div", { class: "rv-hint" },
          h("span", { class: "label", text: "在心里回忆发音和释义" }),
          h("button", { class: "btn ghost" }, "显示答案", h("kbd", { text: "SPACE" }))),
        h("div", { class: "rv-answer" }, h("div", { class: "rule red" }), defBlock(card.definition, 6, { class: "scroll" }),
          card.auto_def ? h("p", { class: "auto-def", text: "这条中文释义是程序自动匹配的，仅供参考；可在设置里切换成英日释义。" }) : null)),
      h("div", { class: "rv-side" },
        h("div", { class: "slab" }, h("div", { class: "inner" },
          h("div", {}, h("span", { class: "label", text: "EXAMPLES · 例句" }),
            examples.length ? examples.map((ex) => exampleEl(ex, card.term, card.lang)) : h("div", { class: "ex none", text: "这个词暂时没有例句，可以在词库里自己加。" })),
          h("div", {}, h("span", { class: "label", text: "MEMO · 助记" }), note),
          h("div", { class: "rv-meta" },
            h("div", {}, h("span", { class: "label", text: "已复习" }), h("span", { class: "num", text: `${card.reps} 次` })),
            h("div", {}, h("span", { class: "label", text: "遗忘" }), h("span", { class: "num", text: `${card.lapses} 次` })),
            h("div", {}, h("span", { class: "label", text: "认识后下次" }), h("span", { class: "num", text: iv["3"] }))))),
        h("div", { class: "slash" })),
      h("div", { class: "rv-actions", "data-sfx": "none" }, RATES.map((x, i) =>
        h("button", { class: `rate ${x.cls}`, "data-r": x.r, style: { "--i": i }, onclick: () => rate(x.r) },
          h("span", { class: "top" }, h("span", { class: "name", text: x.name }), h("kbd", { text: x.r })),
          h("span", { class: "iv", text: iv[String(x.r)] + "后" })))),
      h("button", { class: "rv-easy", "data-sfx": "none", onclick: () => rate(4) }, "太简单了", h("kbd", { text: "4" }), `直接安排到 ${iv["4"]}后`));
    stage._word = word;
    stage._note = note;
    return stage;
  }

  function reveal() {
    if (S.revealed || S.busy || !S.stage || S.spell) return;
    S.revealed = true;
    sfx.play("flip");
    const stage = S.stage, word = stage._word, term = $(".term", word);
    const a = word.getBoundingClientRect(), aw = term.getBoundingClientRect().width;
    stage.classList.add("revealed");
    const b = word.getBoundingClientRect(), bw = term.getBoundingClientRect().width;
    if (!reduced() && bw > 0) {
      // 单词从屏幕中央滑到左上角：先量出前后位置，再用 transform 补间
      word.animate([{ transform: `translate(${a.left - b.left}px, ${a.top - b.top}px) scale(${aw / bw})` }, { transform: "none" }],
        { duration: 820, easing: EASE });
    }
    if (!app.settings.autoplay) speakCard();
  }

  // ---------------------------------------------------------------- 评分
  async function rate(r) {
    if (S.busy || !S.card || (!S.revealed && !S.spell)) return;
    S.busy = true;
    const card = S.card;
    S.stage.querySelector(`.rate[data-r="${r}"]`)?.classList.add("picked");
    S.session.n++;
    if (r > 1) S.session.right++;
    if (!S.spell) sfx.play(["again", "hard", "good", "easy"][r - 1]);
    try {
      if (mode === "practice") {
        await wait(140);
        updateTop();
        return show(S.practice.shift() || null);
      }
      const [res] = await Promise.all([
        api("answer", { id: card.id, rating: r, elapsed_ms: Math.round(performance.now() - S.shownAt), mode: S.spell ? "spell" : "recall" }),
        wait(140)]);
      S.counts = res.counts; S.canUndo = res.can_undo;
      updateTop();
      await show(res.card);
    } catch (e) {
      fail(e);
      S.session.n--;
      S.stage?.querySelector(".picked")?.classList.remove("picked");
      S.busy = false;
    }
  }

  async function undo() {
    if (S.busy || mode === "practice") return;
    S.busy = true;
    try {
      const r = await api("undo");
      if (!r.undone) { S.busy = false; return toast("没有可以撤销的"); }
      S.session.n = Math.max(0, S.session.n - 1);
      S.counts = r.counts; S.canUndo = r.can_undo; S.done = false;
      updateTop();
      await show(r.card, true);
      toast("已撤销上一个");
    } catch (e) { fail(e); S.busy = false; }
  }

  // ---------------------------------------------------------------- 拼写
  function buildSpell(card) {
    const input = h("input", { type: "text", autocomplete: "off", autocapitalize: "off", spellcheck: "false", placeholder: "· · · · ·", lang: card.lang, "aria-label": "输入单词" });
    const verdict = h("div", { class: "verdict" });
    const prompt = (card.definition || "").split("\n").slice(0, 3).join("　");
    const box = h("div", { class: "spell" },
      h("span", { class: "label rv-tag", text: mode === "practice" ? "PRACTICE · 练习" + (card.sources?.[0] ? ` · ${card.sources[0]}` : "") : tagText(card).replace(/^[A-Z]+/, "SPELL") }),
      h("p", { class: "prompt rise", text: prompt || "（这个词还没有释义）" }),
      h("div", { class: "slots rise", style: { "--i": 1 } }, input),
      verdict,
      h("div", { class: "tools rise", style: { "--i": 2 } },
        h("button", { class: "btn ghost sm", onclick: () => { speakCard(); input.focus(); } }, "听发音"),
        h("button", { class: "btn ghost sm", onclick: () => hint() }, "提示", h("kbd", { text: "TAB" })),
        h("button", { class: "btn ghost sm", onclick: () => check(true) }, "不会"),
        h("button", { class: "btn sm", onclick: () => enter() }, "确认", h("kbd", { text: "ENTER" }))));
    S.spell = { input, verdict, box, hinted: false, checked: false, wrong: false };
    return h("div", { class: "rv-stage" }, h("div", { class: "rv-main" }, box));
  }

  function hint() {
    const sp = S.spell, card = S.card;
    if (!sp || sp.checked) return;
    sp.hinted = true;
    const answer = card.lang === "ja" && card.reading ? card.reading : card.term;
    fill(sp.verdict, h("span", { class: "label rise", text: `提示：${answer[0]}${" ·".repeat(Math.max(0, answer.length - 1))}　共 ${answer.length} 个字` }));
    sp.input.focus();
  }

  function check(giveUp = false) {
    const sp = S.spell, card = S.card;
    if (!sp || sp.checked || S.busy) return;
    const val = norm(sp.input.value);
    if (!val && !giveUp) return sp.input.focus();
    const answers = [card.term, card.lang === "ja" ? card.reading : null].filter(Boolean).map(norm);
    const ok = !giveUp && answers.includes(val);
    sp.checked = true;
    sp.input.readOnly = true;
    const truth = h("span", { class: "truth", lang: card.lang });
    if (ok) truth.textContent = card.term;
    else [...card.term].forEach((ch, i) => truth.append(val[i] === ch.toLowerCase() ? ch : h("u", { text: ch })));
    sp.box.classList.add(ok ? "ok" : "bad");
    sfx.play(ok ? "ok" : "error");
    fill(sp.verdict, 
      h("span", { class: "label rise", text: ok ? (sp.hinted ? "对了 · 用了提示" : "对了") : (giveUp ? "正确拼写" : "不对 · 正确拼写") }),
      h("span", { class: "rise", style: { "--i": 1 } }, truth, readingText(card) ? h("span", { class: "reading", style: { "margin-left": "14px" }, text: readingText(card) }) : null),
      ok ? null : h("span", { class: "label rise", style: { "--i": 2 }, text: "按 ENTER 继续" }));
    speakCard();
    sp.box.querySelectorAll(".tools .ghost").forEach((b) => (b.style.display = "none"));
    if (ok) { sp.box.querySelector(".tools").style.visibility = "hidden"; setTimeout(() => rate(sp.hinted ? 2 : 3), ms(950)); }
    else { sp.wrong = true; sp.box.querySelector(".tools .btn:last-child").firstChild.textContent = "继续"; }
  }
  const enter = () => { const sp = S.spell; if (!sp) return; if (!sp.checked) check(); else if (sp.wrong) rate(1); };

  // ---------------------------------------------------------------- 结束
  function showDone() {
    S.done = true; S.busy = false; S.spell = null;
    const n = S.session.n, mins = Math.max(1, Math.round((Date.now() - S.session.start) / 60000));
    const br = () => h("br");
    let title, sub;
    if (mode === "practice") {
      title = n ? ["练习", br(), "结束了。"] : ["还没有", br(), "学过的词。"];
      sub = n ? "自由练习不会改动复习安排。" : "先背几个词，再回来练拼写。";
    } else if (n) {
      title = ["今天的词", br(), "背完了。"];
      sub = "到期的词明天会自己回来，不用惦记。";
    } else {
      title = ["现在没有", br(), "要背的词。"];
      sub = "可以去词库加一本词书，或者做一组自由拼写练习。";
    }
    const stat = (name, val, suffix = "") => { const el = h("span", { class: "num", text: "0" }); countUp(el, val, { fmt: (v) => Math.round(v) + suffix }); return h("div", {}, h("span", { class: "label", text: name }), el); };
    const stage = h("div", { class: "rv-stage" }, h("div", { class: "done" },
      h("span", { class: "label rise", html: "<b>01</b> / DONE<span class=\"sep\">·</span>完成" }),
      h("h1", { class: "display rise", style: { "--i": 1 } }, title),
      h("p", { class: "home-sub rise", style: { "--i": 2 }, text: sub }),
      n ? h("div", { class: "done-stats rise", style: { "--i": 3 } }, stat("本次", n, " 次"), stat("用时", mins, " 分"), stat("记住", Math.round((S.session.right / n) * 100), "%")) : h("div", { style: { height: "36px" } }),
      h("div", { class: "home-cta rise", style: { "--i": 4 } },
        h("a", { class: "btn", href: "#/home" }, "回到今日", h("span", { class: "arr", text: "→" })),
        mode === "practice" ? (n ? h("button", { class: "btn ghost", onclick: () => restartPractice() }, "再练一组") : null)
                            : h("a", { class: "btn ghost", href: "#/review?mode=practice" }, "自由拼写练习"))));
    host.append(stage);
    S.stage = stage;
    if (n) setTimeout(() => sfx.play("done"), 260);
    if (mode !== "practice") refreshNav();
  }

  async function restartPractice() {
    S.session = { n: 0, right: 0, start: Date.now() };
    S.done = false;
    S.practice = (await api("practice", { n: 20 })).cards;
    S.practiceTotal = S.practice.length;
    updateTop();
    show(S.practice.shift() || null);
  }

  // ---------------------------------------------------------------- 键盘
  app.keyHandler = (e, typing) => {
    const k = e.key.toLowerCase();
    if (k === "escape") { location.hash = "#/home"; return true; }
    if (S.done) { if (k === "enter" && !typing) { location.hash = "#/home"; return true; } return false; }
    if (S.spell) {
      if (k === "enter") { enter(); return true; }
      if (k === "tab") { hint(); return true; }
      return false;
    }
    if (typing) { if (k === "enter" && !e.shiftKey) { e.target.blur(); return true; } return false; }
    if (k === "z") { undo(); return true; }
    if (e.ctrlKey || e.metaKey || e.altKey) return false;
    if (k === "r") { speakCard(); return true; }
    if (k === "t" && S.revealed) { S.stage?.querySelector(".ex-say")?.click(); return true; }  // 读第一条例句
    if (!S.revealed) { if (k === " " || k === "enter") { reveal(); return true; } return false; }
    if ("1234".includes(k)) { rate(+k); return true; }
    if (k === "e") { S.stage?._note?.focus(); return true; }
    return k === " ";
  };

  // ---------------------------------------------------------------- 开始
  try {
    if (mode === "practice") await restartPractice();
    else {
      const r = await api("next");
      S.counts = r.counts; S.canUndo = r.can_undo;
      updateTop();
      await show(r.card);
    }
  } catch (e) { fail(e); }
}
