// Mercury 的养成（板子这一侧）。成长记录（星星、教过的东西、解锁的配饰）在服务器上，
// 见 server/plugins/mercury_growth.py；板子负责两件事：
//
// 1. 屏幕上的样子：服务器每次连上来、或者孩子教了东西 / 做到小约定 / 换配饰时，调用设备上的
//    self.mercury.growth 工具，把"头上、身上戴什么"告诉板子。板子记在 NVS 里，开机不联网也照样戴着。
//    这个工具是 user-only 的，不出现在大模型的工具列表里，只有服务器的插件会调。
// 2. 今天的心情温度（0~100）= 水银柱的高度：每天第一次用时回到 kBaseline，之后只涨不掉。
//    点一下、摸一摸能让它涨，但最多涨到 kTouchCap；再往上要靠聊天、教它东西、做到小约定。
//    几天不玩也不会降，第二天照样从 kBaseline 开始（"只开心不难过"）。
#pragma once

#include "mcp_server.h"
#include "mercury_display.h"
#include "settings.h"

#include <esp_log.h>
#include <lvgl.h>

#include <algorithm>
#include <ctime>
#include <string>

class MercuryGrowth {
public:
    explicit MercuryGrowth(MercuryDisplay* display) : display_(display) {
        Settings s(kNs, false);
        stars_ = s.GetInt("stars", 0);
        head_ = s.GetString("head", "");
        body_ = s.GetString("body", "");
        mood_ = s.GetInt("mood", kBaseline);
        mood_day_ = s.GetInt("mood_day", 0);
        RolloverDay();
        Show();

        McpServer::GetInstance().AddUserOnlyTool(
            "self.mercury.growth",
            "Mercury growth state pushed by the server plugin (accessories and mood).",
            PropertyList({
                Property("stars", kPropertyTypeInteger, 0, 0, 1000000),
                Property("head", kPropertyTypeString, std::string("")),
                Property("body", kPropertyTypeString, std::string("")),
                Property("event", kPropertyTypeString, std::string("sync")),
            }),
            [this](const PropertyList& p) -> ReturnValue {
                OnServer(p["stars"].value<int>(), p["head"].value<std::string>(),
                         p["body"].value<std::string>(), p["event"].value<std::string>());
                return true;
            });

        // 每分钟看一眼：过了零点就回到 kBaseline；攒着的触摸加分顺便写进 NVS
        lvgl_port_lock(0);
        timer_ = lv_timer_create(&MercuryGrowth::OnTimer, 60 * 1000, this);
        lvgl_port_unlock();
        ESP_LOGI(kTag, "stars=%d head=%s body=%s mood=%d", stars_, head_.c_str(), body_.c_str(), mood_);
    }

    // 触摸：点一下 +1，摸一摸 +4。在 LVGL 任务里调用。
    void Cheer(int points) {
        RolloverDay();
        if (mood_ >= kTouchCap) {
            return;
        }
        mood_ = std::min(kTouchCap, mood_ + points);
        dirty_ = true;
        Show();
    }

private:
    static constexpr const char* kTag = "MercuryGrowth";
    static constexpr const char* kNs = "mercury";
    static constexpr int kBaseline = 30;  // 每天开始时的心情温度
    static constexpr int kTouchCap = 70;  // 光靠点和摸最多到这里
    static constexpr int kMax = 100;

    MercuryDisplay* display_;
    lv_timer_t* timer_ = nullptr;
    int stars_ = 0;
    std::string head_, body_;
    int mood_ = kBaseline;
    int mood_day_ = 0;  // yyyymmdd，0 = 还不知道
    bool dirty_ = false;

    void OnServer(int stars, const std::string& head, const std::string& body, const std::string& event) {
        // 服务器推来的事件让心情温度涨多少
        int bump = 0;
        if (event == "sync") bump = 3;            // 来找 Mercury 玩了
        else if (event == "learned") bump = 12;   // 教了它新东西
        else if (event == "habit") bump = 8;      // 做到了好习惯小约定
        else if (event == "levelup") bump = 15;   // 长大了，得到新配饰
        ESP_LOGI(kTag, "server: stars=%d head=%s body=%s event=%s", stars, head.c_str(), body.c_str(),
                 event.c_str());

        lvgl_port_lock(0);
        RolloverDay();
        stars_ = stars;
        head_ = head;
        body_ = body;
        mood_ = std::min(kMax, mood_ + bump);
        Save();
        Show();
        lvgl_port_unlock();
    }

    static void OnTimer(lv_timer_t* t) {
        auto* self = static_cast<MercuryGrowth*>(lv_timer_get_user_data(t));
        if (self->RolloverDay()) {
            self->Show();
        }
        if (self->dirty_) {
            self->Save();
        }
    }

    // 换天了就回到 kBaseline。没对上时间（开机还没联网）时不动。
    bool RolloverDay() {
        time_t now = time(nullptr);
        struct tm tm_now;
        localtime_r(&now, &tm_now);
        if (tm_now.tm_year + 1900 < 2025) {
            return false;
        }
        const int today = (tm_now.tm_year + 1900) * 10000 + (tm_now.tm_mon + 1) * 100 + tm_now.tm_mday;
        if (today == mood_day_) {
            return false;
        }
        ESP_LOGI(kTag, "new day %d, mood back to %d", today, kBaseline);
        mood_day_ = today;
        mood_ = kBaseline;
        dirty_ = true;
        return true;
    }

    void Save() {
        Settings s(kNs, true);
        s.SetInt("stars", stars_);
        s.SetString("head", head_);
        s.SetString("body", body_);
        s.SetInt("mood", mood_);
        s.SetInt("mood_day", mood_day_);
        dirty_ = false;
    }

    void Show() {
        if (display_ != nullptr) {
            display_->SetGrowthLook(mood_, head_, body_);
        }
    }
};
