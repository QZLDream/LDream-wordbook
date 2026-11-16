"""桌面外壳：一个 PySide6 窗口，里面用 Qt WebEngine 显示界面；发音也在这里出声。"""
from __future__ import annotations

import json
import sys

from PySide6.QtCore import QLocale, QObject, QSettings, QTimer, QUrl, Qt, Signal, Slot
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
    copy_text = Signal(str)

    def __init__(self, core: Core):
        super().__init__()
        self.core = core
        self.tts = None
        self.player = None
        self.audio_out = None
        self._pending = ("", "en")
        self.request.connect(self._speak)
        self.open_path.connect(lambda p: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
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
            self.player.play()
        except Exception:
            self._say(text, lang)


def run(core: Core, server: Server) -> int:
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
    core.clipboard = voice.copy_text.emit

    view = QWebEngineView()
    view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
    view.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)  # 按键音效不需要先点一下
    dark = core.settings.get("theme") == "dark"
    silver = core.settings.get("palette") == "silver"
    view.page().setBackgroundColor(QColor(("#0B0B0D" if silver else "#121214") if dark else ("#F5F5F7" if silver else "#F6F5F2")))  # 加载时不闪白
    win = QMainWindow()
    win.setWindowTitle(APP_NAME)
    win.setWindowIcon(icon)
    win.setCentralWidget(view)
    win.setMinimumSize(980, 660)
    store = QSettings(DATA_DIR_NAME, APP_ID)
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
    view.load(QUrl(server.url))
    win.show()
    view.setFocus()  # 让键盘快捷键一打开就能用，不用先点一下窗口
    QTimer.singleShot(1200, voice.probe)

    code = app.exec()
    store.setValue("geometry", win.saveGeometry())
    return code
