/* 「小梦的词书.exe」：双击打开小梦的词书。
 *
 * 做的事和 start.bat 一样，只是不弹黑色命令行窗口，并且带头像图标：
 *   1. 找到 pythonw.exe（或 Python 启动器 pyw.exe）；
 *   2. 检查依赖是否已安装，装好了就直接用 pythonw 运行 run.py；
 *   3. 没装好就打开 start.bat，让它在命令行窗口里安装依赖（第一次运行时）。
 *
 * 编译（在任何系统上都可以交叉编译出 Windows 程序）：
 *   pip install ziglang
 *   python tools/launcher/build.py
 */
#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>

static WCHAR dir[MAX_PATH];

static void msg(const WCHAR *text) {
    MessageBoxW(NULL, text, L"小梦的词书", MB_OK | MB_ICONINFORMATION);
}

/* 在 PATH 里找可执行文件，找到返回 1 */
static int find(const WCHAR *name, WCHAR *out) {
    return SearchPathW(NULL, name, NULL, MAX_PATH, out, NULL) > 0;
}

/* 运行一条命令，不显示窗口；wait 为真时等它结束并返回退出码 */
static DWORD run(WCHAR *cmd, int wait, int hidden) {
    STARTUPINFOW si = {0};
    PROCESS_INFORMATION pi = {0};
    si.cb = sizeof(si);
    DWORD code = 1;
    DWORD flags = hidden ? CREATE_NO_WINDOW : CREATE_NEW_CONSOLE;
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, flags, NULL, dir, &si, &pi)) return 9999;
    if (wait) {
        WaitForSingleObject(pi.hProcess, 120000);
        GetExitCodeProcess(pi.hProcess, &code);
    } else {
        code = 0;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return code;
}

int WINAPI WinMain(HINSTANCE h, HINSTANCE p, LPSTR args, int show) {  /* 参数用不到，所有路径都用宽字符 API 处理 */
    (void)h; (void)p; (void)args; (void)show;
    WCHAR exe[MAX_PATH], py[MAX_PATH], cmd[MAX_PATH * 3 + 64], runpy[MAX_PATH];
    GetModuleFileNameW(NULL, exe, MAX_PATH);
    wcscpy(dir, exe);
    WCHAR *slash = wcsrchr(dir, L'\\');
    if (slash) *slash = 0;

    swprintf(runpy, MAX_PATH, L"%ls\\run.py", dir);
    if (GetFileAttributesW(runpy) == INVALID_FILE_ATTRIBUTES) {
        msg(L"没有找到 run.py。\n\n请把「小梦的词书.exe」和程序的其他文件放在同一个文件夹里，不要单独移动它。\n（想放到桌面的话，右键 → 发送到 → 桌面快捷方式。）");
        return 1;
    }

    int launcher = 0;  /* 1 = 用的是 pyw.exe（Python 启动器） */
    if (!find(L"pythonw.exe", py)) {
        if (find(L"pyw.exe", py)) launcher = 1;
        else {
            if (MessageBoxW(NULL, L"没有找到 Python。\n\n小梦的词书需要 Python 3.10 或更新版本。安装时请勾选 “Add python.exe to PATH”。\n\n现在打开 Python 下载页面吗？",
                            L"小梦的词书", MB_YESNO | MB_ICONQUESTION) == IDYES)
                ShellExecuteW(NULL, L"open", L"https://www.python.org/downloads/", NULL, NULL, SW_SHOWNORMAL);
            return 1;
        }
    }
    const WCHAR *ver = launcher ? L" -3" : L"";

    /* 依赖装好了吗？ */
    swprintf(cmd, sizeof(cmd) / sizeof(WCHAR), L"\"%ls\"%ls -c \"import PySide6, fsrs, openpyxl\"", py, ver);
    if (run(cmd, 1, 1) != 0) {
        /* 第一次运行：交给 start.bat 在命令行窗口里安装依赖，装完它会自己打开程序 */
        WCHAR bat[MAX_PATH];
        swprintf(bat, MAX_PATH, L"%ls\\start.bat", dir);
        if (GetFileAttributesW(bat) == INVALID_FILE_ATTRIBUTES) {
            msg(L"缺少运行所需的组件，也没有找到 start.bat。\n\n请在这个文件夹里打开命令行，运行：\npip install -r requirements.txt");
            return 1;
        }
        swprintf(cmd, sizeof(cmd) / sizeof(WCHAR), L"cmd.exe /c \"\"%ls\"\"", bat);
        run(cmd, 0, 0);
        return 0;
    }

    swprintf(cmd, sizeof(cmd) / sizeof(WCHAR), L"\"%ls\"%ls \"%ls\"", py, ver, runpy);
    if (run(cmd, 0, 1) != 0) {
        msg(L"启动失败。可以试试双击 start.bat，看看命令行窗口里的提示。");
        return 1;
    }
    return 0;
}
