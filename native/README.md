# 仅记录官方 libultrahdr 获取与 Windows 桥接构建边界。

使用 Google 官方 `libultrahdr v2.0.2`，固定提交 `e5f5a022fe96fc4dc2ee35c19f733a50df807abe`。
此版本修复静态 libheif 特性检测及链接清理；本项目关闭 HEIF，只输出 JPEG Ultra HDR。

源码：`https://codeload.github.com/google/libultrahdr/zip/e5f5a022fe96fc4dc2ee35c19f733a50df807abe`
SHA-256：`7C2B5F02B463CB9E67AD00F24CC504198FFC384D32B3793781038245FB4B9171`

桥接只支持官方 API-3：HDR RGBA float16 原始图 + 原始压缩 SDR JPEG。它不从 vivo 私有 trailer 生成增益图，也不允许无 sidecar 的像素文件。构建使用 Visual Studio 2022 自带 CMake 和 C++17；依赖在显式指定的临时工具目录，不运行第三方安装程序。

`libjpeg-turbo 3.2.0` 固定使用官方发行源码，SHA-256 为 `6F30092CEF9FB839779646608F4EE14AE3CBAC989C47FA05E841B0841F09878E`。上游禁止 `add_subdirectory` 嵌入，因此用 `ExternalProject` 独立构建；不启用其内部 Git 克隆。所有目标统一 MSVC 静态运行库，C++ 源以 `/utf-8` 编译。

```powershell
$env:HDRVIEW_TOOL_DIR = 'C:\Users\N452\AppData\Local\Temp\opencode\hdrview-build'
pwsh -File scripts/Build-Native.ps1 -Test
```
