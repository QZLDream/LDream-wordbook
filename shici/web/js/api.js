// 和本机后端通信。口令在启动时由程序放进地址里（#t=...），之后存在 sessionStorage。
let token = sessionStorage.getItem("shici-token") || "";
const m = location.hash.match(/^#t=([\w-]+)/);
if (m) {
  token = m[1];
  sessionStorage.setItem("shici-token", token);
  history.replaceState(null, "", location.pathname + "#/home");
}

export async function api(name, params) {
  const res = await fetch("/api/" + name, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Shici-Token": token },
    body: JSON.stringify(params || {}),
  });
  const json = await res.json().catch(() => ({ ok: false, error: "连接不上程序后台" }));
  if (!json.ok) throw new Error(json.error || "出错了");
  return json.data;
}

let audio = null;
const warned = {};
function webSpeech(text, lang) {
  if (!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = lang === "ja" ? "ja-JP" : "en-US";
  u.rate = 0.92;
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}

// 朗读。后台按“内置语音包 → 在线发音 → 系统语音”的顺序找（顺序随设置变化）：
// 桌面版由后台直接播放；在浏览器里打开时后台把音频传回来，由这里播放；都没有就用浏览器自带的朗读。
// kind = "sentence" 时朗读例句：先找本机缓存，再联网取（取到后永久缓存），最后用系统语音。
export async function speak(text, lang = "en", kind = "word") {
  if (!text) return;
  try {
    const r = await api("speak", { text, lang, kind });
    const name = (r.missing || lang) === "ja" ? "日语" : "英语";
    if (r.missing && r.kind === "sentence") {
      if (!warned["s" + r.missing]) {
        warned["s" + r.missing] = true;
        document.dispatchEvent(new CustomEvent("shici-toast", { detail: `例句发音要联网取一次（之后会存在本机），现在没取到，系统里也没有${name}语音。联网后再点一次就好。` }));
      }
    } else if (r.missing && !warned[r.missing]) {
      warned[r.missing] = true;
      document.dispatchEvent(new CustomEvent("shici-toast", { detail: `「${text}」不在内置语音包里，联网也没取到发音，系统里又没有${name}语音，所以读不出来。联网后再试一次就会缓存下来。` }));
    }
    if (r.handled) return;
    if (r.audio) {
      if (audio) audio.pause();
      audio = new Audio("data:audio/mpeg;base64," + r.audio);
      audio.play().catch(() => webSpeech(text, lang));
    } else webSpeech(text, lang);
  } catch { webSpeech(text, lang); }
}
