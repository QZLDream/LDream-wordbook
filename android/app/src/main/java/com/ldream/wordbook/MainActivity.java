package com.ldream.wordbook;

import android.annotation.SuppressLint;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.media.AudioAttributes;
import android.media.MediaPlayer;
import android.net.Uri;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.os.VibratorManager;
import android.provider.MediaStore;
import android.provider.Settings;
import android.speech.tts.TextToSpeech;
import android.util.Base64;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;

import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.FileProvider;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.Locale;

/**
 * 小梦的词书安卓版：界面和电脑版是同一套网页，由手机上运行的 Python 服务（Chaquopy）提供。
 * 这里只做壳：全屏 WebView、系统栏颜色、返回键、选文件、存文件、系统朗读、复制、打开网页。
 */
public class MainActivity extends AppCompatActivity {
    private FrameLayout root;
    private WebView web;
    private TextToSpeech tts;
    private volatile boolean ttsReady;
    private volatile float speechRate = 1f;   // 设置里的「语速」
    private volatile String ttsLangs = null;  // 系统 TTS 能读的语言（"en,ja"），还没初始化完是 null
    private MediaPlayer player;
    private ValueCallback<Uri[]> fileCallback;
    private ActivityResultLauncher<Intent> filePicker;
    private SharedPreferences prefs;
    private boolean loaded;
    private Vibrator vibrator;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences("shell", MODE_PRIVATE);
        int bg = prefs.getInt("bg", Color.parseColor("#F5F5F7"));
        boolean dark = prefs.getBoolean("dark", false);

        // 内容画在系统栏后面，再按系统栏的高度留出边距；边距露出来的颜色跟着主题走
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        root = new FrameLayout(this);
        web = new WebView(this);
        root.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);
        ViewCompat.setOnApplyWindowInsetsListener(root, (v, insets) -> {
            Insets bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout());
            Insets ime = insets.getInsets(WindowInsetsCompat.Type.ime());
            v.setPadding(bars.left, bars.top, bars.right, Math.max(bars.bottom, ime.bottom));
            return WindowInsetsCompat.CONSUMED;
        });
        applyBars(bg, bg, dark);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setTextZoom(100);  // 不跟系统字体大小缩放，否则排版会乱
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(true);
        web.setBackgroundColor(bg);
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        web.addJavascriptInterface(new JsBridge(), "ShiciAndroid");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                String host = u.getHost();
                if ("127.0.0.1".equals(host) || "localhost".equals(host)) return false;
                openUrl(u.toString());  // 外部链接交给浏览器
                return true;
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent i = new Intent(Intent.ACTION_GET_CONTENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                i.setType("*/*");  // 词表、字体、进度文件的类型系统都不一定认得，干脆都让选
                try {
                    filePicker.launch(Intent.createChooser(i, "选择文件"));
                } catch (Exception e) {
                    fileCallback = null;
                    return false;
                }
                return true;
            }
        });
        filePicker = registerForActivityResult(new ActivityResultContracts.StartActivityForResult(), r -> {
            if (fileCallback == null) return;
            Uri[] picked = null;
            if (r.getResultCode() == RESULT_OK && r.getData() != null && r.getData().getData() != null)
                picked = new Uri[]{r.getData().getData()};
            fileCallback.onReceiveValue(picked);
            fileCallback = null;
        });

        // 返回键：先关浮层，再回“今日”，在“今日”再按一次才退出
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (!loaded) { moveTaskToBack(true); return; }
                web.evaluateJavascript("window.__shiciBack ? window.__shiciBack() : false", v -> {
                    if (!"true".equals(v)) moveTaskToBack(true);
                });
            }
        });

        if (Build.VERSION.SDK_INT >= 31) {
            VibratorManager vm = (VibratorManager) getSystemService(Context.VIBRATOR_MANAGER_SERVICE);
            if (vm != null) vibrator = vm.getDefaultVibrator();
        } else {
            vibrator = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
        }

        tts = new TextToSpeech(this, status -> {
            ttsReady = status == TextToSpeech.SUCCESS;
            // 看看系统 TTS 装没装英语 / 日语：没装日语时，它会拿中文的声音去读汉字（只念出中文），不如不读
            StringBuilder sb = new StringBuilder();
            if (ttsReady) {
                try {
                    if (tts.isLanguageAvailable(Locale.US) >= TextToSpeech.LANG_AVAILABLE) sb.append("en");
                    if (tts.isLanguageAvailable(Locale.JAPAN) >= TextToSpeech.LANG_AVAILABLE) sb.append(sb.length() > 0 ? ",ja" : "ja");
                } catch (Exception ignored) { }
            }
            ttsLangs = sb.toString();
        });

        showSplash(bg, dark);
        new Thread(() -> {
            String url;
            try {
                // 在后台线程里启动 Python：第一次要解压运行环境，放在主线程会白屏卡住
                if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
                PyObject m = Python.getInstance().getModule("android_main");
                url = m.callAttr("start", getFilesDir().getAbsolutePath(), new PyBridge()).toString();
            } catch (Throwable e) {
                String msg = String.valueOf(e);
                runOnUiThread(() -> web.loadDataWithBaseURL(null,
                        "<meta name=viewport content='width=device-width'><body style='font:15px sans-serif;padding:24px;color:#333'>"
                                + "<h3>启动失败</h3><p>请把这一页截图发给作者（GitHub 或 B 站 千醉_LDream）。</p><pre style='white-space:pre-wrap;font-size:12px'>"
                                + android.text.Html.escapeHtml(msg) + "</pre></body>", "text/html", "utf-8", null));
                return;
            }
            final String go = url;
            runOnUiThread(() -> { loaded = true; web.loadUrl(go); });
        }).start();
    }

    /** 第一次打开要把词典解压到手机里，要等一会儿：先显示一个小猫的等待页 */
    private void showSplash(int bg, boolean dark) {
        String ink = dark ? "#F5F5F7" : "#18181B";
        String html = "<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'>"
                + "<body style='margin:0;height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;"
                + "background:" + String.format("#%06X", 0xFFFFFF & bg) + ";color:" + ink + ";font:14px sans-serif'>"
                + "<div style='width:96px;height:38px;background:" + ink + ";-webkit-mask:url(file:///android_asset/cat.png) center/contain no-repeat'></div>"
                + "<p style='margin-top:22px;opacity:.55;letter-spacing:.08em'>正在打开…</p>"
                + "<p style='opacity:.4;font-size:12px'>第一次打开要准备词典，大约半分钟</p></body>";
        web.loadDataWithBaseURL("file:///android_asset/", html, "text/html", "utf-8", null);
    }

    private void applyBars(int top, int bottom, boolean dark) {
        root.setBackgroundColor(top);
        getWindow().getDecorView().setBackgroundColor(bottom);
        WindowInsetsControllerCompat c = WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView());
        c.setAppearanceLightStatusBars(!dark);
        c.setAppearanceLightNavigationBars(!dark);
        if (Build.VERSION.SDK_INT < 35) {
            getWindow().setStatusBarColor(top);
            getWindow().setNavigationBarColor(bottom);
        }
    }

    private void openUrl(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Exception ignored) {
        }
    }

    /** 把文件复制到“下载/小梦的词书”里，返回给人看的位置 */
    private String saveToDownloads(File src, String name, String mime) throws Exception {
        if (Build.VERSION.SDK_INT >= 29) {
            ContentValues v = new ContentValues();
            v.put(MediaStore.Downloads.DISPLAY_NAME, name);
            v.put(MediaStore.Downloads.MIME_TYPE, mime);
            v.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/小梦的词书");
            Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
            if (uri == null) throw new Exception("无法写入下载文件夹");
            try (InputStream in = new FileInputStream(src); OutputStream out = getContentResolver().openOutputStream(uri)) {
                copy(in, out);
            }
            return "手机的“下载/小梦的词书/" + name + "”";
        }
        File dir = new File(getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), "");
        dir.mkdirs();
        File dst = new File(dir, name);
        try (InputStream in = new FileInputStream(src); OutputStream out = new FileOutputStream(dst)) {
            copy(in, out);
        }
        return dst.getAbsolutePath();
    }

    private static void copy(InputStream in, OutputStream out) throws Exception {
        byte[] buf = new byte[65536];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
    }

    private static String mimeOf(String name) {
        String n = name.toLowerCase(Locale.ROOT);
        if (n.endsWith(".csv")) return "text/csv";
        if (n.endsWith(".db")) return "application/vnd.sqlite3";
        return "application/octet-stream";
    }

    private void speak(String text, String lang, String path) {
        runOnUiThread(() -> {
            if (player != null) { player.release(); player = null; }
            if (path != null && !path.isEmpty()) {
                try {
                    player = new MediaPlayer();
                    player.setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build());
                    player.setDataSource(path);
                    player.setOnPreparedListener(mp -> {
                        try { if (Math.abs(speechRate - 1f) > 0.01f) mp.setPlaybackParams(mp.getPlaybackParams().setSpeed(speechRate)); }
                        catch (Exception ignored) { }
                        mp.start();
                    });
                    player.prepareAsync();
                    return;
                } catch (Exception ignored) {
                }
            }
            if (!ttsReady) return;
            Locale loc = "ja".equals(lang) ? Locale.JAPAN : Locale.US;
            if (tts.isLanguageAvailable(loc) < TextToSpeech.LANG_AVAILABLE) return;  // 没有这种语言的声音：不拿中文声音硬读
            tts.setLanguage(loc);
            tts.setSpeechRate(("ja".equals(lang) ? 0.95f : 0.9f) * speechRate);
            tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "shici");
        });
    }

    private void copyText(String text) {
        runOnUiThread(() -> {
            ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            cm.setPrimaryClip(ClipData.newPlainText("小梦的词书", text));
        });
    }

    // 局域网同步要收其他设备的广播：不少手机为了省电默认会丢掉 Wi-Fi 广播包，程序在前台时申请收下来
    private WifiManager.MulticastLock multicastLock;

    @Override
    protected void onResume() {
        super.onResume();
        try {
            if (multicastLock == null) {
                WifiManager wm = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
                multicastLock = wm.createMulticastLock("xmcs-lan-sync");
                multicastLock.setReferenceCounted(false);
            }
            multicastLock.acquire();
        } catch (Exception ignored) { }
    }

    @Override
    protected void onPause() {
        try { if (multicastLock != null) multicastLock.release(); } catch (Exception ignored) { }
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (tts != null) tts.shutdown();
        if (player != null) player.release();
        super.onDestroy();
    }

    /** Python 那边（android_main.py）调用的方法 */
    public class PyBridge {
        public void speak(String text, String lang, String path) { MainActivity.this.speak(text, lang, path); }

        public void openUrl(String url) { runOnUiThread(() -> MainActivity.this.openUrl(url)); }

        public void copy(String text) { copyText(text); }

        /** 系统 TTS 能读的语言："en,ja" / "en" / ""；还没初始化完返回 null */
        public String ttsLangs() { return ttsLangs; }

        /** 局域网同步时给电脑看的名字：优先用系统设置里的“设备名称”（比如 Xiaomi 17 Pro），没有就用型号 */
        public String deviceName() {
            try {
                String n = Settings.Global.getString(getContentResolver(), "device_name");
                if (n != null && !n.trim().isEmpty()) return n.trim();
            } catch (Exception ignored) { }
            try {
                String n = Settings.Secure.getString(getContentResolver(), "bluetooth_name");
                if (n != null && !n.trim().isEmpty()) return n.trim();
            } catch (Exception ignored) { }
            return Build.MANUFACTURER + " " + Build.MODEL;
        }

        public String saveFile(String path) {
            try {
                File f = new File(path);
                return saveToDownloads(f, f.getName(), mimeOf(f.getName()));
            } catch (Exception e) {
                return path;
            }
        }
    }

    /** 网页里的脚本调用的方法（window.ShiciAndroid） */
    public class JsBridge {
        /** 设置里的「语速」：系统 TTS 和 MediaPlayer 播放都按这个倍速 */
        @JavascriptInterface
        public void setSpeechRate(float rate) { speechRate = Math.max(0.5f, Math.min(1.5f, rate)); }

        /** 主题变了：系统栏跟着换颜色。top = 顶栏颜色，bottom = 底部标签栏颜色 */
        @JavascriptInterface
        public void setBars(String top, String bottom, boolean dark) {
            runOnUiThread(() -> {
                try {
                    int t = Color.parseColor(top), b = Color.parseColor(bottom);
                    applyBars(t, b, dark);
                    web.setBackgroundColor(b);
                    prefs.edit().putInt("bg", t).putBoolean("dark", dark).apply();
                } catch (Exception ignored) {
                }
            });
        }

        /** 网页里生成的文件（进度文件）：存到“下载”文件夹，再弹出分享，方便直接发到电脑上 */
        @JavascriptInterface
        public String saveFile(String name, String base64, String mime, boolean share) {
            try {
                File dir = new File(getCacheDir(), "out");
                dir.mkdirs();
                File f = new File(dir, name);
                try (OutputStream out = new FileOutputStream(f)) {
                    out.write(Base64.decode(base64, Base64.DEFAULT));
                }
                String where = saveToDownloads(f, name, mime);
                if (share) {
                    Uri uri = FileProvider.getUriForFile(MainActivity.this, getPackageName() + ".files", f);
                    Intent send = new Intent(Intent.ACTION_SEND).setType(mime).putExtra(Intent.EXTRA_STREAM, uri)
                            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    runOnUiThread(() -> startActivity(Intent.createChooser(send, "发送进度文件")));
                }
                return where;
            } catch (Exception e) {
                return "";
            }
        }

        @JavascriptInterface
        public void speak(String text, String lang) { MainActivity.this.speak(text, lang, ""); }

        /** 震动反馈：不同操作用不同的震感。用系统预设的震动效果，支持线性马达的手机上是清脆的“哒”一下 */
        @JavascriptInterface
        public void vibrate(String kind) {
            if (vibrator == null || !vibrator.hasVibrator()) return;
            try {
                if (Build.VERSION.SDK_INT >= 29) {
                    VibrationEffect fx;
                    switch (kind == null ? "" : kind) {
                        case "again": case "error":
                            fx = VibrationEffect.createPredefined(VibrationEffect.EFFECT_DOUBLE_CLICK); break;
                        case "hard":
                            fx = VibrationEffect.createPredefined(VibrationEffect.EFFECT_HEAVY_CLICK); break;
                        case "good": case "easy": case "ok": case "flip":
                            fx = VibrationEffect.createPredefined(VibrationEffect.EFFECT_CLICK); break;
                        case "done":  // 背完一组：轻、轻、重三下
                            fx = VibrationEffect.createWaveform(new long[]{0, 14, 80, 14, 80, 28}, new int[]{0, 110, 0, 150, 0, 255}, -1); break;
                        default:      // 普通按钮、开关
                            fx = VibrationEffect.createPredefined(VibrationEffect.EFFECT_TICK);
                    }
                    vibrator.vibrate(fx);
                } else if (Build.VERSION.SDK_INT >= 26) {
                    long ms = "tap".equals(kind) || "toggle".equals(kind) ? 8 : "done".equals(kind) ? 40 : 18;
                    vibrator.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE));
                } else {
                    vibrator.vibrate(15);
                }
            } catch (Exception ignored) {
            }
        }
    }
}
