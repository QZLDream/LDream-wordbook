// 字体设置：把“标题和单词 / 正文”两个选择变成 CSS 变量，导入的字体用 @font-face 加载。
export const SERIF_FALLBACK = '"Shici Serif", "Noto Serif SC", "Source Han Serif SC", "Songti SC", "SimSun", serif';
export const SANS_FALLBACK = '"Shici Sans", "Inter", "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Hiragino Sans", "Yu Gothic UI", "Noto Sans CJK SC", sans-serif';
const quote = (name) => `"${String(name).replace(/["\\\n]/g, "")}"`;

// 把设置里的值变成 font-family 列表；"" 表示跟随配色（返回 null）
export function family(value, userFonts, slot) {
  const [kind, ...rest] = (value || "").split(":");
  const val = rest.join(":");
  const fb = slot === "title" ? SERIF_FALLBACK : SANS_FALLBACK;
  if (kind === "builtin") return val === "serif" ? SERIF_FALLBACK : SANS_FALLBACK;
  if (kind === "system" && val) return `${quote(val)}, ${fb}`;
  if (kind === "user" && userFonts.some((f) => f.id === val)) return `"ShiciUser-${val}", ${fb}`;
  return null;
}

export function applyFonts(settings, userFonts = []) {
  let el = document.getElementById("shici-fonts");
  if (!el) { el = document.createElement("style"); el.id = "shici-fonts"; document.head.append(el); }
  const faces = userFonts.map((f) => `@font-face { font-family: "ShiciUser-${f.id}"; src: url("/userfonts/${f.file}") format("${f.format}"); font-display: swap; }`);
  const title = family(settings.font_title, userFonts, "title"), body = family(settings.font_body, userFonts, "body");
  const vars = [];
  if (title) vars.push(`--serif: ${title} !important;`, `--serif-ja: ${title} !important;`);
  if (body) vars.push(`--sans: ${body} !important;`);
  el.textContent = faces.join("\n") + (vars.length ? `\nhtml[data-palette] { ${vars.join(" ")} }` : "");
}
