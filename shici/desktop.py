"""桌面外壳：一个 PySide6 窗口，里面用 Qt WebEngine 显示界面；发音也在这里出声。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QLocale, QObject, QProcess, QSettings, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QIcon
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

from . import APP_ID, APP_NAME, DATA_DIR_NAME
from .core import Core
from .paths import resource_dir
from .server import Server


class Voice(QObject):
    """出声的地方：播放音频文件（内置语音包、在线发音的缓存），或者用系统语音朗读。

    后台线程通过信号把请求交给主线程，Qt 的播放器和语音只能在主线程用。
    """

    request = Signal(str, str, str)   # 文本, 语言(en/ja), 音频文件路径(为空则用系统语音)
    open_path = Signal(str)
    open_url = Signal(str)
    copy_text = Signal(str)
    restart = Signal()
    look = Signal(bool, bool)         # 是否暗色, 是否简约白

    def __init__(self, core: Core):
        super().__init__()
        self.core = core
        self.tts = None
        self.player = None
        self.audio_out = None
        self._pending = ("", "en")
        self.request.connect(self._speak)
        self.open_path.connect(lambda p: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
        self.open_url.connect(lambda u: QDesktopServices.openUrl(QUrl(u)))
        self.copy_text.connect(lambda t: QGuiApplication.clipboard().setText(t))

    def _ensure_tts(self):
        if self.tts is None:
            from PySide6.QtTextToSpeech import QTextToSpeech

            self.tts = QTextToSpeech(self)
            self.tts.setRate(-0.15)
        return self.tts

    def probe(self) -> None:
        """看看系统里装了哪些语言的语音，界面据此提示“没有日语语音”之类的情况。"""
        try:
            langs = {loc.language() for loc in self._ensure_tts().availableLocales()}
            self.core.voice_langs = {code for code, lang in (("en", QLocale.Language.English), ("ja", QLocale.Language.Japanese)) if lang in langs}
        except Exception:  # 语音模块不可用时不影响其他功能
            self.core.voice_langs = set()

    def _say(self, text: str, lang: str) -> None:
        try:
            tts = self._ensure_tts()
            want = QLocale.Language.Japanese if lang == "ja" else QLocale.Language.English
            locales = [loc for loc in tts.availableLocales() if loc.language() == want]
            if not locales:
                return
            prefer = self.core.settings.get("accent", "us")
            territory = QLocale.Country.UnitedKingdom if prefer == "uk" else QLocale.Country.UnitedStates
            best = next((loc for loc in locales if loc.territory() == territory), locales[0])
            if tts.locale() != best:
                tts.setLocale(best)
            # 语速：Qt 的 rate 是 -1（最慢）~ 1（最快），0 是正常；默认稍慢一点（-0.15）
            r = float(self.core.settings.get("voice_rate", 1.0))
            tts.setRate(max(-1.0, min(1.0, -0.15 + (r - 1) * 1.6)))
            tts.stop()
            tts.say(text)
        except Exception as e:
            print("朗读失败:", e, file=sys.stderr)

    @Slot(str, str, str)
    def _speak(self, text: str, lang: str, path: str) -> None:
        if not path:
            return self._say(text, lang)
        try:
            if self.player is None:
                from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

                self.audio_out = QAudioOutput(self)
                self.player = QMediaPlayer(self)
                self.player.setAudioOutput(self.audio_out)
                # 音频文件播不出来（解码器缺失等）就退回系统语音
                self.player.errorOccurred.connect(lambda *_: self._say(*self._pending))
            self._pending = (text, lang)
            self.player.stop()
            self.player.setSource(QUrl.fromLocalFile(path))
            self.player.setPlaybackRate(float(self.core.settings.get("voice_rate", 1.0)))
            self.player.play()
        except Exception:
            self._say(text, lang)


def apply_render(mode: str) -> None:
    """选择画面渲染方式。必须在创建 QApplication 之前设置。

    Windows 上 Qt WebEngine 默认走 D3D11，部分显卡 / 驱动下鼠标在界面上移动时，整个窗口偶尔会空白闪一两帧
    （Qt 已知问题 QTBUG-123181）。换成 OpenGL，或者让网页用软件渲染，通常就不会了。
    """
    if mode == "opengl":
        os.environ["QSG_RHI_BACKEND"] = "opengl"
        os.environ["QT_WIDGETS_RHI_BACKEND"] = "opengl"


GPU_KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"


def gpu_targets() -> list[str]:
    """要指定显卡的程序：Python 本身（Qt 在这里合成画面）和 QtWebEngineProcess.exe（网页在这里渲染）。"""
    out = []
    exe = Path(sys.executable)
    out += [str(exe.parent / n) for n in ("python.exe", "pythonw.exe")] if not getattr(sys, "frozen", False) else [str(exe)]
    try:
        from PySide6.QtCore import QLibraryInfo
        out.append(str(Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.LibraryExecutablesPath)) / "QtWebEngineProcess.exe"))
    except Exception:
        pass
    return [p for p in dict.fromkeys(out) if Path(p).exists()]


def apply_gpu(pref: str, store: QSettings) -> None:
    """双显卡电脑上选用哪张显卡：和 Windows「设置 → 显示 → 图形」里给程序选显卡是同一个设置（写在当前用户的注册表里）。

    选「自动」时把我们改过的值恢复成原样（原来没有就删掉），不动用户自己在系统设置里给别的程序选的显卡。
    另外给网页引擎加上 Chromium 的对应开关。
    """
    flag = {"high": "--force_high_performance_gpu", "low": "--force_low_power_gpu"}.get(pref)
    if flag:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " " + flag).strip()
    if sys.platform != "win32":
        return
    try:
        import winreg

        backup = json.loads(store.value("gpu_backup") or "{}")  # 路径 -> 改之前的值（None = 原来没有）
        value = {"high": "GpuPreference=2;", "low": "GpuPreference=1;"}.get(pref)
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, GPU_KEY, 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
            if value:
                for path in gpu_targets():
                    if path not in backup:
                        try:
                            backup[path] = winreg.QueryValueEx(k, path)[0]
                        except OSError:
                            backup[path] = None
                    winreg.SetValueEx(k, path, 0, winreg.REG_SZ, value)
            else:
                for path, old in backup.items():
                    try:
                        if old is None:
                            winreg.DeleteValue(k, path)
                        else:
                            winreg.SetValueEx(k, path, 0, winreg.REG_SZ, old)
                    except OSError:
                        pass
                backup = {}
        store.setValue("gpu_backup", json.dumps(backup))
    except Exception as e:  # 改不了注册表也不影响使用
        print("设置显卡偏好失败:", e, file=sys.stderr)


def restart_command() -> tuple[str, list[str], str]:
    """重新启动自己用的命令：(程序, 参数, 工作目录)"""
    if getattr(sys, "frozen", False):  # PyInstaller 打包的 exe
        return sys.executable, sys.argv[1:], str(Path(sys.executable).parent)
    root = Path(__file__).resolve().parent.parent
    return sys.executable, ["-m", "shici", *sys.argv[1:]], str(root)


def run(core: Core, server: Server) -> int:
    # 画面设置（渲染方式 + 显卡）。三道保险，保证不会因为这两个设置打不开程序：
    #   1. 每次启动先记下“正在用某个配置启动”，界面真正画出来后由网页报告一声才划掉；
    #      下次启动发现上次没划掉（闪退、卡死、白屏被关掉），说明这个配置在这台电脑上不行，自动换回默认；
    #   2. 用户手动改过的配置，第一次启动要确认画面正常（像 Windows 改分辨率那样），15 秒不确认自动换回；
    #   3. 「自动」在 N 卡 / A 卡上用 OpenGL（闪屏少），其他显卡用 D3D11；OpenGL 在这台电脑上出过问题就不再用。
    store = QSettings(DATA_DIR_NAME, APP_ID)

    def effective() -> tuple[str, str, str]:
        render, gpu = core.settings.get("render", "auto"), core.settings.get("gpu", "auto")
        if render == "auto":
            seen = str(store.value("gpu_seen") or "").lower()
            good = sys.platform == "win32" and store.value("gl_bad") != "1" and any(v in seen for v in ("nvidia", "amd", "radeon"))
            backend = "opengl" if good else "d3d11"
        else:
            backend = render
        return render, gpu, f"{backend}|{gpu}"

    render, gpu, eff = effective()
    failed = store.value("display_pending") == eff
    unconfirmed = store.value("render_trial") == eff
    if failed or unconfirmed:
        if render == "auto" and eff.startswith("opengl"):
            store.setValue("gl_bad", "1")
        core.api_settings_set({"render": "auto", "gpu": "auto"})
        core.display_reverted = True
        render, gpu, eff = effective()
    store.remove("render_trial")
    explicit = render != "auto" or gpu != "auto"
    if explicit and store.value("display_confirmed") != eff:
        store.setValue("render_trial", eff)
        core.render_trial = True
    store.setValue("display_pending", eff)
    apply_render(eff.split("|")[0])
    if core.settings.get("lcd_text"):
        # 清晰文字：Qt 的网页引擎默认只用灰度抗锯齿画字，在 100% 缩放的普通屏幕上小字容易发虚、有锯齿；
        # 打开后用 ClearType 那样的彩色（次像素）抗锯齿
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " --enable-lcd-text").strip()
    apply_gpu(gpu, store)
    store.sync()

    def confirm():
        store.remove("render_trial")
        store.setValue("display_confirmed", eff)
        store.sync()

    def display_ok(renderer: str):
        store.remove("display_pending")
        if renderer:
            store.setValue("gpu_seen", renderer)
        store.sync()

    core.render_confirm = confirm
    core.display_ok = display_ok

    if sys.platform == "win32":  # 让任务栏显示我们自己的图标，而不是 Python 的
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LDream.Wordbook")
        except Exception:
            pass
    app = QApplication(sys.argv[:1])
    app.setApplicationName(DATA_DIR_NAME)
    app.setOrganizationName(DATA_DIR_NAME)
    app.setApplicationDisplayName(APP_NAME)
    # Windows 用带多种尺寸的 .ico，标题栏和任务栏的小图标更清楚
    icon = QIcon(str(resource_dir() / "web" / "img" / ("icon.ico" if sys.platform == "win32" else "icon.png")))
    app.setWindowIcon(icon)

    voice = Voice(core)
    core.voice_langs = None
    try:  # 系统字体列表，给设置里的字体选择用；竖排字体（名字以 @ 开头）不要
        from PySide6.QtGui import QFontDatabase
        core.system_fonts = sorted({f for f in QFontDatabase.families() if not f.startswith("@")}, key=str.casefold)
    except Exception:
        core.system_fonts = []
    core.speaker = lambda text, lang, path: voice.request.emit(text, lang, path or "")
    core.opener = voice.open_path.emit
    core.url_opener = voice.open_url.emit
    core.clipboard = voice.copy_text.emit

    view = QWebEngineView()
    view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
    view.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)  # 按键音效不需要先点一下
    dark = core.settings.get("theme") == "dark"
    silver = core.settings.get("palette") == "silver"

    def backdrop(dark: bool, silver: bool):  # 网页还没画出来的地方露出的底色：和当前主题一致，加载、换主题、拉大窗口时都不闪白
        view.page().setBackgroundColor(QColor(("#0B0B0D" if silver else "#121214") if dark else ("#F5F5F7" if silver else "#F6F5F2")))

    backdrop(dark, silver)
    voice.look.connect(backdrop)
    core.look_changed = voice.look.emit
    win = QMainWindow()
    win.setWindowTitle(APP_NAME)
    win.setWindowIcon(icon)
    win.setCentralWidget(view)
    win.setMinimumSize(980, 660)
    geo = store.value("geometry")
    if not (geo and win.restoreGeometry(geo)):
        win.resize(1360, 860)
    # 界面里“导出进度文件”等下载：内置浏览器默认会忽略下载，这里弹出“另存为”窗口让你选位置
    def on_download(req):
        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog

        name = req.downloadFileName() or "download"
        start = Path.home() / "Desktop"
        start = start if start.is_dir() else Path.home()
        flt = "小梦的词书进度文件 (*.xmdb)" if name.endswith(".xmdb") else "所有文件 (*)"
        path, _ = QFileDialog.getSaveFileName(win, "保存", str(start / name), flt)
        if not path:
            req.cancel()
            return
        req.setDownloadDirectory(str(Path(path).parent))
        req.setDownloadFileName(Path(path).name)

        def done():
            if req.isFinished():
                ok = req.state() == req.DownloadState.DownloadCompleted
                msg = f"已保存到 {path}" if ok else "保存失败，请换个位置再试"
                view.page().runJavaScript(f"document.dispatchEvent(new CustomEvent('shici-toast', {{detail: {json.dumps(msg)}}}))")

        req.isFinishedChanged.connect(done)
        req.accept()

    view.page().profile().downloadRequested.connect(on_download)
    def restart():
        store.setValue("geometry", win.saveGeometry())
        store.sync()
        prog, args, cwd = restart_command()
        QProcess.startDetached(prog, args, cwd)
        app.quit()

    voice.restart.connect(restart)
    core.restarter = voice.restart.emit
    view.load(QUrl(server.url))
    win.show()
    view.setFocus()  # 让键盘快捷键一打开就能用，不用先点一下窗口
    QTimer.singleShot(1200, voice.probe)

    code = app.exec()
    store.setValue("geometry", win.saveGeometry())
    return code
