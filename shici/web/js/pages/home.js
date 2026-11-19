// 今日：今天要背多少、连续天数、遗忘曲线示意。
import { api } from "../api.js";
import { h, countUp, pct } from "../ui.js";
import { app, refreshNav } from "../app.js";
import { memoryIllustration } from "../charts.js";

export async function mount(root) {
  const d = await api("home");
  const c = d.counts, st = d.states;
  refreshNav(c);
  const learned = st.learning + st.young + st.mature;
  const tomorrow = d.forecast[1]?.count ?? 0;

  let label = "00 / TODAY", title, sub, cta;
  const numEl = h("em", { text: "0" });
  if (!d.has_items) {
    title = ["从一本词书", h("br"), "开始。"];
    sub = "选一本词书，或者导入你自己的词表。每天花十来分钟，剩下的交给遗忘曲线。";
    cta = [h("a", { class: "btn", href: "#/library" }, "去选词书", h("span", { class: "arr", text: "→" }))];
  } else if (c.total > 0) {
    title = c.done > 0 ? ["还剩 ", numEl, " 个词，", h("br"), "慢慢来。"] : ["今天有 ", numEl, " 个词", h("br"), "等你回来。"];
    sub = c.done > 0 ? `今天已经背了 ${c.done} 次。不用赶，背完为止。` : "先复习到期的词，再学新词。想不起来也没关系，照实选就好。";
    cta = [
      h("a", { class: "btn", href: "#/review" }, c.done > 0 ? "继续复习" : "开始复习", h("span", { class: "arr", text: "→" })),
      h("a", { class: "btn ghost", href: "#/review?mode=spell" }, "拼写模式"),
    ];
  } else if (c.done > 0) {
    title = ["今天的词", h("br"), "背完了。"];
    sub = tomorrow ? `明天有 ${tomorrow} 个词到期。今天可以到此为止，也可以再练练拼写。` : "今天可以到此为止，也可以再练练拼写。";
    cta = [h("a", { class: "btn", href: "#/review?mode=practice" }, "自由拼写练习", h("span", { class: "arr", text: "→" })),
           h("a", { class: "btn ghost", href: "#/stats" }, "看看统计")];
  } else {
    title = ["今天没有", h("br"), "要背的词。"];
    sub = c.unseen > 0 ? "每日新词数现在是 0，可以在设置里调高。" : "词库里的词都学过了，可以再加一本词书。";
    cta = [h("a", { class: "btn", href: c.unseen > 0 ? "#/settings" : "#/library" }, c.unseen > 0 ? "去设置" : "去词库", h("span", { class: "arr", text: "→" }))];
  }

  const q = (name, n, i) => { const el = h("span", { class: "num", text: "0" }); countUp(el, n); return h("div", { class: "rise", style: { "--i": i } }, h("span", { class: "label", text: name }), el); };
  // 名称里“ · 30 天”这类补充说明手机上放不下，单独包一层（phone.css 里隐藏）
  const strip = (name, text) => { const [main, more] = name.split(" · ");
    return h("div", {}, h("span", { class: "label" }, main, more ? h("span", { class: "more", text: " · " + more }) : null), h("span", { class: "num", text })); };
  const streakEl = h("span", { text: "0" });

  root.append(h("div", { class: "home" },
    h("div", { class: "home-main" },
      h("span", { class: "label rise", style: { "--i": 0 }, html: `<b>00</b> / TODAY<span class="sep">·</span>今日` }),
      h("h1", { class: "display rise", style: { "--i": 1 } }, title),
      h("p", { class: "home-sub rise", style: { "--i": 2 }, text: sub }),
      d.has_items ? h("div", { class: "home-queue" }, q("待复习", c.review, 3), q("学习中", c.learning, 4), q("新词", c.new, 5)) : h("div", { class: "home-queue" }),
      h("div", { class: "home-cta rise", style: { "--i": 6 } }, cta),
      h("div", { class: "home-strip rise", style: { "--i": 8 } },
        h("div", { class: "rule", style: { "--d": "700ms" } }),
        strip("已学", learned.toLocaleString("en-US")), strip("已掌握", st.mature.toLocaleString("en-US")),
        strip("保持率 · 30 天", pct(d.retention.rate)), strip("今日用时", d.today.minutes ? d.today.minutes + " 分" : "—")),
    ),
    h("div", { class: "home-dark" },
      h("div", { class: "slab" }, h("div", { class: "inner" },
        h("span", { class: "label rise", style: { "--d": "500ms" }, text: "STREAK · 连续学习" }),
        h("div", { class: "big rise", style: { "--d": "600ms" } }, streakEl, h("small", { text: "DAYS" })),
        h("div", { class: "home-curve rise", style: { "--d": "800ms" } },
          memoryIllustration(),
          h("div", { class: "cap" }, h("span", { class: "label", text: "遗忘曲线 · 每复习一次，忘得更慢" }), h("span", { class: "label", text: `FSRS · ${Math.round(app.settings.retention * 100)}%` }))),
      )),
      h("div", { class: "slash" }),
    ),
  ));
  // 手机上把四个数字放进下面那张“连续学习”卡片里，合成一张
  if (matchMedia("(max-width: 720px)").matches) {
    root.querySelector(".home-dark .inner").append(root.querySelector(".home-strip"));
    root.querySelector(".home").append(root.querySelector(".home-cta"));  // 两个按钮放到最下面（卡片下方）
  }
  countUp(numEl, c.total);
  countUp(streakEl, d.streak, { fmt: (v) => String(Math.round(v)).padStart(2, "0") });
  app.keyHandler = (e, typing) => {
    if (typing) return false;
    if ((e.key === "Enter" || e.key === " ") && c.total > 0) { location.hash = "#/review"; return true; }
    return false;
  };
}
