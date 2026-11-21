"""安卓版入口：在手机上启动和电脑版一样的本机服务，界面由 WebView 打开。

由 MainActivity 在后台线程里调用 start()；bridge 是 Java 那边的 PyBridge 对象，
用来做 Python 自己做不了的事：系统朗读、复制、打开网页、把文件存到“下载”文件夹。
"""
import os

_server = None


def start(files_dir, bridge):
    global _server
    if _server is not None:  # 界面重建（比如切到后台很久又回来）时，服务还在，直接复用
        return _server.url
    os.environ["SHICI_DATA"] = os.path.join(files_dir, "data")
    from shici.core import Core
    from shici.server import Server

    core = Core()
    core.android = True
    core.voice_langs = None  # 安卓系统朗读（TextToSpeech）一般都带英语和日语
    core.speaker = lambda text, lang, path: bridge.speak(text, lang, path or "")
    core.url_opener = lambda url: bridge.openUrl(url)
    core.clipboard = lambda text: bridge.copy(text)
    core.file_saver = lambda path: bridge.saveFile(path)
    try:
        core.device_name = str(bridge.deviceName() or "")[:40]  # 局域网同步时电脑上显示的手机名字
    except Exception:
        core.device_name = "安卓手机"
    _server = Server(core)
    _server.start()
    return _server.url
