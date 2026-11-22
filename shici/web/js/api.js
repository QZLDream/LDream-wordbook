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
// 语速（设置里的「语速」）：1 = 原速。不是 1 时用 <audio> 播放，浏览器会保持音调不变地加快 / 放慢
let rate = 1;
export function setVoiceRate(r) {
  rate = Number(r) || 1;
  try { window.ShiciAndroid?.setSpeechRate?.(rate); } catch { /* 旧版安卓外壳没有这个接口 */ }
}
// 是不是桌面版（启动时 app.js 会设置）；不直接引用 app.js，避免循环依赖
const app_desktop = () => !!window.__shiciDesktop;
function webSpeech(text, lang) {
  if (window.ShiciAndroid) return window.ShiciAndroid.speak(text, lang);  // 安卓 WebView 没有网页朗读，交给系统 TTS
  if (!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = lang === "ja" ? "ja-JP" : "en-US";
  u.rate = 0.92 * rate;
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}

// 发音用 Web Audio 播放：整段先解码进内存再播，不会因为电脑忙而断续（以前交给 Qt 播放器边解码边播，偶尔会掉几毫秒，听起来是“噼”的爆音）；
// 开头 4ms 淡入、打断时 15ms 淡出，避免波形被硬切产生咔哒声。解码好的音频留一小份缓存，重复播放不用再解码。
let actx = null, voiceOut = null, playing = null, webAudioOk = true;
const decoded = new Map();
function audioCtx() {
  if (!actx) {
    const C = window.AudioContext || window.webkitAudioContext;
    if (!C) return null;
    actx = new C({ latencyHint: "playback" });
    voiceOut = actx.createGain();
    voiceOut.connect(actx.destination);
  }
  if (actx.state === "suspended") actx.resume().catch(() => {});
  return actx;
}
let playingEl = null;
function stopVoice() {
  if (playingEl) { playingEl.pause(); playingEl = null; }
  if (!playing) return;
  const { src, gain } = playing, t = actx.currentTime;
  gain.gain.cancelScheduledValues(t);
  gain.gain.setValueAtTime(gain.gain.value, t);
  gain.gain.linearRampToValueAtTime(0, t + 0.015);
  try { src.stop(t + 0.02); } catch { /* 已经停了 */ }
  playing = null;
}
// 变速播放：Web Audio 一变速就变调（声音发尖 / 发闷），<audio> 的 playbackRate 默认保持音调
async function playStretched(b64) {
  stopVoice();
  const el = new Audio("data:audio/mpeg;base64," + b64);
  el.preservesPitch = true;
  el.playbackRate = rate;
  playingEl = el;
  await el.play();
  await new Promise((res) => { el.onended = el.onpause = el.onerror = res; });
  if (playingEl === el) playingEl = null;
}
async function playClip(key, b64) {
  if (Math.abs(rate - 1) > 0.01) return playStretched(b64);
  const c = audioCtx();
  if (!c) throw new Error("no web audio");
  let buf = decoded.get(key);
  if (!buf) {
    const bytes = Uint8Array.from(atob(b64), (ch) => ch.charCodeAt(0));
    buf = await c.decodeAudioData(bytes.buffer);
    decoded.set(key, buf);
    if (decoded.size > 60) decoded.delete(decoded.keys().next().value);
  }
  stopVoice();
  const src = c.createBufferSource(), gain = c.createGain(), t = c.currentTime + 0.01;
  src.buffer = buf;
  gain.gain.setValueAtTime(0, t);
  gain.gain.linearRampToValueAtTime(1, t + 0.004);
  src.connect(gain).connect(voiceOut);
  src.start(t);
  const me = { src, gain };
  playing = me;
  // 播完（或被下一段打断）才返回，方便接着读下一段（比如单词读完再读例句）
  await new Promise((res) => { src.onended = () => { if (playing === me) playing = null; res(); }; });
}

// 返回 true 表示等到了播放结束；false 表示交给了系统朗读等，不知道什么时候读完
export async function speak(text, lang = "en", kind = "word") {
  if (!text) return false;
  try {
    const web = webAudioOk && !!(window.AudioContext || window.webkitAudioContext);
    const r = await api("speak", { text, lang, kind, web });
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
    if (r.handled) { if (r.source === "system") stopVoice(); return false; }
    if (r.audio) {
      if (web) {
        try { await playClip(`${kind}|${lang}|${text}|${r.source}`, r.audio); return true; } catch {
          // 解码不了（个别系统的内置浏览器不支持 MP3）：以后都交回桌面程序播放
          webAudioOk = false;
          if (app_desktop()) { await api("speak", { text, lang, kind, web: false }); return false; }
        }
      }
      if (audio) audio.pause();
      const el = audio = new Audio("data:audio/mpeg;base64," + r.audio);
      el.playbackRate = rate;
      try {
        await el.play();
        await new Promise((res) => { el.onended = el.onpause = res; });
        return true;
      } catch { webSpeech(text, lang); return false; }
    }
    webSpeech(text, lang);
    return false;
  } catch { webSpeech(text, lang); return false; }
}
