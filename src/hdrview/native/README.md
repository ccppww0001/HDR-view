# 仅记录官方 libultrahdr 获取与 Windows 桥接构建边界。

使用 Google 官方 `libultrahdr v2.0.2`，固定提交 `e5f5a022fe96fc4dc2ee35c19f733a50df807abe`。
此版本修复静态 libheif 特性检测及链接清理；本项目关闭 HEIF，只输出 JPEG Ultra HDR。

源码：`https://codeload.github.com/google/libultrahdr/zip/e5f5a022fe96fc4dc2ee35c19f733a50df807abe`
SHA-256：`7C2B5F02B463CB9E67AD00F24CC504198FFC384D32B3793781038245FB4B9171`

桥接只支持官方 API-3：HDR RGBA float16 原始图 + 原始压缩 SDR JPEG。它不从 vivo 私有 trailer 生成增益图，也不允许无 sidecar 的像素文件。构建使用 Visual Studio 2022 自带 CMake 和 C++17；依赖在显式指定的临时工具目录，不运行第三方安装程序。

`libjpeg-turbo 3.2.0` 固定使用官方发行源码，SHA-256 为 `6F30092CEF9FB839779646608F4EE14AE3CBAC989C47FA05E841B0841F09878E`。上游禁止 `add_subdirectory` 嵌入，因此用 `ExternalProject` 独立构建；不启用其内部 Git 克隆。所有目标统一 MSVC 静态运行库，C++ 源以 `/utf-8` 编译。

```powershell
$env:HDRVIEW_TOOL_DIR = 'C:\Users\N452\AppData\Local\Temp\opencode\hdrview-build'
pwsh -File src/hdrview/native/Build-Native.ps1 -Test
```

同一构建入口还生成 `hdrview-jxr.exe`。它通过 Windows WIC 的 `GUID_ContainerFormatWmp` 编码 `GUID_WICPixelFormat64bppRGBAHalf`：共享 BT.2020 线性光（参考白 203 nit）先以 `REC709_TO_BT2020` 的**数值逆矩阵**转为 Rec.709 scRGB（参考白 80 nit），再全分辨率写入。该色彩矩阵并非正交矩阵，不能用转置代替逆矩阵，否则中性白也会偏色。原生解码只接受该 float16 格式，若系统拒绝或更改像素格式会明确失败，不会静默降为整数。sidecar 只从顶层读取固定字段，拒绝重复/嵌套保留字段和不完整的数值、字符串标量 token。JPEG XR 输出先写临时文件，关闭并提交 WIC 后移动，且不覆盖已有文件。

实测 Windows WIC 接受 `UseCodecOptions=true`、`Lossless=true`、`Subsampling=3` 属性，但对本机 float16 色块回读没有可测改善；仅 `ImageQuality=1.0` 与增加三个选项的结果都满足相同的严格误差界限。因此最终实现不保留这三个无效选项，也不据此声称 float16 JPEG XR 无损。16×16 固定色块实测最大绝对误差约为 0.000308；高光 `(2,1,0.5)` 回读约 `(2.000133,1.000146,0.500090)`。复杂纹理仍可能有 JPEG XR 有损误差，测试只对明确色块作严格数值保证。

WIC 编解码与像素回读只证明格式及 HDR 数值保留；**Windows Photos 的 HDR 显示未验证**。
