#!/usr/bin/env python3
"""编译并烧录 Mercury 固件。必须在 ESP-IDF v6.1 的终端里运行：

    python firmware/build_firmware.py                  编译并烧录到 COM11
    python firmware/build_firmware.py --phase star     换一套形态（mercury / glass / warm / frost / star / rainbow）
    python firmware/build_firmware.py --wake xiaozhi   唤醒词退回"你好小智"
    python firmware/build_firmware.py --no-flash       只编译不烧录
    python firmware/build_firmware.py --orientation portrait-180   竖屏画面是倒的时候用
    python firmware/build_firmware.py --orientation landscape      回到原来的横屏

基于开源固件 xiaozhi-esp32 v2.6.0，板型：立创·实战派 ESP32-S3。
脚本做这几件事：
  1. 克隆固件源码到 firmware/xiaozhi-esp32，打几处小补丁（见 SOURCE_PATCHES）
  2. 把 firmware/board（Mercury 自己的板型代码：竖屏、电量显示）复制成 main/boards/mercury，
     并按 --orientation / --battery-* 参数生成 mercury_options.h
  3. 让立创实战派板型改用 boards/mercury 和 character/out/<形态>/png 里的表情（字库、语音模型保持原样）
  4. 生成配置片段：板型、中文、唤醒词、服务器 OTA 地址（从 server/.env 读取）
  5. idf.py reconfigure / build / flash
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FW_DIR = ROOT / "firmware" / "xiaozhi-esp32"
GEN_DIR = ROOT / "firmware" / "generated"
FW_REPO = "https://github.com/78/xiaozhi-esp32.git"
FW_TAG = "v2.6.0"
BOARD_MARK = "CONFIG_BOARD_TYPE_LICHUANG_DEV_S3)"
BOARD_NAME = "lichuang-dev"
PHASES = ["mercury", "glass", "warm", "frost", "star", "rainbow"]


def die(msg):
    print(f"\n错误：{msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd, cwd=None):
    cmd = [str(c) for c in cmd]
    print("\n> " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def ota_url():
    """从 server/.env 拼出设备要访问的 OTA 地址（含网关密钥路径）。"""
    env_file = ROOT / "server" / ".env"
    if not env_file.exists():
        die(f"没找到 {env_file}，固件需要从里面读取服务器地址。")
    vals = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
        if m:
            vals[m.group(1)] = m.group(2).strip()
    missing = [k for k in ("PUBLIC_HOST", "SECRET_PATH") if not vals.get(k)]
    if missing:
        die(f"server/.env 里还没有 {', '.join(missing)}。")
    port = vals.get("GATEWAY_PORT") or "18080"
    return f"http://{vals['PUBLIC_HOST']}:{port}/{vals['SECRET_PATH']}/xiaozhi/ota/"


def ensure_source():
    if (FW_DIR / "main" / "CMakeLists.txt").exists():
        return
    run(["git", "clone", "--depth", "1", "--branch", FW_TAG, FW_REPO, FW_DIR])


# 对固件源码的小改动：(文件, 原文, 改后)。每条都要求原文恰好出现一次，对不上就报错而不是悄悄跳过。
SOURCE_PATCHES = [
    # 这块板子 8MB 的外部内存被图片缓存（预留 3.5MB）和自定义唤醒词模型占满，
    # 拍照时连 150KB 的编码缓冲都申请不到（Failed to allocate memory for encode buffer）。
    # 字库和表情图是直接从闪存映射的，图片缓存只存解码后的表情（160px 每张约 100KB），
    # 缩到 768KB（约 7 张）足够，腾出约 1.5MB。
    (
        "main/display/lcd_display.cc",
        "const size_t extra_total = 2560 * 1024;",
        "const size_t extra_total = 1024 * 1024;  // Mercury: was 2560KB, leave PSRAM for the camera",
    ),
    (
        "main/display/lcd_display.cc",
        'lv_image_cache_resize(2 * 1024 * 1024, true);\n        ESP_LOGI(TAG, "Use 2MB of PSRAM for image cache");',
        'lv_image_cache_resize(768 * 1024, true);  // Mercury: was 2MB\n        ESP_LOGI(TAG, "Use 768KB of PSRAM for image cache");',
    ),
    # 定期日志里加上外部内存的余量和最大连续块，方便判断内存够不够
    (
        "main/system_info.cc",
        'ESP_LOGI(TAG, "free sram: %u minimal sram: %u", free_sram, min_free_sram);',
        'ESP_LOGI(TAG, "free sram: %u minimal sram: %u", free_sram, min_free_sram);\n'
        '    ESP_LOGI(TAG, "free psram: %u largest block: %u minimal psram: %u",  // Mercury\n'
        "             (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),\n"
        "             (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM),\n"
        "             (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_SPIRAM));",
    ),
    # 摄像头画面旋转：板子竖着放时摄像头也转了 90°，在拷贝帧数据时顺手转回来。
    # 预览和上传都用转过的尺寸。旋转角度由板型代码调用 SetRotation() 设置。
    (
        "main/boards/common/esp32_camera.h",
        "    size_t encode_buf_size_ = 0;\n",
        "    size_t encode_buf_size_ = 0;\n"
        "    int rotation_ = 0;      // Mercury: clockwise rotation applied to RGB565 frames\n"
        "    uint16_t frame_w_ = 0;  // Mercury: size of the (rotated) image in encode_buf_\n"
        "    uint16_t frame_h_ = 0;\n",
    ),
    (
        "main/boards/common/esp32_camera.h",
        "    virtual bool SetSwapBytes(bool enabled) override;\n",
        "    virtual bool SetSwapBytes(bool enabled) override;\n"
        "    void SetRotation(int degrees_cw) { rotation_ = ((degrees_cw % 360) + 360) % 360; }  // Mercury\n",
    ),
    (
        "main/boards/common/esp32_camera.cc",
        "        uint16_t* dst = (uint16_t*)encode_buf_;\n"
        "        if (swap_bytes_enabled_) {\n",
        "        uint16_t* dst = (uint16_t*)encode_buf_;\n"
        "        // Mercury: optionally rotate while copying (board mounted in portrait)\n"
        "        const int sw = current_fb_->width;\n"
        "        const int sh = current_fb_->height;\n"
        "        const bool quarter_turn = rotation_ == 90 || rotation_ == 270;\n"
        "        frame_w_ = quarter_turn ? sh : sw;\n"
        "        frame_h_ = quarter_turn ? sw : sh;\n"
        "        if (rotation_ == 90 || rotation_ == 180 || rotation_ == 270) {\n"
        "            const bool swap = swap_bytes_enabled_;\n"
        "            for (int y = 0; y < sh; y++) {\n"
        "                const uint16_t* row = src + (size_t)y * sw;\n"
        "                for (int x = 0; x < sw; x++) {\n"
        "                    const uint16_t p = swap ? __builtin_bswap16(row[x]) : row[x];\n"
        "                    size_t di;\n"
        "                    if (rotation_ == 90) {\n"
        "                        di = (size_t)x * sh + (sh - 1 - y);\n"
        "                    } else if (rotation_ == 180) {\n"
        "                        di = (size_t)(sh - 1 - y) * sw + (sw - 1 - x);\n"
        "                    } else {\n"
        "                        di = (size_t)(sw - 1 - x) * sh + y;\n"
        "                    }\n"
        "                    dst[di] = p;\n"
        "                }\n"
        "            }\n"
        "        } else if (swap_bytes_enabled_) {\n",
    ),
    (
        "main/boards/common/esp32_camera.cc",
        "                    preview_data, data_size, current_fb_->width, current_fb_->height,\n"
        "                    current_fb_->width * 2, LV_COLOR_FORMAT_RGB565));",
        "                    preview_data, data_size, frame_w_, frame_h_,\n"
        "                    frame_w_ * 2, LV_COLOR_FORMAT_RGB565));  // Mercury: rotated size",
    ),
    (
        "main/boards/common/esp32_camera.cc",
        "    const uint16_t w = current_fb_->width;\n"
        "    const uint16_t h = current_fb_->height;\n",
        "    // Mercury: RGB565 frames were copied (possibly rotated) into encode_buf_\n"
        "    const bool from_encode_buf = current_fb_->format == PIXFORMAT_RGB565 && encode_buf_ != nullptr;\n"
        "    const uint16_t w = from_encode_buf ? frame_w_ : current_fb_->width;\n"
        "    const uint16_t h = from_encode_buf ? frame_h_ : current_fb_->height;\n",
    ),
    (
        "main/boards/common/esp32_camera.cc",
        "             current_fb_->width, current_fb_->height, (int)jpeg_size, (int)remain_stack_size,",
        "             w, h, (int)jpeg_size, (int)remain_stack_size,  // Mercury: rotated size",
    ),
    # 按住屏幕开始对话时也"叮"一声：借用唤醒词那条路的提示音标志。
    # 提示音必须等进入聆听、解码器重置之后再放，否则会被清掉，所以不能在按住时直接放。
    (
        "main/application.h",
        "    void StopListening();\n",
        "    void StopListening();\n"
        "    // Mercury: play the popup sound when the next listening session starts (touch to talk)\n"
        "    void PlayPopupOnNextListening() { play_popup_on_listening_ = true; }\n",
    ),
]

# 屏幕方向 -> mercury_options.h 里的取值（含义见 firmware/board/config.h）
ORIENTATIONS = {
    "portrait": "MERCURY_ORIENTATION_PORTRAIT",
    "portrait-180": "MERCURY_ORIENTATION_PORTRAIT_180",
    "landscape": "MERCURY_ORIENTATION_LANDSCAPE",
}
BOARD_SRC = ROOT / "firmware" / "board"
BOARD_SUBDIR = "mercury"  # 复制到 main/boards/mercury/
SOUNDS_DIR = ROOT / "firmware" / "sounds"  # 触摸时的短音效（make_sounds.py 生成），打包成 mercury_sounds.h
GENERATED_BOARD_FILES = {"mercury_options.h", "mercury_sounds.h", "mercury_growth_art.h"}
# 养成的配饰图（character/gen-faces.mjs 生成），只有 mercury 形态有
GROWTH_ART_DIR = ROOT / "character" / "out" / "mercury" / "growth"
GROWTH_ART_STUB = """// 由 firmware/build_firmware.py 生成：当前形态没有养成配饰
#pragma once

#include <cstdint>

namespace mercury_art {

constexpr int kFaceSize = 0;

struct Accessory {
    const char* id;
    const char* slot;
    int16_t x, y;
    uint16_t w, h;
    const uint8_t* argb8888;
};

static const Accessory kAccessories[] = {{nullptr, nullptr, 0, 0, 0, 0, nullptr}};

}  // namespace mercury_art
"""


def apply_source_patches():
    for rel, old, new in SOURCE_PATCHES:
        path = FW_DIR / rel
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        eol = "\r\n" if "\r\n" in text else "\n"
        old_n, new_n = old.replace("\n", eol), new.replace("\n", eol)
        if new_n in text:
            continue  # 已经打过
        if text.count(old_n) != 1:
            die(f"固件源码和预期不一样，补丁打不上：{rel}\n  找不到（或不止一处）：{old.splitlines()[0]}")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text.replace(old_n, new_n))
        print(f"已打补丁：{rel}")


def write_if_changed(path, data):
    """内容没变就不写，免得改动时间戳触发不必要的重新编译。"""
    if path.exists() and path.read_bytes() == data:
        return False
    path.write_bytes(data)
    return True


def install_board(args):
    """把 firmware/board 复制成固件里的 main/boards/mercury，并按参数生成 mercury_options.h。"""
    dest = FW_DIR / "main" / "boards" / BOARD_SUBDIR
    dest.mkdir(parents=True, exist_ok=True)
    names = set()
    for src in sorted(BOARD_SRC.iterdir()):
        if src.is_file():
            names.add(src.name)
            write_if_changed(dest / src.name, src.read_bytes())
    for old in dest.iterdir():  # 源目录里删掉的文件，这边也删掉
        if old.is_file() and old.name not in names and old.name not in GENERATED_BOARD_FILES:
            old.unlink()
    write_sounds_header(dest / "mercury_sounds.h")

    # 养成：配饰图要和表情图一样大（竖屏 224px、横屏 160px）
    growth_art = args.phase == "mercury"
    if growth_art:
        size = 160 if args.orientation == "landscape" else 224
        art = GROWTH_ART_DIR / f"growth_art_{size}.h"
        if not art.exists():
            die(f"没找到养成配饰图：{art}\n  先在 character 目录运行：npm run build")
        write_if_changed(dest / "mercury_growth_art.h", art.read_bytes())
    else:
        write_if_changed(dest / "mercury_growth_art.h", GROWTH_ART_STUB.encode("utf-8"))

    if args.battery_gpio == "none":
        battery_gpio = -1
    else:
        try:
            battery_gpio = int(args.battery_gpio)
        except ValueError:
            die(f"--battery-gpio 要填 GPIO 编号或 none，收到的是：{args.battery_gpio}")
    lines = [
        "// 由 firmware/build_firmware.py 生成，不要手改",
        "#pragma once",
        f"#define MERCURY_ORIENTATION {ORIENTATIONS[args.orientation]}",
    ]
    if args.camera_rotate != "auto":
        lines.append(f"#define MERCURY_CAMERA_ROTATION {int(args.camera_rotate)}")
    lines += [
        f"#define MERCURY_BATTERY_ADC_GPIO {battery_gpio}",
        f"#define MERCURY_BATTERY_DIVIDER {args.battery_divider:.4f}f",
        f"#define MERCURY_GROWTH_ART {1 if growth_art else 0}",
    ]
    write_if_changed(dest / "mercury_options.h", ("\n".join(lines) + "\n").encode("utf-8"))


def write_sounds_header(path):
    """把 firmware/sounds/*.ogg 做成 C 数组，固件里用 mercury_sounds::Get("名字") 取。

    没有音效文件时也生成（空表），固件照常编译，只是触摸时不出声。
    """
    lines = [
        "// 由 firmware/build_firmware.py 从 firmware/sounds/*.ogg 生成，不要手改",
        "#pragma once",
        "",
        "#include <cstring>",
        "#include <string_view>",
        "",
        "namespace mercury_sounds {",
    ]
    clips = sorted(SOUNDS_DIR.glob("*.ogg")) if SOUNDS_DIR.exists() else []
    for i, clip in enumerate(clips):
        data = clip.read_bytes()
        body = ",".join(str(b) for b in data)
        lines.append(f"static const unsigned char kData{i}[] = {{{body}}};  // {clip.name}")
    lines += ["", "struct Clip {", "    const char* name;", "    const unsigned char* data;", "    size_t size;", "};", ""]
    entries = [f'    {{"{c.stem}", kData{i}, sizeof(kData{i})}},' for i, c in enumerate(clips)]
    lines += ["static const Clip kClips[] = {"] + entries + ['    {nullptr, nullptr, 0},', "};", ""]
    lines += [
        "// 找不到时返回空的 string_view",
        "inline std::string_view Get(const char* name) {",
        "    for (const Clip* c = kClips; c->name != nullptr; ++c) {",
        "        if (std::strcmp(c->name, name) == 0) {",
        "            return std::string_view(reinterpret_cast<const char*>(c->data), c->size);",
        "        }",
        "    }",
        "    return {};",
        "}",
        "",
        "}  // namespace mercury_sounds",
        "",
    ]
    if write_if_changed(path, "\n".join(lines).encode("utf-8")):
        print(f"已打包 {len(clips)} 个触摸音效：{', '.join(c.stem for c in clips) or '（无）'}")


def point_board_at(emoji_dir):
    """改 main/CMakeLists.txt 里立创实战派那一段：板型代码用 boards/mercury，表情集用我们的目录。

    固件打包脚本用 os.path.join(字体组件目录, 'png', 表情集名) 找图片，
    传绝对路径时 join 的结果就是这个绝对路径，所以只需要改这一行。
    """
    cm = FW_DIR / "main" / "CMakeLists.txt"
    with open(cm, encoding="utf-8", newline="") as f:
        original = f.read()
    lines = original.splitlines(keepends=True)
    wanted = {
        "set(BOARD_DIR": f'set(BOARD_DIR "{BOARD_SUBDIR}")',
        "set(DEFAULT_EMOJI_COLLECTION": f'set(DEFAULT_EMOJI_COLLECTION "{emoji_dir.as_posix()}")',
    }
    found = set()
    in_block = False
    for i, line in enumerate(lines):
        if BOARD_MARK in line:
            in_block = True
            continue
        if not in_block:
            continue
        if line.startswith(("elseif", "else", "endif")):
            break
        for key, value in wanted.items():
            if line.strip().startswith(key):
                indent = line[: len(line) - len(line.lstrip())]
                eol = "\r\n" if line.endswith("\r\n") else "\n"
                lines[i] = f"{indent}{value}{eol}"
                found.add(key)
    missing = [k for k in wanted if k not in found]
    if missing:
        die(f"在 main/CMakeLists.txt 的立创实战派一段里没找到 {', '.join(missing)}，固件版本可能变了。")
    updated = "".join(lines)
    if updated != original:
        with open(cm, "w", encoding="utf-8", newline="") as f:
            f.write(updated)


def write_sdkconfig(args, url):
    if args.wake == "custom":
        # MultiNet 中文模型只认拼音，英文 Mercury 用近似音节代替；识别不灵时调 --wake-pinyin / --wake-threshold
        wake = [
            "CONFIG_USE_CUSTOM_WAKE_WORD=y",
            f'CONFIG_CUSTOM_WAKE_WORD="{args.wake_pinyin}"',
            'CONFIG_CUSTOM_WAKE_WORD_DISPLAY="你好Mercury"',
            f"CONFIG_CUSTOM_WAKE_WORD_THRESHOLD={args.wake_threshold}",
            "CONFIG_SR_MN_CN_MULTINET6_QUANT=y",
        ]
    else:
        wake = ["CONFIG_USE_AFE_WAKE_WORD=y", "CONFIG_SR_WN_WN9_NIHAOXIAOZHI_TTS=y"]
    base = (ROOT / "firmware" / "mercury.sdkconfig.defaults").read_text(encoding="utf-8")
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    out = GEN_DIR / "sdkconfig.mercury"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(base.rstrip("\n") + "\n\n" + "\n".join(wake) + f'\nCONFIG_OTA_URL="{url}"\n')
    switches = [l for l in base.splitlines() + wake if l.endswith("=y")]
    return out, switches


def check_applied(switches):
    """sdkconfig.defaults 里写错的符号会被静默忽略，这里确认开关真的生效了。"""
    applied = (FW_DIR / "sdkconfig").read_text(encoding="utf-8", errors="replace").splitlines()
    missing = [s for s in switches if s not in applied]
    if missing:
        die("这些配置没有生效（多半是该固件版本里符号改了名）：\n  " + "\n  ".join(missing))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="COM11", help="板子的串口，默认 COM11")
    ap.add_argument("--phase", default="mercury", choices=PHASES, help="表情形态，默认 mercury")
    ap.add_argument("--wake", default="custom", choices=["custom", "xiaozhi"], help="custom=你好Mercury，xiaozhi=你好小智")
    ap.add_argument("--wake-pinyin", default="ni hao mo ke rui", help="自定义唤醒词的拼音，空格分隔")
    ap.add_argument("--wake-threshold", type=int, default=20, help="1~99，越小越灵敏（也越容易误唤醒）")
    ap.add_argument("--orientation", default="portrait", choices=list(ORIENTATIONS),
                    help="屏幕方向，默认 portrait（竖屏：从原来横屏的位置顺时针转 90° 摆放）；"
                         "画面倒了就用 portrait-180；landscape 是原来的横屏")
    ap.add_argument("--camera-rotate", default="auto", choices=["auto", "0", "90", "180", "270"],
                    help="摄像头画面顺时针旋转角度，默认 auto（跟着屏幕方向走）")
    ap.add_argument("--battery-gpio", default="10",
                    help="电池分压接到哪个 GPIO（只能用 ADC1 的 GPIO1~10），默认 10；none 关闭电量显示")
    ap.add_argument("--battery-divider", type=float, default=2.0,
                    help="电池电压 / 引脚电压，默认 2.0（两只 100kΩ 分压）")
    ap.add_argument("--no-flash", action="store_true", help="只编译不烧录")
    ap.add_argument("--flash-only", action="store_true", help="不重新编译，直接把上次编译的结果烧录到板子")
    ap.add_argument("--clean", action="store_true", help="即使配置没变也从头重新配置")
    args = ap.parse_args()

    idf_path = os.environ.get("IDF_PATH")
    if not idf_path or not (Path(idf_path) / "tools" / "idf.py").exists():
        die("没有检测到 ESP-IDF 环境（IDF_PATH）。请用 firmware\\idf-env.cmd 来运行本脚本。")
    idf = [sys.executable, Path(idf_path) / "tools" / "idf.py"]

    if args.flash_only:
        if not (FW_DIR / "build" / "xiaozhi.bin").exists():
            die("还没有编译结果，先不带 --flash-only 运行一次。")
        run(idf + ["-p", args.port, "flash"], cwd=FW_DIR)
        print("\n烧录完成。")
        return

    # 竖屏用大一号的表情图（224px），横屏用原来的 160px
    emoji_set = "png" if args.orientation == "landscape" else "png-portrait"
    emoji_dir = ROOT / "character" / "out" / args.phase / emoji_set
    count = len(list(emoji_dir.glob("*.png"))) if emoji_dir.exists() else 0
    if count != 21 or not (emoji_dir / "neutral.png").exists():
        die(f"没找到 21 张表情图：{emoji_dir}\n  先在 character 目录运行：npm install 然后 npm run build")

    url = ota_url()
    ensure_source()
    apply_source_patches()
    install_board(args)
    point_board_at(emoji_dir)
    previous = (GEN_DIR / "sdkconfig.mercury").read_text(encoding="utf-8") if (GEN_DIR / "sdkconfig.mercury").exists() else None
    fragment, switches = write_sdkconfig(args, url)

    # 删掉旧的资源包，强制用当前表情重新打包（只要几秒）
    assets = FW_DIR / "build" / "generated_assets.bin"
    if assets.exists():
        assets.unlink()

    # 配置没变、上次的编译结果还在时，跳过重新配置，只增量编译改过的文件（几分钟 → 几十秒）
    unchanged = (
        not args.clean
        and previous == fragment.read_text(encoding="utf-8")
        and (FW_DIR / "sdkconfig").exists()
        and (FW_DIR / "build" / "build.ninja").exists()
    )
    if unchanged:
        print("\n配置没有变化，跳过重新配置，做增量编译。")
    else:
        # 和官方 scripts/build.py 相同的配置方式：从"官方默认 + 我们的片段"重新生成 sdkconfig。
        # BOARD_NAME 是设备上报给服务器的板型名，沿用官方发布版的 lichuang-dev。
        if (FW_DIR / "sdkconfig").exists():
            (FW_DIR / "sdkconfig").unlink()
        run(
            idf
            + [
                "-DIDF_TARGET=esp32s3",
                f"-DSDKCONFIG_DEFAULTS=sdkconfig.defaults;{fragment.as_posix()}",
                f"-DBOARD_NAME={BOARD_NAME}",
                "reconfigure",
            ],
            cwd=FW_DIR,
        )
    check_applied(switches)
    run(idf + ["build"], cwd=FW_DIR)
    if args.no_flash:
        print("\n编译完成（--no-flash，未烧录）。")
        return
    run(idf + ["-p", args.port, "flash"], cwd=FW_DIR)
    print("\n烧录完成。板子重启后会进入配网：手机连上 Xiaozhi- 开头的热点，在页面里选家里的 Wi-Fi 即可。")
    print("服务器地址已经编进固件，不需要在配网页面里再填。")


if __name__ == "__main__":
    main()
