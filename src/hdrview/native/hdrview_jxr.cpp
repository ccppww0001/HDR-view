// Windows WIC JPEG XR 原生 float16 HDR 桥接。
// 输入是线性 BT.2020、1.0=203 nit；JPEG XR 内是线性 Rec.709 scRGB、1.0=80 nit。
// 此程序只验证 WIC 编解码与像素语义，不声称 Windows Photos 的 HDR 显示已经验证。

#define NOMINMAX
#include <windows.h>
#include <wincodec.h>
#include <bcrypt.h>
#include <wrl/client.h>
#include <DirectXPackedVector.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using Microsoft::WRL::ComPtr;
using DirectX::PackedVector::XMConvertFloatToHalf;
using DirectX::PackedVector::XMConvertHalfToFloat;

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

void check(HRESULT result, const char* message) {
    if (FAILED(result)) {
        std::ostringstream text;
        text << message << " (HRESULT=0x" << std::hex << std::uppercase << static_cast<unsigned long>(result) << ")";
        throw std::runtime_error(text.str());
    }
}

class ComSession {
public:
    ComSession() { check(CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED), "COM initialization failed"); }
    ~ComSession() { CoUninitialize(); }
    ComSession(const ComSession&) = delete;
    ComSession& operator=(const ComSession&) = delete;
};

std::vector<uint8_t> read_file(const fs::path& path, uint64_t maximum) {
    std::error_code error;
    const auto length = fs::file_size(path, error);
    require(!error && length > 0 && length <= maximum, "input is missing, empty, or too large");
    std::ifstream stream(path, std::ios::binary);
    require(stream.good(), "cannot open input");
    std::vector<uint8_t> bytes(static_cast<size_t>(length));
    require(stream.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(length)).good(), "input is truncated");
    return bytes;
}

// 仅解析严格 Python sidecar 的有界标量字段；不引入通用 JSON 框架。
size_t json_value(const std::string& json, const std::string& key) {
    const std::string quoted_key = "\"" + key + "\"";
    size_t match = std::string::npos;
    int object_depth = 0;
    int array_depth = 0;
    bool in_string = false;
    bool escaped = false;
    size_t string_start = 0;
    for (size_t at = 0; at <= json.size(); ++at) {
        if (!in_string && at == json.size()) break;
        const char character = at < json.size() ? json[at] : '\0';
        if (in_string) {
            if (escaped) escaped = false;
            else if (character == '\\') escaped = true;
            else if (character == '"') {
                in_string = false;
                if (object_depth >= 1 && json.compare(string_start, quoted_key.size(), quoted_key) == 0) {
                    size_t colon = at + 1;
                    while (colon < json.size() && std::isspace(static_cast<unsigned char>(json[colon]))) ++colon;
                    if (colon < json.size() && json[colon] == ':') {
                        require(object_depth == 1 && array_depth == 0, "sidecar contains a nested reserved field");
                        require(match == std::string::npos, "sidecar contains duplicate top-level field");
                        size_t value = colon + 1;
                        while (value < json.size() && std::isspace(static_cast<unsigned char>(json[value]))) ++value;
                        require(value < json.size(), "sidecar field has no value");
                        match = value;
                    }
                }
            }
            continue;
        }
        require(at < json.size(), "sidecar JSON structure is incomplete");
        if (character == '"') {
            in_string = true;
            escaped = false;
            string_start = at;
        } else if (character == '{') ++object_depth;
        else if (character == '}') {
            --object_depth;
            require(object_depth >= 0, "sidecar has unbalanced objects");
        } else if (character == '[') ++array_depth;
        else if (character == ']') {
            --array_depth;
            require(array_depth >= 0, "sidecar has unbalanced arrays");
        }
    }
    require(object_depth == 0 && array_depth == 0, "sidecar JSON structure is incomplete");
    require(match != std::string::npos, "sidecar is missing a required top-level field");
    return match;
}

void json_delimiter(const std::string& json, size_t at) {
    while (at < json.size() && std::isspace(static_cast<unsigned char>(json[at]))) ++at;
    require(at < json.size() && (json[at] == ',' || json[at] == '}'), "sidecar scalar has an invalid delimiter");
}

void json_literal(const std::string& json, const std::string& key, const std::string& expected) {
    const auto at = json_value(json, key);
    require(json.compare(at, expected.size(), expected) == 0, "sidecar literal does not match the HDR schema");
    // 合法数字后可跟空白，再必须是逗号或对象结束；203junk 等前缀不能被接受。
    size_t end = at + expected.size();
    while (end < json.size() && std::isspace(static_cast<unsigned char>(json[end]))) ++end;
    require(end < json.size() && (json[end] == ',' || json[end] == '}'), "sidecar literal has an invalid delimiter");
}

uint32_t json_uint(const std::string& json, const std::string& key) {
    const auto at = json_value(json, key);
    require(at < json.size() && std::isdigit(static_cast<unsigned char>(json[at])), "sidecar integer is invalid");
    errno = 0;
    char* end = nullptr;
    const auto value = std::strtoull(json.c_str() + at, &end, 10);
    require(errno == 0 && end != json.c_str() + at && value <= UINT32_MAX, "sidecar integer overflow");
    require(end && (std::isspace(static_cast<unsigned char>(*end)) || *end == ',' || *end == '}'), "sidecar integer has trailing characters");
    json_delimiter(json, static_cast<size_t>(end - json.c_str()));
    return static_cast<uint32_t>(value);
}

std::string json_string(const std::string& json, const std::string& key) {
    auto at = json_value(json, key);
    require(at < json.size() && json[at] == '"', "sidecar string is invalid");
    const auto end = json.find('"', ++at);
    require(end != std::string::npos && end - at <= 128, "sidecar string is invalid or too long");
    json_delimiter(json, end + 1);
    return json.substr(at, end - at);
}

float json_float(const std::string& json, const std::string& key) {
    const auto at = json_value(json, key);
    errno = 0;
    char* end = nullptr;
    const auto value = std::strtof(json.c_str() + at, &end);
    require(errno == 0 && end != json.c_str() + at && std::isfinite(value), "sidecar floating-point value is invalid");
    json_delimiter(json, static_cast<size_t>(end - json.c_str()));
    return value;
}

void validate_bt2020_metadata(const std::string& json) {
    constexpr std::array<const char*, 10> required{
        "schema", "width", "height", "channels", "pixel_format", "byte_stride",
        "primaries", "transfer", "sdr_white_nits", "hdr_capacity_max",
    };
    // 一次性拒绝嵌套或重复的保留字段，避免后续读取被 provenance 等同名键劫持。
    for (const auto* key : required) static_cast<void>(json_value(json, key));
    json_literal(json, "schema", "1");
    json_literal(json, "channels", "4");
    require(json_string(json, "pixel_format") == "rgba-float16", "HDR format is not rgba-float16");
    require(json_string(json, "primaries") == "bt2020", "HDR primaries are not BT.2020");
    require(json_string(json, "transfer") == "linear", "HDR transfer is not linear");
    const auto white = json_float(json, "sdr_white_nits");
    require(white == 203.0f, "HDR SDR reference white is not 203 nits");
    require(json_float(json, "hdr_capacity_max") >= 1.0f, "HDR capacity must be at least one");
}

struct Dimensions {
    uint32_t width;
    uint32_t height;
    uint64_t pixels;
    uint64_t bytes;
};

Dimensions dimensions(uint32_t width, uint32_t height) {
    require(width > 0 && height > 0 && width <= 16384 && height <= 16384, "image dimensions exceed the 16384 limit");
    const uint64_t pixels = uint64_t(width) * height;
    require(pixels <= 128ull * 1024 * 1024 && pixels <= std::numeric_limits<size_t>::max() / 8, "image dimensions exceed memory bounds");
    return {width, height, pixels, pixels * 8};
}

std::string sha256(const std::vector<uint8_t>& bytes) {
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    check(BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0), "SHA-256 provider unavailable");
    const auto created = BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0);
    if (created < 0) BCryptCloseAlgorithmProvider(algorithm, 0);
    check(created, "SHA-256 hash unavailable");
    const auto hashed = BCryptHashData(hash, const_cast<PUCHAR>(bytes.data()), static_cast<ULONG>(bytes.size()), 0);
    std::vector<uint8_t> digest(32);
    const auto finished = hashed >= 0 ? BCryptFinishHash(hash, digest.data(), static_cast<ULONG>(digest.size()), 0) : hashed;
    BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(algorithm, 0);
    check(hashed, "SHA-256 data failed");
    check(finished, "SHA-256 finish failed");
    std::ostringstream output;
    output << std::hex << std::setfill('0');
    for (const auto byte : digest) output << std::setw(2) << static_cast<unsigned>(byte);
    return output.str();
}

std::string native_format_name(const GUID& format) {
    if (IsEqualGUID(format, GUID_WICPixelFormat64bppRGBAHalf)) return "GUID_WICPixelFormat64bppRGBAHalf";
    if (IsEqualGUID(format, GUID_WICPixelFormat128bppRGBAFloat)) return "GUID_WICPixelFormat128bppRGBAFloat";
    if (IsEqualGUID(format, GUID_WICPixelFormat128bppRGBFloat)) return "GUID_WICPixelFormat128bppRGBFloat";
    if (IsEqualGUID(format, GUID_WICPixelFormat128bppPRGBAFloat)) return "GUID_WICPixelFormat128bppPRGBAFloat";
    WCHAR value[40]{};
    const auto length = StringFromGUID2(format, value, static_cast<int>(std::size(value)));
    require(length > 0, "cannot format native pixel-format GUID");
    std::wstring wide(value);
    std::string output;
    output.reserve(wide.size());
    std::transform(wide.begin(), wide.end(), std::back_inserter(output), [](wchar_t character) {
        return static_cast<char>(character);
    });
    return output;
}

ComPtr<IWICImagingFactory> create_factory() {
    ComPtr<IWICImagingFactory> factory;
    check(CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&factory)), "WIC factory creation failed");
    return factory;
}

int encode(const fs::path& hdr_path, const fs::path& meta_path, const fs::path& output) {
    require(!fs::exists(output), "JPEG XR output already exists");
    const auto metadata_bytes = read_file(meta_path, 1024 * 1024);
    const std::string metadata(metadata_bytes.begin(), metadata_bytes.end());
    validate_bt2020_metadata(metadata);
    const auto size = dimensions(json_uint(metadata, "width"), json_uint(metadata, "height"));
    require(json_uint(metadata, "byte_stride") == size.width * 8, "sidecar byte stride does not match width");
    const auto input = read_file(hdr_path, size.bytes);
    require(input.size() == size.bytes, "HDR byte count does not match sidecar");

    // 使用 REC709_TO_BT2020 的数值逆矩阵（不是转置）：该色彩矩阵非正交，转置会破坏等能白。
    // BT.2020 到 Rec.709 的矩阵转换可能产生小的 scRGB 负分量，scRGB 允许且必须保留它们。
    constexpr std::array<float, 9> bt2020_to_rec709{
        1.6604909983f, -0.5876411388f, -0.0728498633f,
        -0.1245504765f, 1.1328998971f, -0.0083494224f,
        -0.0181507634f, -0.1005788980f, 1.1187296615f,
    };
    std::vector<uint16_t> scrgb(static_cast<size_t>(size.pixels * 4));
    const auto* half = reinterpret_cast<const uint16_t*>(input.data());
    for (uint64_t pixel = 0; pixel < size.pixels; ++pixel) {
        std::array<float, 4> rgba{};
        for (size_t channel = 0; channel < 4; ++channel) rgba[channel] = XMConvertHalfToFloat(half[pixel * 4 + channel]);
        require(std::all_of(rgba.begin(), rgba.end(), [](float value) { return std::isfinite(value) && value >= 0.0f; }), "HDR pixels must be finite and nonnegative");
        require(rgba[3] == 1.0f, "HDR alpha must equal one");
        for (size_t row = 0; row < 3; ++row) {
            const float value = (bt2020_to_rec709[row * 3] * rgba[0] + bt2020_to_rec709[row * 3 + 1] * rgba[1] + bt2020_to_rec709[row * 3 + 2] * rgba[2]) * (203.0f / 80.0f);
            require(std::isfinite(value) && value >= -65504.0f && value <= 65504.0f, "converted scRGB pixel is outside float16 bounds");
            scrgb[pixel * 4 + row] = XMConvertFloatToHalf(value);
        }
        scrgb[pixel * 4 + 3] = XMConvertFloatToHalf(1.0f);
    }

    const fs::path temporary = output.wstring() + L".tmp";
    require(!fs::exists(temporary), "temporary JPEG XR output already exists");
    try {
        ComSession com;
        auto factory = create_factory();
        {
            ComPtr<IWICStream> stream;
            check(factory->CreateStream(&stream), "WIC output stream creation failed");
            check(stream->InitializeFromFilename(temporary.c_str(), GENERIC_WRITE), "WIC cannot open temporary JPEG XR output");
            ComPtr<IWICBitmapEncoder> encoder;
            check(factory->CreateEncoder(GUID_ContainerFormatWmp, nullptr, &encoder), "Windows WIC JPEG XR encoder is unavailable");
            check(encoder->Initialize(stream.Get(), WICBitmapEncoderNoCache), "JPEG XR encoder initialization failed");
            ComPtr<IWICBitmapFrameEncode> frame;
            ComPtr<IPropertyBag2> properties;
            check(encoder->CreateNewFrame(&frame, &properties), "JPEG XR frame creation failed");
            // 先只设置 ImageQuality=1.0，用于实测 codec options 对 float16 的实际作用。
            PROPBAG2 option{};
            option.pstrName = const_cast<LPOLESTR>(L"ImageQuality");
            VARIANT value;
            VariantInit(&value);
            value.vt = VT_R4;
            value.fltVal = 1.0f;
            check(properties->Write(1, &option, &value), "cannot set JPEG XR ImageQuality=1.0");
            VariantClear(&value);
            check(frame->Initialize(properties.Get()), "JPEG XR frame initialization with high ImageQuality failed");
            check(frame->SetSize(size.width, size.height), "JPEG XR SetSize failed");
            WICPixelFormatGUID format = GUID_WICPixelFormat64bppRGBAHalf;
            check(frame->SetPixelFormat(&format), "WIC refused native float16 JPEG XR encoding");
            require(IsEqualGUID(format, GUID_WICPixelFormat64bppRGBAHalf), "WIC silently downgraded the JPEG XR pixel format: " + native_format_name(format));
            const UINT stride = size.width * 8;
            require(size.bytes <= UINT_MAX, "single-frame WIC buffer exceeds UINT_MAX");
            check(frame->WritePixels(size.height, stride, static_cast<UINT>(size.bytes), reinterpret_cast<BYTE*>(scrgb.data())), "JPEG XR full-resolution WritePixels failed");
            check(frame->Commit(), "JPEG XR frame commit failed");
            check(encoder->Commit(), "JPEG XR encoder commit failed");
        } // 先关闭 WIC 流，再移动完整文件，避免未提交或仍被占用的输出。
        factory.Reset();
        require(!fs::exists(output), "JPEG XR output appeared during encoding");
        fs::rename(temporary, output);
    } catch (...) {
        std::error_code ignored;
        fs::remove(temporary, ignored);
        throw;
    }
    return 0;
}

int decode(const fs::path& input_path, const fs::path& raw, const fs::path& metadata) {
    require(!fs::exists(raw) && !fs::exists(metadata), "decode output already exists");
    const auto bytes = read_file(input_path, 512ull * 1024 * 1024);
    const auto digest = sha256(bytes);
    const fs::path raw_temporary = raw.wstring() + L".tmp";
    const fs::path meta_temporary = metadata.wstring() + L".tmp";
    require(!fs::exists(raw_temporary) && !fs::exists(meta_temporary), "temporary decode output already exists");

    Dimensions size{};
    float content_max = 0.0f;
    try {
        ComSession com;
        auto factory = create_factory();
        ComPtr<IWICBitmapDecoder> decoder;
        check(factory->CreateDecoderFromFilename(input_path.c_str(), nullptr, GENERIC_READ, WICDecodeMetadataCacheOnDemand, &decoder), "WIC cannot decode JPEG XR input");
        ComPtr<IWICBitmapFrameDecode> frame;
        check(decoder->GetFrame(0, &frame), "JPEG XR has no decodable first frame");
        WICPixelFormatGUID format = GUID_WICPixelFormatUndefined;
        check(frame->GetPixelFormat(&format), "cannot query native JPEG XR pixel format");
        // 只有 64bpp RGBA half 是本桥接的允许格式；整数与宽浮点都不静默转换。
        require(IsEqualGUID(format, GUID_WICPixelFormat64bppRGBAHalf), "JPEG XR native pixel format is not GUID_WICPixelFormat64bppRGBAHalf: " + native_format_name(format));
        UINT width = 0, height = 0;
        check(frame->GetSize(&width, &height), "cannot query JPEG XR dimensions");
        size = dimensions(width, height);
        require(size.bytes <= UINT_MAX, "single-frame WIC buffer exceeds UINT_MAX");
        std::vector<uint16_t> pixels(static_cast<size_t>(size.bytes / 2));
        check(frame->CopyPixels(nullptr, width * 8, static_cast<UINT>(size.bytes), reinterpret_cast<BYTE*>(pixels.data())), "native float16 JPEG XR CopyPixels failed");
        // scRGB 允许由宽色域转换产生的负分量；这里保留它们，避免错误钳制改变颜色。
        for (uint64_t pixel = 0; pixel < size.pixels; ++pixel) {
            for (size_t channel = 0; channel < 4; ++channel) {
                const float value = XMConvertHalfToFloat(pixels[pixel * 4 + channel]);
                require(std::isfinite(value) && (channel < 3 || value >= 0.0f), "decoded scRGB pixels must be finite with nonnegative alpha");
                if (channel < 3) content_max = std::max(content_max, value);
            }
            require(XMConvertHalfToFloat(pixels[pixel * 4 + 3]) == 1.0f, "decoded JPEG XR alpha must equal one");
        }
        {
            std::ofstream stream(raw_temporary, std::ios::binary | std::ios::trunc);
            require(stream.good(), "cannot create temporary decoded raw output");
            stream.write(reinterpret_cast<const char*>(pixels.data()), static_cast<std::streamsize>(size.bytes));
            stream.close();
            require(stream.good(), "cannot write complete decoded raw output");
        }
        {
            std::ofstream json(meta_temporary, std::ios::trunc);
            require(json.good(), "cannot create temporary decoded metadata");
            json << "{\n"
                 << "  \"schema\": 1,\n"
                 << "  \"width\": " << size.width << ",\n"
                 << "  \"height\": " << size.height << ",\n"
                 << "  \"channels\": 4,\n"
                 << "  \"pixel_format\": \"rgba-float16\",\n"
                 << "  \"byte_stride\": " << size.width * 8 << ",\n"
                 << "  \"primaries\": \"rec709\",\n"
                 << "  \"transfer\": \"linear\",\n"
                 << "  \"sdr_white_nits\": 80.0,\n"
                 << "  \"hdr_capacity_max\": 1.0,\n"
                 << "  \"native_float\": true,\n"
                 << "  \"native_pixel_format\": \"GUID_WICPixelFormat64bppRGBAHalf\",\n"
                 << "  \"native_content_max\": " << std::setprecision(9) << content_max << ",\n"
                 << "  \"windows_photos_hdr_verified\": false,\n"
                 << "  \"provenance\": {\"source_sha256\": \"" << digest << "\", \"pipeline\": \"wic-jxr-reference-decode\"}\n"
                 << "}\n";
            json.close();
            require(json.good(), "cannot write complete decoded metadata");
        }
        factory.Reset();
        fs::rename(raw_temporary, raw);
        try {
            fs::rename(meta_temporary, metadata);
        } catch (...) {
            std::error_code ignored;
            fs::remove(raw, ignored); // 本次刚创建的 raw 可回滚，避免只留半个解码结果。
            throw;
        }
    } catch (...) {
        std::error_code ignored;
        fs::remove(raw_temporary, ignored);
        fs::remove(meta_temporary, ignored);
        throw;
    }
    return 0;
}

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::strcmp(argv[1], "--version") == 0) {
            std::cout << "hdrview-jxr bridge; Windows WIC JPEG XR native float16\n";
            return 0;
        }
        if (argc == 8 && std::strcmp(argv[1], "encode") == 0 && std::strcmp(argv[2], "--hdr") == 0 &&
            std::strcmp(argv[4], "--meta") == 0 && std::strcmp(argv[6], "--output") == 0) {
            return encode(argv[3], argv[5], argv[7]);
        }
        if (argc == 8 && std::strcmp(argv[1], "decode") == 0 && std::strcmp(argv[2], "--input") == 0 &&
            std::strcmp(argv[4], "--raw") == 0 && std::strcmp(argv[6], "--meta") == 0) {
            return decode(argv[3], argv[5], argv[7]);
        }
        std::cerr << "usage: hdrview-jxr encode --hdr raw.f16rgba --meta input.json --output new.jxr; "
                     "hdrview-jxr decode --input input.jxr --raw new.f16rgba --meta new.json\n";
        return 2;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
