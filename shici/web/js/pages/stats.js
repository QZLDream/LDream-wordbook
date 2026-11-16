// 统计：连续天数、学习量、保持率、未来到期、单词状态、遗忘曲线。
import { api } from "../api.js";
import { h, countUp, pct, bindTips } from "../ui.js";
import { barChart, curveChart, heatmap, fmtDate } from "../charts.js";

export async function mount(root) {
  const s = await api("stats");
  const st = s.states, learned = st.learning + st.young + st.mature;
  const tile = (i, label, value, unit, sub, fmt) => {
    const num = h("span", { text: "0" });
    countUp(num, value ?? 0, fmt ? { fmt } : undefined);
    return h("div", { class: "panel tile rise", style: { "--i": i } }, h("span", { class: "label", text: label }),
      h("span", { class: "num" }, value == null ? "—" : num, unit ? h("small", { text: unit }) : null), h("span", { class: "small mute", text: sub }));
  };
  const chart = (i, cls, label, title, body, legend) => h("div", { class: `panel chart rise ${cls}`, style: { "--i": i } },
    h("div", { class: "chart-head" }, h("div", {}, h("span", { class: "label", text: label }), h("h3", { class: "h3", text: title })),
      legend ? h("div", { class: "legend" }, legend.map(([name, c]) => h("span", {}, h("i", { style: { "--c": c } }), name))) : null), body);

  const today = s.daily[s.daily.length - 1].date;
  const daily = s.daily.map((d) => ({ label: fmtDate(d.date).replace("月", "/").replace("日", ""), review: d.review, new: d.new,
    tip: `${fmtDate(d.date)}<br>复习 ${d.review} · 新词 ${d.new}` }));
  const forecast = s.forecast.map((d, i) => ({ label: i === 0 ? "今天" : fmtDate(d.date).replace("月", "/").replace("日", ""), count: d.count,
    tip: `${i === 0 ? "今天（含已过期）" : fmtDate(d.date)}<br>${d.count} 个词到期` }));
  const states = [["未学", st.unseen, "var(--line-2)"], ["学习中", st.learning, "var(--accent)"], ["复习中", st.young, "var(--ink)"], ["已掌握", st.mature, "var(--sage)"]];
  const total = Math.max(1, st.unseen + learned);
  const m = s.memory;
  const page = h("div", { class: "page-pad scroll", style: { height: "100%" } },
    h("div", { class: "page-head" }, h("div", { class: "rise" }, h("span", { class: "label", html: "<b>03</b> / STATS<span class=\"sep\">·</span>统计" }), h("h2", { class: "h2", text: "记了多少，忘了多少" }))),
    h("div", { class: "stats-grid" },
      tile(1, "连续学习", s.streak, "天", `累计学习 ${s.totals.days} 天`),
      tile(2, "已学单词", learned, "词", `其中 ${st.mature} 个已掌握`),
      tile(3, "保持率 · 30 天", s.retention.rate == null ? null : s.retention.rate * 100, "%", s.retention.n ? `到期复习 ${s.retention.n} 次里答对的比例` : "复习过到期的词之后才有", (v) => v.toFixed(0)),
      tile(4, "累计用时", s.totals.hours, "小时", `共 ${s.totals.reviews.toLocaleString("en-US")} 次评分`, (v) => v.toFixed(1)),
      chart(5, "span-7", "ACTIVITY · 最近 30 天", "每天背了多少次",
        barChart(daily, [{ key: "review", color: "var(--ink)" }, { key: "new", color: "var(--accent)" }], { every: 5 }), [["复习", "var(--ink)"], ["新词", "var(--accent)"]]),
      chart(6, "span-5", "WORDS · 单词状态", `词库里共 ${(st.total).toLocaleString("en-US")} 个词`,
        h("div", {}, h("div", { class: "statebar" }, states.filter((x) => x[1]).map(([n, v, c]) => h("i", { style: { "--c": c, flex: `${v / total} 0 0` }, "data-tip": `${n}<br>${v} 词` }))),
          h("div", { class: "statelist" }, states.map(([n, v, c]) => h("div", {}, h("i", { style: { "--c": c } }), n, h("span", { class: "num", text: v.toLocaleString("en-US") }))),
            st.suspended ? h("div", {}, h("i", { style: { "--c": "transparent", "box-shadow": "inset 0 0 0 1px var(--line-2)" } }), "已搁置", h("span", { class: "num", text: st.suspended })) : null),
          h("div", { class: "today-mini" }, h("span", { class: "label", text: "TODAY · 今天" }),
            h("div", { class: "kv" }, [["评分", s.today.reviews + " 次"], ["新词", s.today.new + " 个"], ["记住", pct(s.today.accuracy)], ["用时", s.today.minutes + " 分"]]
              .map(([k, v]) => h("div", {}, h("span", { class: "label", text: k }), h("span", { class: "num", text: v })))
            )
          )
        )
      ),
      chart(7, "span-7", "FORECAST · 未来 30 天", "每天有多少词到期", barChart(forecast, [{ key: "count", color: "var(--ink)" }], { every: 5, highlight: 0, height: 268 })),
      chart(8, "span-5", "MEMORY · 遗忘曲线", m.curve ? `一半的词能记住 ${m.median_stability < 10 ? m.median_stability.toFixed(1) : Math.round(m.median_stability)} 天以上` : "复习之后，这里会画出你的曲线",
        h("div", {}, curveChart(m.curve || m.example_curve, { retention: m.retention, height: 240, width: 470,
          marks: m.curve ? [{ t: m.median_stability, label: "保持率降到 90%", accent: true }] : [] }),
          h("p", { class: "small mute", style: { "margin-top": "10px" }, text: m.curve ? "按复习中单词的稳定度中位数画出：不复习的话，记得的概率会沿这条线下降。" : "示意：稳定度 10 天的词，不复习时记得的概率。" }))),
      chart(9, "span-12", "CALENDAR · 最近一年", "每天的学习量", h("div", {}, heatmap(s.heatmap, today),
        h("div", { class: "heat-legend" }, h("span", { text: "少" }),
          [0, 1, 2, 3, 4].map((l) => h("i", { "data-l": l, class: "heat-key" })), h("span", { text: "多" }))))));
  root.append(page);
  bindTips(page);
}
