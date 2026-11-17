// HDR 中间文件与官方 libultrahdr API-3 之间的最小桥接。
// 增益计算、容器与色彩语义交由官方实现；这里不解析 vivo 私有高光公式。

#include <ultrahdr_api.h>

#include <cstdint>
#include <cstring>
#include <iomanip>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <sstream>
#include <string>
#include <vector>
#include <windows.h>
#include <bcrypt.h>
#pragma comment(lib, "bcrypt.lib")

namespace fs = std::filesystem;
using Decoder = std::unique_ptr<uhdr_codec_private_t, decltype(&uhdr_release_decoder)>;
using Encoder = std::unique_ptr<uhdr_codec_private_t, decltype(&uhdr_release_encoder)>;

std::vector<uint8_t> read_file(const fs::path& path) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream) throw std::runtime_error("cannot open input");
    const auto length = stream.tellg();
    if (length <= 0 || length > 512ll * 1024 * 1024) throw std::runtime_error("input is empty or too large");
    std::vector<uint8_t> bytes(static_cast<size_t>(length));
    stream.seekg(0);
    if (!stream.read(reinterpret_cast<char*>(bytes.data()), length)) throw std::runtime_error("input is truncated");
    return bytes;
}

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

// sidecar 只由我们的严格 Python 写入器生成；C++ 端仍校验关键固定字段和尺寸。
uint32_t json_uint(const std::string& json, const std::string& key) {
    const auto at = json.find("\"" + key + "\":");
    require(at != std::string::npos, "sidecar missing integer");
    const auto value = std::stoull(json.substr(at + key.size() + 3));
    require(value <= UINT32_MAX, "sidecar integer overflow");
    return static_cast<uint32_t>(value);
}

void check(uhdr_error_info_t result) {
    if (result.error_code != UHDR_CODEC_OK) {
        throw std::runtime_error(result.has_detail ? result.detail : "libultrahdr codec error");
    }
}

std::string sha256(const std::vector<uint8_t>& bytes) {
    // 使用 Windows 原生密码学接口，避免十六进制字节误当 SHA-256。
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    require(BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) >= 0, "SHA-256 provider unavailable");
    require(BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) >= 0, "SHA-256 hash unavailable");
    std::vector<uint8_t> digest(32);
    const auto status = BCryptHashData(hash, const_cast<PUCHAR>(bytes.data()), static_cast<ULONG>(bytes.size()), 0);
    if (status >= 0) require(BCryptFinishHash(hash, digest.data(), digest.size(), 0) >= 0, "SHA-256 finish failed");
    BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(algorithm, 0);
    require(status >= 0, "SHA-256 data failed");
    std::ostringstream output;
    output << std::hex << std::setfill('0');
    for (const auto byte : digest) output << std::setw(2) << static_cast<unsigned>(byte);
    return output.str();
}

int encode(const fs::path& hdr_path, const fs::path& meta_path, const fs::path& sdr_path, const fs::path& output) {
    require(!fs::exists(output), "output already exists");
    const auto meta_bytes = read_file(meta_path);
    const std::string meta(meta_bytes.begin(), meta_bytes.end());
    require(meta.find("\"pixel_format\": \"rgba-float16\"") != std::string::npos, "HDR format is not rgba-float16");
    require(meta.find("\"primaries\": \"bt2020\"") != std::string::npos, "HDR primaries are not BT.2020");
    require(meta.find("\"transfer\": \"linear\"") != std::string::npos, "HDR transfer is not linear");
    const auto width = json_uint(meta, "width");
    const auto height = json_uint(meta, "height");
    require(width > 0 && height > 0 && uint64_t(width) * height <= 128ull * 1024 * 1024, "invalid HDR dimensions");
    const auto hdr_bytes = read_file(hdr_path);
    const auto sdr_bytes = read_file(sdr_path);
    require(hdr_bytes.size() == uint64_t(width) * height * 8, "HDR byte count does not match sidecar");
    require(sdr_bytes.size() > 4 && sdr_bytes[0] == 0xff && sdr_bytes[1] == 0xd8, "SDR input is not JPEG");

    Encoder encoder(uhdr_create_encoder(), &uhdr_release_encoder);
    require(encoder != nullptr, "cannot allocate encoder");
    uhdr_raw_image_t hdr{};
    hdr.fmt = UHDR_IMG_FMT_64bppRGBAHalfFloat;
    hdr.cg = UHDR_CG_BT_2100;
    hdr.ct = UHDR_CT_LINEAR;
    hdr.range = UHDR_CR_FULL_RANGE;
    hdr.w = width;
    hdr.h = height;
    hdr.planes[0] = const_cast<uint8_t*>(hdr_bytes.data());
    hdr.stride[0] = width;
    uhdr_compressed_image_t sdr{};
    sdr.data = const_cast<uint8_t*>(sdr_bytes.data());
    sdr.data_sz = sdr.capacity = sdr_bytes.size();
    sdr.cg = UHDR_CG_BT_709;
    sdr.ct = UHDR_CT_SRGB;
    sdr.range = UHDR_CR_FULL_RANGE;
    check(uhdr_enc_set_raw_image(encoder.get(), &hdr, UHDR_HDR_IMG));
    check(uhdr_enc_set_compressed_image(encoder.get(), &sdr, UHDR_SDR_IMG));
    check(uhdr_enc_set_quality(encoder.get(), 95, UHDR_BASE_IMG));
    check(uhdr_enc_set_quality(encoder.get(), 95, UHDR_GAIN_MAP_IMG));
    check(uhdr_enc_set_gainmap_scale_factor(encoder.get(), 1));
    check(uhdr_enc_set_using_multi_channel_gainmap(encoder.get(), 1));
    check(uhdr_encode(encoder.get()));
    auto* encoded = uhdr_get_encoded_stream(encoder.get());
    require(encoded && encoded->data && encoded->data_sz > 0, "encoder returned no JPEG");

    const auto temporary = output.wstring() + L".tmp";

    require(!fs::exists(temporary), "temporary output already exists");
    try {
        std::ofstream stream(temporary, std::ios::binary);
        stream.write(static_cast<const char*>(encoded->data), encoded->data_sz);
        stream.close();
        require(stream.good(), "cannot write encoded output");
        fs::rename(temporary, output);
    } catch (...) {
        std::error_code ignored;
        fs::remove(temporary, ignored);
        throw;
    }
    return 0;
}

int inspect(const fs::path& input, const fs::path& report) {
    const auto bytes = read_file(input);
    Decoder decoder(uhdr_create_decoder(), &uhdr_release_decoder);
    require(decoder != nullptr, "cannot allocate decoder");
    uhdr_compressed_image_t image{};
    image.data = const_cast<uint8_t*>(bytes.data());
    image.data_sz = image.capacity = bytes.size();
    image.cg = UHDR_CG_UNSPECIFIED;
    image.ct = UHDR_CT_UNSPECIFIED;
    image.range = UHDR_CR_UNSPECIFIED;
    check(uhdr_dec_set_image(decoder.get(), &image));
    check(uhdr_dec_probe(decoder.get()));
    const auto* metadata = uhdr_dec_get_gainmap_metadata(decoder.get());
    auto* base = uhdr_dec_get_base_image(decoder.get());
    auto* gain = uhdr_dec_get_gainmap_image(decoder.get());
    require(base && gain && metadata, "Ultra HDR probe lacks base/gain/metadata");
    std::ofstream json(report);
    require(json.good(), "cannot open inspect report");
    json << "{\n"
         << "  \"is_ultrahdr\": " << (is_uhdr_image(image.data, static_cast<int>(image.data_sz)) ? "true" : "false") << ",\n"
         << "  \"width\": " << uhdr_dec_get_image_width(decoder.get()) << ",\n"
         << "  \"height\": " << uhdr_dec_get_image_height(decoder.get()) << ",\n"
         << "  \"gainmap_width\": " << uhdr_dec_get_gainmap_width(decoder.get()) << ",\n"
         << "  \"gainmap_height\": " << uhdr_dec_get_gainmap_height(decoder.get()) << ",\n"
         << "  \"hdr_capacity_min\": " << (metadata ? metadata->hdr_capacity_min : 0) << ",\n"
         << "  \"hdr_capacity_max\": " << (metadata ? metadata->hdr_capacity_max : 0) << "\n}\n";
    const fs::path base_path = report.wstring() + L".base.jpg";
    const fs::path gain_path = report.wstring() + L".gain.jpg";
    std::ofstream(base_path, std::ios::binary).write(static_cast<const char*>(base->data), base->data_sz);
    std::ofstream(gain_path, std::ios::binary).write(static_cast<const char*>(gain->data), gain->data_sz);
    return 0;
}

int decode(const fs::path& input, const fs::path& raw, const fs::path& metadata, float display_boost) {
    require(display_boost >= 1.0f, "display boost must be >= 1");
    const auto bytes = read_file(input);
    Decoder decoder(uhdr_create_decoder(), &uhdr_release_decoder);
    require(decoder != nullptr, "cannot allocate decoder");
    uhdr_compressed_image_t image{};
    image.data = const_cast<uint8_t*>(bytes.data());
    image.data_sz = image.capacity = bytes.size();
    image.cg = UHDR_CG_UNSPECIFIED;
    image.ct = UHDR_CT_UNSPECIFIED;
    image.range = UHDR_CR_UNSPECIFIED;
    check(uhdr_dec_set_image(decoder.get(), &image));
    check(uhdr_dec_set_out_img_format(decoder.get(), UHDR_IMG_FMT_64bppRGBAHalfFloat));
    check(uhdr_dec_set_out_color_transfer(decoder.get(), UHDR_CT_LINEAR));
    check(uhdr_dec_set_out_max_display_boost(decoder.get(), display_boost));
    check(uhdr_dec_probe(decoder.get()));
    check(uhdr_decode(decoder.get()));
    auto* decoded = uhdr_get_decoded_image(decoder.get());
    require(decoded && decoded->planes[0], "decode returned no pixels");
    const size_t length = uint64_t(decoded->w) * decoded->h * 8;
    std::ofstream(raw, std::ios::binary).write(static_cast<const char*>(decoded->planes[0]), length);
    std::ofstream json(metadata);
    json << "{\"schema\":1,\"width\":" << decoded->w << ",\"height\":" << decoded->h
         << ",\"channels\":4,\"pixel_format\":\"rgba-float16\",\"byte_stride\":" << decoded->w * 8
         << ",\"primaries\":\"bt2020\",\"transfer\":\"linear\",\"sdr_white_nits\":203.0,"
         << "\"hdr_capacity_max\":" << display_boost
         << ",\"provenance\":{\"source_sha256\":\"" << sha256(bytes)
         << "\",\"pipeline\":\"libultrahdr-reference-decode\"}}\n";
    return 0;
}

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::strcmp(argv[1], "--version") == 0) {
            std::cout << "hdrview-ultrahdr bridge; libultrahdr " << UHDR_LIB_VERSION << '\n';
            return 0;
        }
        if (argc == 10 && std::strcmp(argv[1], "encode") == 0 && std::strcmp(argv[2], "--hdr") == 0 &&
            std::strcmp(argv[4], "--meta") == 0 && std::strcmp(argv[6], "--sdr") == 0 && std::strcmp(argv[8], "--output") == 0) {
            return encode(argv[3], argv[5], argv[7], argv[9]);
        }
        if (argc == 6 && std::strcmp(argv[1], "inspect") == 0 && std::strcmp(argv[2], "--input") == 0 && std::strcmp(argv[4], "--json") == 0) {
            return inspect(argv[3], argv[5]);
        }
        if (argc == 10 && std::strcmp(argv[1], "decode") == 0 && std::strcmp(argv[2], "--input") == 0 &&
            std::strcmp(argv[4], "--raw") == 0 && std::strcmp(argv[6], "--meta") == 0 && std::strcmp(argv[8], "--boost") == 0) {
            return decode(argv[3], argv[5], argv[7], std::stof(argv[9]));
        }
        std::cerr << "usage: encode --hdr raw --meta json --sdr original.jpg --output new.jpg; inspect --input file --json report";
        return 2;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
