# 小梦的词书 · 安卓版

安卓版和电脑版是**同一套代码**：界面是 `shici/web`，背单词、词典、发音都是 `shici/*.py`。
安卓这边只是一个外壳。它用 [Chaquopy](https://chaquo.com/chaquopy/) 在手机上运行 Python，再用 WebView 打开界面。
所以电脑版改了功能，重新打包一次安卓版就同步了。版本号从 `shici/__init__.py` 读取，和电脑版一致。

## 构建

需要 JDK 17、Android SDK（compileSdk 35）、Gradle 8.14 以上，以及一个本机的 Python 3.12（Chaquopy 打包时要用它安装 pip 依赖）。

```bash
cd android
# 本机 Python 3.12 的路径，Windows 上一般是 py -3.12 对应的 python.exe
export CHAQUOPY_BUILD_PYTHON=/usr/bin/python3.12
gradle assembleDebug      # 调试版：app/build/outputs/apk/debug/app-debug.apk
gradle assembleRelease    # 正式版：需要签名，见下
```

也可以直接用 Android Studio 打开 `android` 文件夹。

## 签名

发布 APK 时，每个版本都要用**同一个**签名密钥。换了密钥，手机上就没法覆盖安装，只能卸载重装，学习记录也会跟着丢。
`android/` 下需要放两个文件：

- `ldream-release.jks`：签名密钥
- `keystore.properties`：

  ```
  storeFile=ldream-release.jks
  storePassword=…
  keyAlias=ldream
  keyPassword=…
  ```

这两个文件已经写进 `.gitignore`，**不要传到 GitHub**。

## 说明

- 目前只打包 arm64-v8a（2017 年以后的手机基本都是），最低支持 Android 7.0。
- 学习记录在应用自己的数据目录里，卸载时会被删除。换手机或在电脑和手机之间同步，请用「设置 → 数据 → 进度文件 / 进度密钥」。
- 导出的进度文件、CSV、备份保存在手机的「下载/小梦的词书」文件夹。
- 屏幕宽度 720px 以下使用手机布局（`shici/web/css/phone.css`），平板横屏时和电脑版布局相同。
