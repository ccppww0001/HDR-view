param(
    [switch]$Test,
    [string]$ToolDirectory = $env:HDRVIEW_TOOL_DIR
)
$ErrorActionPreference = 'Stop'
# 让命令行调用者以 UTF-8 读取中文构建与错误信息，不依赖系统区域设置。
$OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = $OutputEncoding
if (!$ToolDirectory) { throw '请通过 HDRVIEW_TOOL_DIR 或 -ToolDirectory 指定临时/忽略的构建工具目录' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).Path
# native/ 是唯一构建入口；构建产物继续留在已被忽略的 native/build。
$build = Join-Path $PSScriptRoot 'build'
New-Item -ItemType Directory -Path $ToolDirectory, $build -Force | Out-Null

# 固定官方源码；压缩包 SHA-256 独立于源码内容执行前校验。
$version = '2.0.2'
$revision = 'e5f5a022fe96fc4dc2ee35c19f733a50df807abe'
$expected = '7C2B5F02B463CB9E67AD00F24CC504198FFC384D32B3793781038245FB4B9171'
$archive = Join-Path $ToolDirectory 'libultrahdr-v2.0.2.zip'
if (!(Test-Path -LiteralPath $archive)) {
    curl.exe -L --fail --silent --show-error --output $archive "https://codeload.github.com/google/libultrahdr/zip/$revision"
    if ($LASTEXITCODE -ne 0) { throw '官方 libultrahdr 源码下载失败' }
}
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expected) { throw 'libultrahdr 源码 SHA-256 不匹配' }
$source = Join-Path $ToolDirectory "libultrahdr-$revision"
if (!(Test-Path -LiteralPath $source)) {
    Expand-Archive -LiteralPath $archive -DestinationPath $ToolDirectory -Force
}
# libultrahdr 内部克隆不可靠且缺少直接哈希门禁，显式准备固定 JPEG 源码。
$jpegRevision = '3.2.0'
$jpegExpected = '6F30092CEF9FB839779646608F4EE14AE3CBAC989C47FA05E841B0841F09878E'
$jpegArchive = Join-Path $ToolDirectory 'libjpeg-turbo-3.2.0.tar.gz'
if (!(Test-Path -LiteralPath $jpegArchive)) {
    curl.exe -L --fail --silent --show-error --output $jpegArchive 'https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/3.2.0/libjpeg-turbo-3.2.0.tar.gz'
    if ($LASTEXITCODE -ne 0) { throw 'libjpeg-turbo 官方源码下载失败' }
}
if ((Get-FileHash -LiteralPath $jpegArchive -Algorithm SHA256).Hash -ne $jpegExpected) { throw 'libjpeg-turbo 源码 SHA-256 不匹配' }
$jpegSource = Join-Path $ToolDirectory 'libjpeg-turbo-3.2.0'
if (!(Test-Path -LiteralPath $jpegSource)) { tar.exe -xzf $jpegArchive -C $ToolDirectory }
$cmake = Join-Path $env:ProgramFiles 'Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
if (!(Test-Path -LiteralPath $cmake)) { $cmake = (Get-Command cmake -ErrorAction Stop).Source }
& $cmake -S $PSScriptRoot -B $build -A x64 "-DUHDR_SOURCE_DIR=$source" "-DJPEG_SOURCE_DIR=$jpegSource" '-DUHDR_BUILD_DEPS=OFF' '-DUHDR_ENABLE_HEIF=OFF' '-DUHDR_BUILD_EXAMPLES=OFF' '-DUHDR_BUILD_TESTS=OFF' '-DBUILD_SHARED_LIBS=OFF'
if ($LASTEXITCODE -ne 0) { throw 'CMake 配置失败' }
& $cmake --build $build --config Release
if ($LASTEXITCODE -ne 0) { throw '本地 Ultra HDR 桥接构建失败' }
if ($Test) {
    $executable = Join-Path $build 'Release/hdrview-ultrahdr.exe'
    if (!(Test-Path -LiteralPath $executable)) { throw '构建产物不存在' }
    & $executable --version
    if ($LASTEXITCODE -ne 0) { throw '桥接版本检查失败' }
    $jxrExecutable = Join-Path $build 'Release/hdrview-jxr.exe'
    if (!(Test-Path -LiteralPath $jxrExecutable)) { throw 'JPEG XR 桥接构建产物不存在' }
    & $jxrExecutable --version
    if ($LASTEXITCODE -ne 0) { throw 'JPEG XR 桥接版本检查失败' }
}
Write-Host "桥接位置：$build/Release/hdrview-ultrahdr.exe"
Write-Host "JPEG XR 桥接位置：$build/Release/hdrview-jxr.exe"
