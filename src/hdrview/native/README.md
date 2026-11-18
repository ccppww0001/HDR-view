# Windows 原生编码组件

## 构建

在仓库根目录运行以下命令。构建使用 Visual Studio 2022、CMake 和 C++17，C++ 源文件按 UTF-8 编译并链接静态运行库。`-ToolDirectory` 指定下载与解压路径，`-Test` 检查两个编码组件的版本入口。

```powershell
.\src\hdrview\native\Build-Native.ps1 -ToolDirectory (Join-Path (Get-Location) '.tools') -Test
```

| 组件 | 构建用途 | 下载来源和 SHA-256 |
| --- | --- | --- |
| Google libultrahdr 2.0.2 | Ultra HDR JPEG 编码和回读。该上游版本调整了 libheif 静态链接检测，本项目构建使用 JPEG 功能 | [固定源码](https://codeload.github.com/google/libultrahdr/zip/e5f5a022fe96fc4dc2ee35c19f733a50df807abe) · `7C2B5F02B463CB9E67AD00F24CC504198FFC384D32B3793781038245FB4B9171` |
| libjpeg-turbo 3.2.0 | JPEG 编解码。由 CMake 的 `ExternalProject` 在独立构建目录编译 | [发行源码](https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/3.2.0/libjpeg-turbo-3.2.0.tar.gz) · `6F30092CEF9FB839779646608F4EE14AE3CBAC989C47FA05E841B0841F09878E` |

## Ultra HDR JPEG

`hdrview-ultrahdr.exe` 使用 Google libultrahdr 的原始像素编码接口，接收 16 位浮点红绿蓝透明度像素、配套元数据及原始压缩标准动态范围 JPEG。编码器根据两份输入计算增益图。

## 浮点 JPEG XR

`hdrview-jxr.exe` 通过 Windows Imaging Component 的 `GUID_ContainerFormatWmp` 写入 `GUID_WICPixelFormat64bppRGBAHalf`。编码将线性 BT.2020 像素从 203 尼特参考白转换到 Rec.709 scRGB 的 80 尼特参考白。色域转换使用 `REC709_TO_BT2020` 的数值逆矩阵，保持中性白比例。

元数据从顶层固定字段读取，并校验字段唯一性、数值格式和字符串完整性。像素格式校验贯穿编码和回读。输出先写入临时文件，再在编码提交后移动至目标位置。同名冲突会报出目标文件。

本机 16×16 色块测试使用 `ImageQuality=1.0`。组合 `UseCodecOptions=true`、`Lossless=true` 和 `Subsampling=3` 的试验与单独设置图像质量的试验处于同一误差界限。实测最大绝对误差约为 0.000308，高光 `(2,1,0.5)` 回读约为 `(2.000133,1.000146,0.500090)`。回读测试覆盖指定色块，照片显示效果按查看器和设备进行实机对照。[验证记录](../../../docs/verification.md)
