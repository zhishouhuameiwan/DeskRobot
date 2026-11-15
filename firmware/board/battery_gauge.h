// 锂电池电量估算：电池正极经分压电阻接到一个 ADC1 引脚，按电压查放电曲线。
//
// 立创实战派本身没有电池电路，这个引脚上可能什么都没接（悬空）。悬空引脚读数会乱跳，
// 所以每次采样先打开内部下拉电阻读一次：接了 100kΩ 分压时读数仍有几百毫伏，悬空时接近 0。
// 连续几次判定为"没接电池"时 GetLevel() 返回 false，屏幕上就不显示电量。
#pragma once

#include "application.h"

#include <driver/gpio.h>
#include <esp_adc/adc_cali.h>
#include <esp_adc/adc_cali_scheme.h>
#include <esp_adc/adc_oneshot.h>
#include <esp_log.h>
#include <esp_timer.h>

#include <algorithm>
#include <atomic>
#include <climits>
#include <cstdlib>

class BatteryGauge {
public:
    BatteryGauge(int gpio, float divider) : gpio_(static_cast<gpio_num_t>(gpio)), divider_(divider) {
        adc_unit_t unit;
        if (adc_oneshot_io_to_channel(gpio, &unit, &channel_) != ESP_OK) {
            ESP_LOGE(kTag, "GPIO%d is not an ADC pin, battery display disabled", gpio);
            return;
        }
        if (unit != ADC_UNIT_1) {
            // ADC2 和 Wi-Fi 共用，联网时读不出来
            ESP_LOGE(kTag, "GPIO%d is on ADC2 (unusable with Wi-Fi), battery display disabled", gpio);
            return;
        }

        adc_oneshot_unit_init_cfg_t unit_cfg = {};
        unit_cfg.unit_id = unit;
        unit_cfg.ulp_mode = ADC_ULP_MODE_DISABLE;
        if (adc_oneshot_new_unit(&unit_cfg, &adc_) != ESP_OK) {
            ESP_LOGE(kTag, "ADC unit init failed, battery display disabled");
            adc_ = nullptr;
            return;
        }
        adc_oneshot_chan_cfg_t chan_cfg = {};
        chan_cfg.atten = ADC_ATTEN_DB_12;  // 量程约 0~3.1V
        chan_cfg.bitwidth = ADC_BITWIDTH_DEFAULT;
        ESP_ERROR_CHECK(adc_oneshot_config_channel(adc_, channel_, &chan_cfg));

#if ADC_CALI_SCHEME_CURVE_FITTING_SUPPORTED
        adc_cali_curve_fitting_config_t cali_cfg = {};
        cali_cfg.unit_id = unit;
        cali_cfg.chan = channel_;
        cali_cfg.atten = ADC_ATTEN_DB_12;
        cali_cfg.bitwidth = ADC_BITWIDTH_DEFAULT;
        if (adc_cali_create_scheme_curve_fitting(&cali_cfg, &cali_) != ESP_OK) {
            cali_ = nullptr;
        }
#endif
        if (cali_ == nullptr) {
            ESP_LOGW(kTag, "ADC calibration unavailable, battery voltage will be approximate");
        }

        esp_timer_create_args_t timer_args = {};
        timer_args.callback = [](void* arg) { static_cast<BatteryGauge*>(arg)->Sample(); };
        timer_args.arg = this;
        timer_args.name = "battery_gauge";
        ESP_ERROR_CHECK(esp_timer_create(&timer_args, &timer_));
        ESP_ERROR_CHECK(esp_timer_start_periodic(timer_, kSamplePeriodUs));
        Sample();
    }

    // 有电池时返回 true 并给出 0~100 的电量
    bool GetLevel(int& level) const {
        if (!present_.load()) {
            return false;
        }
        level = level_.load();
        return true;
    }

private:
    static constexpr const char* kTag = "BatteryGauge";
    static constexpr int64_t kSamplePeriodUs = 2 * 1000 * 1000;
    static constexpr int kPresentAfter = 2;  // 连续几次正常才显示
    static constexpr int kAbsentAfter = 3;   // 连续几次异常才隐藏
    static constexpr int kLogEvery = 30;     // 约每分钟打印一次电压，方便校准

    gpio_num_t gpio_;
    float divider_;
    adc_channel_t channel_ = ADC_CHANNEL_0;
    adc_oneshot_unit_handle_t adc_ = nullptr;
    adc_cali_handle_t cali_ = nullptr;
    esp_timer_handle_t timer_ = nullptr;

    std::atomic<bool> present_{false};
    std::atomic<int> level_{0};
    int good_count_ = 0;
    int bad_count_ = 0;
    float vbat_ema_ = 0;
    int shown_level_ = -1;
    int sample_count_ = 0;

    // 读一次引脚电压（毫伏），失败返回 -1
    int ReadPinMv() {
        int raw = 0;
        if (adc_oneshot_read(adc_, channel_, &raw) != ESP_OK) {
            return -1;
        }
        int mv = 0;
        if (cali_ != nullptr && adc_cali_raw_to_voltage(cali_, raw, &mv) == ESP_OK) {
            return mv;
        }
        return raw * 3100 / 4095;
    }

    // 1S 锂电池（带载）电压 -> 电量。0% 定在 3.40V，留出余量让低电量提示先于掉电出现。
    static int VoltageToLevel(float v) {
        static const struct { float v; int level; } kCurve[] = {
            {4.20f, 100}, {4.10f, 92}, {4.00f, 82}, {3.92f, 72}, {3.85f, 62}, {3.80f, 53},
            {3.75f, 43},  {3.71f, 33}, {3.68f, 24}, {3.64f, 15}, {3.58f, 8},  {3.50f, 4},
            {3.40f, 0},
        };
        if (v >= kCurve[0].v) {
            return 100;
        }
        for (size_t i = 1; i < sizeof(kCurve) / sizeof(kCurve[0]); i++) {
            if (v >= kCurve[i].v) {
                const auto& hi = kCurve[i - 1];
                const auto& lo = kCurve[i];
                return lo.level + (int)((v - lo.v) / (hi.v - lo.v) * (hi.level - lo.level) + 0.5f);
            }
        }
        return 0;
    }

    void Sample() {
        if (adc_ == nullptr) {
            return;
        }
        // 说话时喇叭电流大，电池电压会被拉低一截，这段时间的读数不用
        if (present_.load() &&
            Application::GetInstance().GetDeviceState() == kDeviceStateSpeaking) {
            return;
        }

        // 1. 打开内部下拉（约 45kΩ）判断引脚上有没有接分压电阻
        gpio_pulldown_en(gpio_);
        ReadPinMv();  // 丢掉切换后的第一次读数
        const int pulled_mv = ReadPinMv();
        gpio_pulldown_dis(gpio_);
        ReadPinMv();

        // 2. 正常读 8 次取平均，同时看波动（悬空引脚波动大）
        int sum = 0, lo = INT_MAX, hi = INT_MIN, n = 0;
        for (int i = 0; i < 8; i++) {
            int mv = ReadPinMv();
            if (mv < 0) {
                continue;
            }
            sum += mv;
            lo = std::min(lo, mv);
            hi = std::max(hi, mv);
            n++;
        }
        const float vbat = n > 0 ? (float)sum / n / 1000.0f * divider_ : 0;
        const bool plausible = n == 8 && pulled_mv > 300 && (hi - lo) < 120 && vbat > 2.9f &&
                               vbat < 4.6f;

        if (plausible) {
            bad_count_ = 0;
            if (!present_.load()) {
                if (++good_count_ < kPresentAfter) {
                    return;
                }
                vbat_ema_ = vbat;
                shown_level_ = -1;
                ESP_LOGI(kTag, "Battery detected: %.2fV", vbat);
            } else {
                vbat_ema_ += 0.2f * (vbat - vbat_ema_);
            }

            // 电量取 5 的整数倍，并且要偏离当前显示值 4% 以上才变，避免数字来回跳
            const int level = VoltageToLevel(vbat_ema_);
            if (shown_level_ < 0 || std::abs(level - shown_level_) >= 4 || level == 0 ||
                level == 100) {
                shown_level_ = std::min(100, (level + 2) / 5 * 5);
                level_.store(shown_level_);
            }
            present_.store(true);
            if (sample_count_++ % kLogEvery == 0) {
                ESP_LOGI(kTag, "Battery %.3fV (pin %dmV, pulled %dmV) -> %d%%", vbat_ema_,
                         n > 0 ? sum / n : -1, pulled_mv, shown_level_);
            }
        } else {
            good_count_ = 0;
            if (present_.load() && ++bad_count_ >= kAbsentAfter) {
                present_.store(false);
                ESP_LOGW(kTag, "Battery reading lost (pin %dmV, spread %dmV, pulled %dmV)",
                         n > 0 ? sum / n : -1, n > 0 ? hi - lo : -1, pulled_mv);
            } else if (!present_.load() && sample_count_++ % kLogEvery == 0) {
                ESP_LOGI(kTag, "No battery on GPIO%d (pin %dmV, spread %dmV, pulled %dmV)",
                         (int)gpio_, n > 0 ? sum / n : -1, n > 0 ? hi - lo : -1, pulled_mv);
            }
        }
    }
};
