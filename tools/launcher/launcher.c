/* 「小梦的词书.exe」：双击打开小梦的词书。
 *
 * 做的事和 start.bat 一样，只是不弹黑色命令行窗口，并且带头像图标：
 *   1. 找到能用的 Python 3.10+（PATH 里的 pythonw.exe / pyw.exe，或默认安装位置）；
 *   2. 一个都没有：打开 start.bat，由它在命令行窗口里说明情况、下载安装官方 Python 和依赖；
 *   3. 检查依赖是否已安装，装好了就直接用 pythonw 运行 run.py；
 *   4. 没装好就打开 start.bat，让它在命令行窗口里安装依赖（第一次运行时）。
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

/* 这个 Python 能用吗（3.10 或更新）。Windows 自带的「应用商店占位 python」带参数运行时直接报错退出，也会被排除 */
static int usable(const WCHAR *py, const WCHAR *extra) {
    WCHAR cmd[MAX_PATH * 2 + 160];
    swprintf(cmd, sizeof(cmd) / sizeof(WCHAR), L"\"%ls\"%ls -c \"import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)\"", py, extra);
    return run(cmd, 1, 1) == 0;
}

/* 在默认安装位置（如 %LOCALAPPDATA%\Programs\Python\Python312）里找版本号最高的能用的 pythonw.exe */
static int scan(const WCHAR *base, WCHAR *out) {
    WCHAR root[MAX_PATH], glob[MAX_PATH], cand[MAX_PATH];
    if (!ExpandEnvironmentStringsW(base, root, MAX_PATH)) return 0;
    swprintf(glob, MAX_PATH, L"%ls\\Python3*", root);
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW(glob, &fd);
    if (h == INVALID_HANDLE_VALUE) return 0;
    int best = -1;
    do {
        if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) continue;
        int minor = _wtoi(fd.cFileName + 7);  /* "Python312" -> 12 */
        if (minor <= best) continue;
        swprintf(cand, MAX_PATH, L"%ls\\%ls\\pythonw.exe", root, fd.cFileName);
        if (GetFileAttributesW(cand) != INVALID_FILE_ATTRIBUTES && usable(cand, L"")) {
            best = minor;
            wcscpy(out, cand);
        }
    } while (FindNextFileW(h, &fd));
    FindClose(h);
    return best >= 0;
}

/* 打开 start.bat（带黑色命令行窗口，能看到下载和安装进度） */
static int open_bat(const WCHAR *arg) {  /* arg 目前都是空的，留着以后用 */
    WCHAR bat[MAX_PATH], cmd[MAX_PATH + 64];
    swprintf(bat, MAX_PATH, L"%ls\\start.bat", dir);
    if (GetFileAttributesW(bat) == INVALID_FILE_ATTRIBUTES) return 0;
    swprintf(cmd, sizeof(cmd) / sizeof(WCHAR), L"cmd.exe /c \"\"%ls\" %ls\"", bat, arg);
    run(cmd, 0, 0);
    return 1;
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
    int found = 0;
    if (find(L"pythonw.exe", py) && usable(py, L"")) found = 1;
    else if (find(L"pyw.exe", py) && usable(py, L" -3")) found = launcher = 1;
    else if (scan(L"%LOCALAPPDATA%\\Programs\\Python", py) || scan(L"%ProgramFiles%", py)) found = 1;
    if (!found) {
        /* 没有 Python：直接交给 start.bat，在安装依赖的那个窗口里说明情况、下载安装 Python，不另外弹对话框 */
        if (!open_bat(L"")) msg(L"这台电脑上还没有 Python，也没有找到 start.bat。\n\n请重新下载完整的程序压缩包，解压后再双击「小梦的词书.exe」。");
        return 0;
    }
    const WCHAR *ver = launcher ? L" -3" : L"";

    /* 依赖装好了吗？ */
    swprintf(cmd, sizeof(cmd) / sizeof(WCHAR), L"\"%ls\"%ls -c \"import PySide6, fsrs, openpyxl\"", py, ver);
    if (run(cmd, 1, 1) != 0) {
        /* 第一次运行：交给 start.bat 在命令行窗口里安装依赖，装完它会自己打开程序 */
        if (!open_bat(L"")) {
            msg(L"缺少运行所需的组件，也没有找到 start.bat。\n\n请在这个文件夹里打开命令行，运行：\npip install -r requirements.txt");
            return 1;
        }
        return 0;
    }

    swprintf(cmd, sizeof(cmd) / sizeof(WCHAR), L"\"%ls\"%ls \"%ls\"", py, ver, runpy);
    if (run(cmd, 0, 1) != 0) {
        msg(L"启动失败。可以试试双击 start.bat，看看命令行窗口里的提示。");
        return 1;
    }
    return 0;
}
