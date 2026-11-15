// Mercury 的触摸互动。
//
// 只有一条规则：按住 = "我要说话 / 不说了"，点和摸 = 跟它玩。
//   - 点一下：松手时还没到按住的时间、也不是在摸 → 换个表情（头部开心、身体挠痒痒，连点会头晕），
//     待机时有时还会出声（"嘿嘿""好痒呀"）
//   - 摸摸：按着滑动，来回加起来超过 kStrokePathPx → 眯眼，松手后爱心眼，待机时说"好舒服呀"。
//     待机时连续摸满 kPatStrokeMs，Mercury 会真的开口回应（发一句"【摸摸头】"给服务器，
//     kPatCooldownMs 内最多一次）
//   - 按住：kLongPressMs 不怎么动 → 跟 BOOT 键单击一样：待机时开始对话、说话时打断、聆听时结束对话
//     （语音切到"长按说话"模式时：按住开始说，松手发送）
// 养成：点一下、摸一摸会让今天的心情温度（水银柱）涨一点，见 mercury_growth.h。
// 只有按住和摸头开口会联网，点和摸都在本地完成。Mercury 说话时点和摸也换表情（不打断，
// 下一句的表情一来就换回去），但不出声。开机、配网、升级、连接中时触摸一律不响应；顶部状态栏不响应。
//
// 睡觉：待机 kSleepAfterMs 没人说话也没人摸 → 换成困了的表情；再过 kDimAfterMs → 屏幕调暗。
// 摸一下就醒（这一下只用来叫醒），唤醒词照常能用。
//
// 不走 LVGL 的输入设备：界面上没有可点的控件，自己在 LVGL 任务里每 30ms 读一次触摸芯片
// （这块板子的触摸中断脚没接，只能轮询）。读失败只记日志，不像 esp_lvgl_port 那样直接重启。
#pragma once

#include "application.h"
#include "backlight.h"
#include "board.h"
#include "mercury_display.h"
#include "mercury_sounds.h"  // build_firmware.py 从 firmware/sounds/*.ogg 生成

#include <esp_lcd_touch.h>
#include <esp_log.h>
#include <esp_lvgl_port.h>
#include <esp_random.h>
#include <lvgl.h>

#include <cstdlib>
#include <functional>

class MercuryTouch {
public:
    MercuryTouch(esp_lcd_touch_handle_t tp, MercuryDisplay* display,
                 std::function<bool()> press_to_talk_enabled)
        : tp_(tp), display_(display), press_to_talk_enabled_(std::move(press_to_talk_enabled)) {
        lvgl_port_lock(0);
        timer_ = lv_timer_create(&MercuryTouch::OnTimer, kPollMs, this);
        lvgl_port_unlock();
        ESP_LOGI(kTag, "Touch ready, polling every %dms", (int)kPollMs);
    }

    // 养成：点和摸会让今天的心情温度涨一点（见 mercury_growth.h），在 LVGL 任务里回调
    void SetCheerCallback(std::function<void(int)> cb) { on_cheer_ = std::move(cb); }

private:
    // ---- 可调参数 ----
    static constexpr uint32_t kPollMs = 30;
    static constexpr int kMoveTolerancePx = 20;    // 点和按住时手指允许晃动的距离
    static constexpr uint32_t kLongPressMs = 700;  // 按住多久算"按住"
    static constexpr int kStrokePathPx = 60;       // 滑动累计多远算"摸摸"
    static constexpr int kJitterPx = 3;            // 小于这个的移动不计入滑动距离
    static constexpr int kReleaseDebounce = 2;     // 连续几次读不到才算松手（小孩手指会轻微离开屏幕）
    static constexpr int kMashTaps = 4;            // 2 秒内点这么多下算"连点"
    static constexpr uint32_t kMashWindowMs = 2000;
    static constexpr uint32_t kDizzyMs = 3000;     // 连点后的冷却时间，期间再点继续头晕
    static constexpr uint32_t kTapFaceMs = 1500;
    static constexpr uint32_t kStrokeEndFaceMs = 2000;
    static constexpr uint32_t kSpeakingFaceMs = 1000;  // 说话时的触摸表情短一点，别盖住它说话的表情
    // 出声
    static constexpr uint32_t kClipGapMs = 2500;   // 两句音效之间至少隔这么久
    static constexpr uint32_t kQuietTapMs = 8000;  // 停了这么久之后的第一下一定出声，连着点只有三分之一出声
    // 摸头开口
    static constexpr uint32_t kPatStrokeMs = 2000;
    static constexpr uint32_t kPatCooldownMs = 5 * 60 * 1000;
    static constexpr const char* kPatText = "【摸摸头】";  // 服务端提示词里说明了这句的意思
    // 睡觉
    static constexpr uint32_t kSleepAfterMs = 5 * 60 * 1000;
    static constexpr uint32_t kDimAfterMs = 60 * 1000;
    static constexpr uint8_t kDimBrightness = 10;
    // 养成：心情温度
    static constexpr int kTapCheer = 1;
    static constexpr int kStrokeCheer = 4;
    static constexpr const char* kTag = "MercuryTouch";

    enum class Zone { kStatusBar, kHead, kBody };
    enum class Sleep { kAwake, kDrowsy, kDimmed };

    esp_lcd_touch_handle_t tp_;
    MercuryDisplay* display_;  // 可能为空（表情消息样式下），这时只有按住有效
    std::function<bool()> press_to_talk_enabled_;
    std::function<void(int)> on_cheer_;
    lv_timer_t* timer_ = nullptr;

    // 当前这一次按压
    bool pressed_ = false;
    int release_count_ = 0;
    uint32_t down_at_ = 0;
    int down_x_ = 0, down_y_ = 0, last_x_ = 0, last_y_ = 0;
    int path_ = 0;          // 累计滑动距离
    int max_offset_ = 0;    // 离按下点最远的距离
    Zone zone_ = Zone::kBody;
    bool ignored_ = false;  // 从状态栏开始按的、或者是用来叫醒的，整次忽略
    bool long_fired_ = false;
    bool stroking_ = false;
    uint32_t stroke_started_at_ = 0;
    bool ptt_active_ = false;

    // 连点
    uint32_t tap_times_[kMashTaps] = {};
    int tap_count_ = 0;
    uint32_t dizzy_until_ = 0;
    const char* last_face_ = nullptr;
    bool tapped_before_ = false;
    uint32_t last_tap_at_ = 0;

    // 出声、摸头开口
    bool clip_played_ = false;
    uint32_t last_clip_at_ = 0;
    bool patted_ = false;
    uint32_t last_pat_at_ = 0;

    // 睡觉
    Sleep sleep_ = Sleep::kAwake;
    uint32_t sleep_changed_at_ = 0;
    uint32_t last_activity_ = 0;

    int read_errors_ = 0;

    static void OnTimer(lv_timer_t* t) {
        static_cast<MercuryTouch*>(lv_timer_get_user_data(t))->Poll();
    }

    void Poll() {
        bool down = false;
        int x = 0, y = 0;
        if (esp_lcd_touch_read_data(tp_) == ESP_OK) {
            esp_lcd_touch_point_data_t pt[1] = {};
            uint8_t cnt = 0;
            if (esp_lcd_touch_get_data(tp_, pt, &cnt, 1) == ESP_OK && cnt > 0) {
                down = true;
                x = pt[0].x;
                y = pt[0].y;
            }
        } else if (read_errors_++ % 100 == 0) {
            ESP_LOGW(kTag, "Failed to read touch controller (%d errors so far)", read_errors_);
        }

        const uint32_t now = lv_tick_get();
        if (down) {
            release_count_ = 0;
            if (!pressed_) {
                PressStart(x, y, now);
            } else {
                PressMove(x, y, now);
            }
        } else if (pressed_ && ++release_count_ >= kReleaseDebounce) {
            Release(now);
        }
        UpdateSleep(now);
    }

    void PressStart(int x, int y, uint32_t now) {
        pressed_ = true;
        down_at_ = now;
        down_x_ = last_x_ = x;
        down_y_ = last_y_ = y;
        path_ = 0;
        max_offset_ = 0;
        long_fired_ = false;
        stroking_ = false;
        zone_ = ZoneAt(x, y);
        ignored_ = zone_ == Zone::kStatusBar;
        last_activity_ = now;
        const auto state = State();
        ESP_LOGI(kTag, "down (%d,%d) zone=%s state=%d", x, y, ZoneName(zone_), (int)state);
        if (sleep_ != Sleep::kAwake && state == kDeviceStateIdle) {
            ignored_ = true;  // 这一下只用来叫醒
            WakeUp(now, true);
            return;
        }
        if (ignored_) {
            return;
        }
        // 按下的瞬间先给个反应，让孩子知道它感觉到了
        if (state == kDeviceStateIdle) {
            React("surprised", kLongPressMs + 300);
        }
    }

    void PressMove(int x, int y, uint32_t now) {
        const int step = std::abs(x - last_x_) + std::abs(y - last_y_);
        if (step >= kJitterPx) {
            path_ += step;
            last_x_ = x;
            last_y_ = y;
        }
        const int offset = std::abs(x - down_x_) + std::abs(y - down_y_);
        if (offset > max_offset_) {
            max_offset_ = offset;
        }
        if (ignored_ || long_fired_) {
            return;
        }

        if (!stroking_ && path_ >= kStrokePathPx) {
            stroking_ = true;
            stroke_started_at_ = now;
            ESP_LOGI(kTag, "stroke start");
        }
        if (stroking_) {
            // 摸的过程中一直眯眼（同一个表情只续时间，不重新切图）
            if (CanReact(State())) {
                React("relaxed", 1000);
            }
            return;
        }

        if (now - down_at_ >= kLongPressMs && max_offset_ <= kMoveTolerancePx) {
            long_fired_ = true;
            LongPress();
        }
    }

    void Release(uint32_t now) {
        pressed_ = false;
        last_activity_ = now;
        const uint32_t held = now - down_at_;
        ESP_LOGI(kTag, "up (%d,%d) held=%dms path=%d", last_x_, last_y_, (int)held, path_);
        if (ignored_) {
            return;
        }
        if (long_fired_) {
            if (ptt_active_) {
                ptt_active_ = false;
                ESP_LOGI(kTag, "press-to-talk: stop");
                Application::GetInstance().StopListening();
            }
            return;
        }
        if (stroking_) {
            StrokeEnd(now);
            return;
        }
        // 松手时还没到按住的时间、也不是在摸，就当作点了一下（对小孩宽松一点，不卡 0.4 秒）
        Tap(now);
    }

    void Tap(uint32_t now) {
        const auto state = State();
        ESP_LOGI(kTag, "tap zone=%s state=%d", ZoneName(zone_), (int)state);
        if (state == kDeviceStateListening) {
            React("winking", 600);  // 我在听呢，不结束对话
            return;
        }
        if (state != kDeviceStateIdle && state != kDeviceStateSpeaking) {
            return;
        }
        // 说话时点一下不打断，只短暂换个表情
        const uint32_t face_ms = state == kDeviceStateIdle ? kTapFaceMs : kSpeakingFaceMs;

        // 头晕的冷却期里再点，继续头晕
        if (static_cast<int32_t>(dizzy_until_ - now) > 0) {
            Dizzy(now, false);
            return;
        }
        // 连点：最近 kMashTaps 下都落在 kMashWindowMs 之内
        tap_times_[tap_count_ % kMashTaps] = now;
        tap_count_++;
        if (tap_count_ >= kMashTaps &&
            now - tap_times_[tap_count_ % kMashTaps] <= kMashWindowMs) {
            tap_count_ = 0;
            Dizzy(now, true);
            return;
        }

        const bool head = zone_ == Zone::kHead;
        static const char* const kHead[] = {"happy", "winking", "surprised"};
        static const char* const kBody[] = {"laughing", "funny", "silly"};
        const char* const* faces = head ? kHead : kBody;
        // 随机挑一个，不和上一次重复
        int i = esp_random() % 3;
        if (faces[i] == last_face_) {
            i = (i + 1 + esp_random() % 2) % 3;
        }
        const char* face = faces[i];
        last_face_ = face;
        React(face, face_ms);
        Cheer(kTapCheer);

        // 停了一会儿后的第一下一定出声，连着点只有三分之一出声，免得吵
        const bool quiet = !tapped_before_ || now - last_tap_at_ >= kQuietTapMs;
        tapped_before_ = true;
        last_tap_at_ = now;
        if (state == kDeviceStateIdle && (quiet || esp_random() % 3 == 0)) {
            const bool alt = esp_random() % 2 == 0;
            PlayClip(head ? (alt ? "hehe" : "wow") : (alt ? "tickle1" : "tickle2"), now);
        }
    }

    void Dizzy(uint32_t now, bool starting) {
        ESP_LOGI(kTag, "dizzy");
        dizzy_until_ = now + kDizzyMs;
        React("confused", 2000, "embarrassed", 1500);
        if (starting && State() == kDeviceStateIdle) {
            PlayClip("dizzy", now);
        }
    }

    void StrokeEnd(uint32_t now) {
        const auto state = State();
        const uint32_t stroke_ms = now - stroke_started_at_;
        ESP_LOGI(kTag, "stroke end path=%d stroke=%dms state=%d", path_, (int)stroke_ms, (int)state);
        if (!CanReact(state)) {
            return;
        }
        Cheer(kStrokeCheer);
        if (state != kDeviceStateIdle) {
            React("loving", state == kDeviceStateSpeaking ? kSpeakingFaceMs : kStrokeEndFaceMs);
            return;
        }
        React("loving", kStrokeEndFaceMs);
        // 待机时摸得够久、而且最近没开过口：让 Mercury 真的回应一句
        if (stroke_ms >= kPatStrokeMs && (!patted_ || now - last_pat_at_ >= kPatCooldownMs)) {
            patted_ = true;
            last_pat_at_ = now;
            ESP_LOGI(kTag, "pat: asking Mercury to respond");
            Application::GetInstance().WakeWordInvoke(kPatText);
            return;
        }
        PlayClip("comfy", now);
    }

    // 摸摸在待机、聆听、说话时都有表情反应
    static bool CanReact(DeviceState state) {
        return state == kDeviceStateIdle || state == kDeviceStateListening ||
               state == kDeviceStateSpeaking;
    }

    void LongPress() {
        auto& app = Application::GetInstance();
        const auto state = State();
        ESP_LOGI(kTag, "long press state=%d", (int)state);
        if (state != kDeviceStateIdle && state != kDeviceStateListening &&
            state != kDeviceStateSpeaking && state != kDeviceStateNotifying) {
            return;  // 连接中、开机、配网、升级等：不响应
        }

        if (press_to_talk_enabled_ && press_to_talk_enabled_()) {
            // 长按说话模式：按着说，松手发送（和 BOOT 键一样）
            ptt_active_ = true;
            ESP_LOGI(kTag, "press-to-talk: start");
            app.StartListening();
            return;
        }
        // 和 BOOT 键单击同一条路：待机→开始对话，说话→打断转聆听，聆听→结束对话
        if (state != kDeviceStateListening) {
            app.PlayPopupOnNextListening();  // 开始听的时候"叮"一声
        }
        app.ToggleChatState();
    }

    // ---- 睡觉 ----

    void UpdateSleep(uint32_t now) {
        if (State() != kDeviceStateIdle) {
            // 对话、放儿歌、开机等都算有事在做；唤醒词或 BOOT 键把它叫起来时也从这里醒
            if (sleep_ != Sleep::kAwake) {
                WakeUp(now, false);
            }
            last_activity_ = now;
            return;
        }
        if (pressed_ || display_ == nullptr) {
            return;
        }
        if (sleep_ == Sleep::kAwake && now - last_activity_ >= kSleepAfterMs) {
            ESP_LOGI(kTag, "falling asleep");
            sleep_ = Sleep::kDrowsy;
            sleep_changed_at_ = now;
            display_->SetEmotion("sleepy");
        } else if (sleep_ == Sleep::kDrowsy && now - sleep_changed_at_ >= kDimAfterMs) {
            ESP_LOGI(kTag, "asleep, dimming the screen");
            sleep_ = Sleep::kDimmed;
            sleep_changed_at_ = now;
            if (auto* backlight = Board::GetInstance().GetBacklight()) {
                backlight->SetBrightness(kDimBrightness);  // 不保存，醒来恢复原来的亮度
            }
        }
    }

    void WakeUp(uint32_t now, bool by_touch) {
        ESP_LOGI(kTag, "wake up (%s)", by_touch ? "touch" : "state change");
        if (sleep_ == Sleep::kDimmed) {
            if (auto* backlight = Board::GetInstance().GetBacklight()) {
                backlight->RestoreBrightness();
            }
        }
        sleep_ = Sleep::kAwake;
        last_activity_ = now;
        if (by_touch && display_ != nullptr) {
            display_->SetEmotion("neutral");
            React("surprised", 600, "happy", 1500);
            PlayClip("awake", now);
        }
        // 被唤醒词或 BOOT 键叫醒时，应用会按新状态自己设表情
    }

    // ---- 工具 ----

    // 只在待机时出声（说话时会和它的声音叠在一起，聆听时会被当成小朋友说的话）
    void PlayClip(const char* name, uint32_t now) {
        if (clip_played_ && now - last_clip_at_ < kClipGapMs) {
            return;
        }
        const std::string_view clip = mercury_sounds::Get(name);
        if (clip.empty()) {
            return;
        }
        clip_played_ = true;
        last_clip_at_ = now;
        // 放到主任务里播放，不在界面任务里排队等解码
        auto& app = Application::GetInstance();
        app.Schedule([clip]() {
            auto& app = Application::GetInstance();
            if (app.GetDeviceState() == kDeviceStateIdle) {
                app.PlaySound(clip);
            }
        });
    }

    void Cheer(int points) {
        if (on_cheer_) {
            on_cheer_(points);
        }
    }

    void React(const char* face, uint32_t ms, const char* then = nullptr, uint32_t then_ms = 0) {
        if (display_ != nullptr) {
            display_->ShowReaction(face, ms, then, then_ms);
        }
    }

    Zone ZoneAt(int x, int y) const {
        (void)x;
        if (display_ == nullptr) {
            return Zone::kBody;
        }
        if (y < display_->StatusBarBottom()) {
            return Zone::kStatusBar;
        }
        // 表情图的上半部分是头（圆脑袋），下半部分（围巾、温度计身体）和字幕栏算身体
        lv_area_t a;
        const int split = display_->GetEmojiArea(&a) ? (a.y1 + a.y2) / 2 : 160;
        return y < split ? Zone::kHead : Zone::kBody;
    }

    static const char* ZoneName(Zone z) {
        switch (z) {
            case Zone::kStatusBar: return "status";
            case Zone::kHead: return "head";
            default: return "body";
        }
    }

    static DeviceState State() { return Application::GetInstance().GetDeviceState(); }
};
