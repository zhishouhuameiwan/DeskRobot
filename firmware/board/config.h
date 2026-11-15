// Mercury 板型配置：基于上游 lckfb/szpi-esp32s3/config.h（立创·实战派 ESP32-S3），
// 增加了屏幕方向、摄像头旋转和电池检测的选项。
// build_firmware.py 会把本目录复制到 xiaozhi-esp32/main/boards/mercury/，
// 并按命令行参数生成 mercury_options.h；这里的默认值只在没有该文件时生效。
#ifndef _BOARD_CONFIG_H_
#define _BOARD_CONFIG_H_

#include <driver/gpio.h>

#if __has_include("mercury_options.h")
#include "mercury_options.h"
#endif

// ---- 选项（mercury_options.h 可覆盖）----
#define MERCURY_ORIENTATION_LANDSCAPE    0  // 上游原样：横屏 320x240
#define MERCURY_ORIENTATION_PORTRAIT     1  // 竖屏 240x320：从横屏位置顺时针转 90° 摆放
#define MERCURY_ORIENTATION_PORTRAIT_180 2  // 竖屏 240x320：从横屏位置逆时针转 90° 摆放

#ifndef MERCURY_ORIENTATION
#define MERCURY_ORIENTATION MERCURY_ORIENTATION_PORTRAIT
#endif

// 摄像头画面顺时针旋转的角度（0/90/180/270）。摄像头跟着板子一起转，
// 竖着放时不转回来，上传给大模型的照片就是横躺的。
#ifndef MERCURY_CAMERA_ROTATION
#if MERCURY_ORIENTATION == MERCURY_ORIENTATION_PORTRAIT
#define MERCURY_CAMERA_ROTATION 90
#elif MERCURY_ORIENTATION == MERCURY_ORIENTATION_PORTRAIT_180
#define MERCURY_CAMERA_ROTATION 270
#else
#define MERCURY_CAMERA_ROTATION 0
#endif
#endif

// 电池电压检测：电池正极经 1:1 分压（两只 100kΩ）接到这个 GPIO。
// 板子本身没有电池电路，GPIO10 是多功能扩展口上唯一空闲的 ADC1 引脚。
// 设为 -1 关闭电量显示。没接分压电阻时固件会自动隐藏电量。
#ifndef MERCURY_BATTERY_ADC_GPIO
#define MERCURY_BATTERY_ADC_GPIO 10
#endif
// 电池电压 / 引脚电压
#ifndef MERCURY_BATTERY_DIVIDER
#define MERCURY_BATTERY_DIVIDER 2.0f
#endif

// ---- 硬件 ----
#define AUDIO_INPUT_SAMPLE_RATE  24000
#define AUDIO_OUTPUT_SAMPLE_RATE 24000

#define AUDIO_INPUT_REFERENCE    true

#define AUDIO_I2S_GPIO_MCLK GPIO_NUM_38
#define AUDIO_I2S_GPIO_WS GPIO_NUM_13
#define AUDIO_I2S_GPIO_BCLK GPIO_NUM_14
#define AUDIO_I2S_GPIO_DIN  GPIO_NUM_12
#define AUDIO_I2S_GPIO_DOUT GPIO_NUM_45

#define AUDIO_CODEC_USE_PCA9557
#define AUDIO_CODEC_I2C_SDA_PIN  GPIO_NUM_1
#define AUDIO_CODEC_I2C_SCL_PIN  GPIO_NUM_2
#define AUDIO_CODEC_ES8311_ADDR  ES8311_CODEC_DEFAULT_ADDR
#define AUDIO_CODEC_ES7210_ADDR  0x82

#define BUILTIN_LED_GPIO        GPIO_NUM_48
#define BOOT_BUTTON_GPIO        GPIO_NUM_0
#define VOLUME_UP_BUTTON_GPIO   GPIO_NUM_NC
#define VOLUME_DOWN_BUTTON_GPIO GPIO_NUM_NC

// ST7789 面板的原生方向是竖屏 240x320。横屏靠交换 XY + 镜像实现（与上游相同），
// 竖屏两种摆法互差 180°。触摸屏的原生坐标与面板一致，所以用同一组翻转参数。
#define PANEL_NATIVE_WIDTH  240
#define PANEL_NATIVE_HEIGHT 320

#if MERCURY_ORIENTATION == MERCURY_ORIENTATION_LANDSCAPE
#define DISPLAY_WIDTH   320
#define DISPLAY_HEIGHT  240
#define DISPLAY_MIRROR_X true
#define DISPLAY_MIRROR_Y false
#define DISPLAY_SWAP_XY true
#elif MERCURY_ORIENTATION == MERCURY_ORIENTATION_PORTRAIT
#define DISPLAY_WIDTH   240
#define DISPLAY_HEIGHT  320
#define DISPLAY_MIRROR_X false
#define DISPLAY_MIRROR_Y false
#define DISPLAY_SWAP_XY false
#elif MERCURY_ORIENTATION == MERCURY_ORIENTATION_PORTRAIT_180
#define DISPLAY_WIDTH   240
#define DISPLAY_HEIGHT  320
#define DISPLAY_MIRROR_X true
#define DISPLAY_MIRROR_Y true
#define DISPLAY_SWAP_XY false
#else
#error "Unknown MERCURY_ORIENTATION"
#endif

#define DISPLAY_OFFSET_X  0
#define DISPLAY_OFFSET_Y  0

#define DISPLAY_BACKLIGHT_PIN GPIO_NUM_42
#define DISPLAY_BACKLIGHT_OUTPUT_INVERT true

/* Camera pins */
#define CAMERA_PIN_PWDN GPIO_NUM_NC
#define CAMERA_PIN_RESET GPIO_NUM_NC
#define CAMERA_PIN_XCLK GPIO_NUM_5
#define CAMERA_PIN_SIOD GPIO_NUM_1
#define CAMERA_PIN_SIOC GPIO_NUM_2

#define CAMERA_PIN_D7 GPIO_NUM_9
#define CAMERA_PIN_D6 GPIO_NUM_4
#define CAMERA_PIN_D5 GPIO_NUM_6
#define CAMERA_PIN_D4 GPIO_NUM_15
#define CAMERA_PIN_D3 GPIO_NUM_17
#define CAMERA_PIN_D2 GPIO_NUM_8
#define CAMERA_PIN_D1 GPIO_NUM_18
#define CAMERA_PIN_D0 GPIO_NUM_16
#define CAMERA_PIN_VSYNC GPIO_NUM_3
#define CAMERA_PIN_HREF GPIO_NUM_46
#define CAMERA_PIN_PCLK GPIO_NUM_7

#define XCLK_FREQ_HZ 20000000


#endif // _BOARD_CONFIG_H_
