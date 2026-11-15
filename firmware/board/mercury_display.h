// Mercury 的屏幕布局：在上游 SpiLcdDisplay（默认样式）的基础上
//   1. 状态文字（时钟、"聆听中"等）和网络、电池图标在同一行，宽度按两侧图标实际占的位置收窄，
//      放不下的长文字在中间滚动，不会压到图标上；
//   2. 表情放在顶栏和底部字幕栏之间的正中间（竖屏用更大的表情图，见 build_firmware.py）；
//   3. 电池图标左边加上百分比数字，没检测到电池时图标和数字都隐藏；
//   4. 触摸用的临时表情（ShowReaction）：显示几秒后恢复应用/服务端设的"正式表情"，
//      正式表情一变（比如服务端发来新表情、状态切换），临时表情立刻让位；
//   5. 养成（SetGrowthLook）：mercury 形态的表情图是空玻璃管，这里按今天的心情温度画红色水银柱，
//      再把配饰叠在表情图上面。别的形态（MERCURY_GROWTH_ART 为 0）不画。
#pragma once

#include "board.h"
#include "display/lcd_display.h"
#include "lvgl_theme.h"
#include "mercury_growth_art.h"  // build_firmware.py 从 character/out/mercury/growth/ 复制过来
#include "mercury_options.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

class MercuryDisplay : public SpiLcdDisplay {
public:
    MercuryDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel, int width,
                   int height, int offset_x, int offset_y, bool mirror_x, bool mirror_y,
                   bool swap_xy)
        : SpiLcdDisplay(panel_io, panel, width, height, offset_x, offset_y, mirror_x, mirror_y,
                        swap_xy) {}

    void SetupUI() override {
        if (setup_ui_called_) {
            return;
        }
        SpiLcdDisplay::SetupUI();

        DisplayLockGuard lock(this);
        auto theme = static_cast<LvglTheme*>(current_theme_);

        // 百分比数字：放在电池图标左边，字体跟随屏幕正文字体
        if (battery_label_ != nullptr) {
            lv_obj_t* right_icons = lv_obj_get_parent(battery_label_);
            battery_text_ = lv_label_create(right_icons);
            lv_label_set_text(battery_text_, "");
            lv_obj_set_style_text_color(battery_text_, theme->text_color(), 0);
            lv_obj_set_style_margin_left(battery_text_, theme->spacing(2), 0);
            lv_obj_move_to_index(battery_text_, lv_obj_get_index(battery_label_));
            lv_obj_add_flag(battery_text_, LV_OBJ_FLAG_HIDDEN);
        }

        // 通知文字（如"音量 60"）上游是自动换行的，窄屏上会变成好几行压到表情上，改成单行滚动
        if (notification_label_ != nullptr) {
            lv_label_set_long_mode(notification_label_, LV_LABEL_LONG_SCROLL_CIRCULAR);
        }
        FitStatusText();

        // 表情放在顶栏和底部字幕栏之间的正中
        if (emoji_box_ != nullptr && top_bar_ != nullptr) {
            lv_obj_update_layout(top_bar_);
            const int top = lv_obj_get_height(top_bar_);
            const int bottom = height_ - (bottom_bar_ != nullptr ? lv_obj_get_height(bottom_bar_) : 0);
            lv_obj_align(emoji_box_, LV_ALIGN_CENTER, 0, (top + bottom) / 2 - height_ / 2);
        }
    }

    void UpdateStatusBar(bool update_all = false) override {
        SpiLcdDisplay::UpdateStatusBar(update_all);
        if (battery_text_ == nullptr) {
            return;
        }

        int level = 0;
        bool charging = false, discharging = false;
        const bool have = Board::GetInstance().GetBatteryLevel(level, charging, discharging);

        DisplayLockGuard lock(this);
        if (!have) {
            // 上游只在有电量时更新图标，电池断开后要自己清掉
            if (battery_icon_ != nullptr) {
                battery_icon_ = nullptr;
                lv_label_set_text(battery_label_, "");
            }
            if (!lv_obj_has_flag(battery_text_, LV_OBJ_FLAG_HIDDEN)) {
                lv_obj_add_flag(battery_text_, LV_OBJ_FLAG_HIDDEN);
                lv_label_set_text(battery_text_, "");
            }
        } else {
            char text[8];
            snprintf(text, sizeof(text), "%d%%", level);
            if (strcmp(lv_label_get_text(battery_text_), text) != 0) {
                lv_label_set_text(battery_text_, text);
            }
            lv_obj_remove_flag(battery_text_, LV_OBJ_FLAG_HIDDEN);
        }
        // 静音、电量图标出现或消失后，重新算状态文字能用的宽度
        FitStatusText();
    }

    void SetTheme(Theme* theme) override {
        SpiLcdDisplay::SetTheme(theme);
        if (battery_text_ != nullptr) {
            DisplayLockGuard lock(this);
            lv_obj_set_style_text_color(battery_text_,
                                        static_cast<LvglTheme*>(theme)->text_color(), 0);
        }
    }

    // 正式表情：应用和服务端都走这里。记下来，并打断正在显示的临时表情。
    bool SetEmotion(const char* emotion) override {
        DisplayLockGuard lock(this);
        base_emotion_ = emotion != nullptr ? emotion : "neutral";
        StopReaction();
        const bool shown = SpiLcdDisplay::SetEmotion(emotion);
        ApplyGrowth();  // 第一张表情图出来之后才知道图的大小，配饰要等它
        return shown;
    }

    // 养成（见 mercury_growth.h）：水银柱高度 = 今天的心情温度 0~100，head / body 是配饰 id（空 = 不戴）。
    // 配饰和水银柱是表情图的子对象，所以 21 个表情、临时表情都带着它们。
    void SetGrowthLook(int mood, const std::string& head, const std::string& body) {
        DisplayLockGuard lock(this);
        growth_mood_ = std::clamp(mood, 0, 100);
        growth_head_ = head;
        growth_body_ = body;
        ApplyGrowth();
    }

    // 临时表情：显示 ms 毫秒，有 then 就接着显示 then（then_ms 毫秒），然后恢复正式表情。
    // 同一个临时表情正在显示时只续时间，不重新切图（摸的时候每 30ms 会调一次）。
    void ShowReaction(const char* emotion, uint32_t ms, const char* then = nullptr,
                      uint32_t then_ms = 0) {
        DisplayLockGuard lock(this);
        if (!setup_ui_called_ || emotion == nullptr) {
            return;
        }
        if (reaction_timer_ == nullptr) {
            reaction_timer_ = lv_timer_create(&MercuryDisplay::OnReactionTimer, ms, this);
        }
        if (reaction_face_ != emotion) {
            if (!SpiLcdDisplay::SetEmotion(emotion)) {
                return;
            }
            reaction_face_ = emotion;
        }
        next_face_ = then;
        next_ms_ = then_ms;
        lv_timer_set_period(reaction_timer_, ms);
        lv_timer_reset(reaction_timer_);
        lv_timer_resume(reaction_timer_);
    }

    // 表情图在屏幕上的位置，触摸用来区分头和身体
    bool GetEmojiArea(lv_area_t* out) {
        DisplayLockGuard lock(this);
        lv_obj_t* obj = emoji_image_;
        if (obj == nullptr || lv_obj_has_flag(obj, LV_OBJ_FLAG_HIDDEN)) {
            obj = emoji_box_;
        }
        if (obj == nullptr) {
            return false;
        }
        lv_obj_get_coords(obj, out);
        return out->y2 > out->y1;
    }

    // 顶部状态栏的下边缘，触摸时状态栏不响应
    int StatusBarBottom() {
        DisplayLockGuard lock(this);
        if (top_bar_ == nullptr) {
            return 0;
        }
        lv_area_t a;
        lv_obj_get_coords(top_bar_, &a);
        return a.y2 + 1;
    }

private:
    lv_obj_t* battery_text_ = nullptr;

    std::string base_emotion_ = "neutral";
    std::string reaction_face_;  // 正在显示的临时表情，空 = 没有
    const char* next_face_ = nullptr;
    uint32_t next_ms_ = 0;
    lv_timer_t* reaction_timer_ = nullptr;

    // ---- 养成 ----
    int growth_mood_ = -1;  // -1 = 还没收到，不画水银柱
    std::string growth_head_, growth_body_;
    lv_obj_t* mercury_bar_ = nullptr;
    lv_obj_t* head_img_ = nullptr;
    lv_obj_t* body_img_ = nullptr;
    int bar_top_ = -1;  // 水银柱现在的上沿（表情图坐标）
    lv_image_dsc_t art_dsc_[sizeof(mercury_art::kAccessories) / sizeof(mercury_art::kAccessories[0])] = {};

    // 调用方需持有显示锁
    void ApplyGrowth() {
#if MERCURY_GROWTH_ART
        if (emoji_image_ == nullptr || growth_mood_ < 0 ||
            lv_obj_get_width(emoji_image_) != mercury_art::kFaceSize) {
            return;  // 表情图还没出来，或者是别的尺寸（字体表情兜底时）
        }
        if (mercury_bar_ == nullptr) {
            mercury_bar_ = lv_obj_create(emoji_image_);
            lv_obj_remove_style_all(mercury_bar_);
            lv_obj_set_style_bg_color(mercury_bar_, lv_color_hex(0xF5333F), 0);
            lv_obj_set_style_bg_opa(mercury_bar_, LV_OPA_COVER, 0);
            head_img_ = lv_image_create(emoji_image_);
            body_img_ = lv_image_create(emoji_image_);
            for (lv_obj_t* o : {mercury_bar_, head_img_, body_img_}) {
                lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE);
                lv_obj_add_flag(o, LV_OBJ_FLAG_IGNORE_LAYOUT);
            }
        }
        // 玻璃管内壁在 240 坐标系里是 x 115~125；下沿到水银球的描边（y 194），上沿最高到 y 166
        const float s = mercury_art::kFaceSize / 240.0f;
        const int x0 = (int)std::ceil(115 * s);
        const int x1 = (int)std::floor(125 * s);
        const int bottom = (int)std::floor(194 * s);
        const int full = (int)std::ceil(166 * s);
        const int top = bottom - (bottom - full) * growth_mood_ / 100;
        lv_obj_set_x(mercury_bar_, x0);
        lv_obj_set_width(mercury_bar_, x1 - x0);
        if (top != bar_top_) {
            const int from = bar_top_ < 0 ? top : bar_top_;
            bar_top_ = top;
            lv_anim_delete(mercury_bar_, nullptr);
            lv_anim_t a;
            lv_anim_init(&a);
            lv_anim_set_var(&a, mercury_bar_);
            lv_anim_set_values(&a, from, top);
            lv_anim_set_duration(&a, from == top ? 0 : 800);
            lv_anim_set_path_cb(&a, lv_anim_path_ease_out);
            lv_anim_set_user_data(&a, (void*)(intptr_t)bottom);
            lv_anim_set_custom_exec_cb(&a, [](lv_anim_t* anim, int32_t v) {
                auto* bar = static_cast<lv_obj_t*>(anim->var);
                const int bottom = (int)(intptr_t)lv_anim_get_user_data(anim);
                lv_obj_set_y(bar, v);
                lv_obj_set_height(bar, bottom - v);
            });
            lv_anim_start(&a);
        }
        ShowAccessory(head_img_, growth_head_);
        ShowAccessory(body_img_, growth_body_);
#endif
    }

    void ShowAccessory(lv_obj_t* img, const std::string& id) {
        for (size_t i = 0; i < sizeof(art_dsc_) / sizeof(art_dsc_[0]); ++i) {
            const auto& art = mercury_art::kAccessories[i];
            if (art.id == nullptr || id != art.id) {
                continue;
            }
            lv_image_dsc_t& d = art_dsc_[i];
            if (d.data == nullptr) {
                d.header.magic = LV_IMAGE_HEADER_MAGIC;
                d.header.cf = LV_COLOR_FORMAT_ARGB8888;
                d.header.w = art.w;
                d.header.h = art.h;
                d.header.stride = art.w * 4;
                d.data_size = art.w * art.h * 4;
                d.data = art.argb8888;
            }
            if (lv_image_get_src(img) != &d) {
                lv_image_set_src(img, &d);
            }
            lv_obj_set_pos(img, art.x, art.y);
            lv_obj_remove_flag(img, LV_OBJ_FLAG_HIDDEN);
            return;
        }
        lv_obj_add_flag(img, LV_OBJ_FLAG_HIDDEN);
    }

    // 调用方需持有显示锁
    void StopReaction() {
        if (reaction_timer_ != nullptr) {
            lv_timer_pause(reaction_timer_);
        }
        reaction_face_.clear();
        next_face_ = nullptr;
    }

    // 在 LVGL 任务里运行（已持有显示锁）
    static void OnReactionTimer(lv_timer_t* t) {
        auto* self = static_cast<MercuryDisplay*>(lv_timer_get_user_data(t));
        if (self->next_face_ != nullptr) {
            const char* face = self->next_face_;
            self->next_face_ = nullptr;
            self->SpiLcdDisplay::SetEmotion(face);
            self->reaction_face_ = face;
            lv_timer_set_period(t, self->next_ms_);
            lv_timer_reset(t);
            return;
        }
        lv_timer_pause(t);
        self->reaction_face_.clear();
        self->SpiLcdDisplay::SetEmotion(self->base_emotion_.c_str());
    }

    // 状态文字居中，宽度 = 屏宽 - 2 × (左右两侧图标里占得更宽的那一侧)。
    // 调用方需持有显示锁（SetupUI / UpdateStatusBar 里都已持有）。
    void FitStatusText() {
        if (top_bar_ == nullptr || network_label_ == nullptr || battery_label_ == nullptr ||
            status_label_ == nullptr) {
            return;
        }
        lv_obj_update_layout(top_bar_);
        lv_area_t net, right;
        lv_obj_get_coords(network_label_, &net);
        lv_obj_get_coords(lv_obj_get_parent(battery_label_), &right);
        const int left_used = net.x2 + 1;
        const int right_used = width_ - right.x1;
        const int gap = static_cast<LvglTheme*>(current_theme_)->spacing(2);
        const int width = std::max(40, width_ - 2 * (std::max(left_used, right_used) + gap));
        if (lv_obj_get_width(status_label_) != width) {
            lv_obj_set_width(status_label_, width);
            lv_obj_align(status_label_, LV_ALIGN_CENTER, 0, 0);
            if (notification_label_ != nullptr) {
                lv_obj_set_width(notification_label_, width);
                lv_obj_align(notification_label_, LV_ALIGN_CENTER, 0, 0);
            }
        }
    }
};
