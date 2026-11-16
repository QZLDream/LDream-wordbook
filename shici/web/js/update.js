// 外部链接和检查更新
import { api } from "./api.js";
import { h, icons, toast, openLayer } from "./ui.js";
import { app } from "./app.js";

// 用系统浏览器打开网页（桌面版交给后台；浏览器里直接开新标签页）
export async function openLink(url) {
  try { if ((await api("open_url", { url })).opened) return; } catch { /* 往下试 */ }
  window.open(url, "_blank", "noopener");
}

async function copy(text) {
  try { if ((await api("clipboard_copy", { text })).copied) return true; } catch { /* 往下试 */ }
  try { await navigator.clipboard.writeText(text); return true; } catch { return false; }
}

// 百度网盘：顺手把提取码复制好
export async function openNetdisk(links = app.info.links) {
  const ok = await copy(links.netdisk_code);
  toast(ok ? `提取码 ${links.netdisk_code} 已复制` : `提取码：${links.netdisk_code}`, 4200);
  openLink(links.netdisk);
}

// manual=true：设置里点「立即检查」，结果都要告诉用户；启动时的自动检查只在有新版本时出声
export async function checkUpdate(manual = false) {
  let r;
  try { r = await api("update_check"); } catch (e) { if (manual) toast(e.message || String(e), 4200); return; }
  if (!r.ok) {
    if (manual) toast("连不上 GitHub，没能检查更新。可以去百度网盘看看有没有新版本。", 5200);
    return;
  }
  if (!r.newer) {
    if (manual) toast(`已经是最新版（v${r.current}）`);
    return;
  }
  const notes = (r.notes || "").replace(/\r/g, "").split("\n").map((s) => s.replace(/^#+\s*/, "").replace(/\*\*/g, "")).filter((s) => s.trim()).slice(0, 14).join("\n");
  openLayer("modal", (close) => [
    h("div", { class: "modal-head" },
      h("div", {}, h("span", { class: "label", text: "UPDATE · 新版本" }), h("h3", { class: "h2", style: { "margin-top": "10px" }, text: `发现新版本 v${r.latest}` })),
      h("button", { class: "icon-btn", "aria-label": "关闭", html: icons.close, onclick: close })),
    h("div", { class: "modal-body" },
      h("p", { class: "note", text: `当前是 v${r.current}。下载新版本的压缩包，解压覆盖原来的文件夹就行，学习记录不在程序文件夹里，不会丢。` }),
      notes ? h("pre", { class: "update-notes scroll", text: notes }) : null),
    h("div", { class: "modal-foot" },
      h("button", { class: "btn ghost sm", onclick: close }, "以后再说"),
      h("button", { class: "btn ghost sm", onclick: () => openNetdisk(r.links) }, "百度网盘下载"),
      h("button", { class: "btn sm", autofocus: true, onclick: () => { openLink(r.url); close(); } }, "去 GitHub 下载")),
  ], { width: "560px" });
}
