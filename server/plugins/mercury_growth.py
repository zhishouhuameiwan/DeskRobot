"""Mercury 的养成：然然教它东西、和它做好习惯小约定，它攒小星星、长大、解锁配饰。

挂载到后端的 plugins_func/functions/ 下（见 docker-compose.yml），后端启动时自动加载。做三件事：

1. 给大模型三个工具（要在配置的 Intent.function_call.functions 里列出来才会启用）：
   - mercury_learned：她教了 Mercury 一样新东西
   - mercury_habit：早安 / 喝水 / 晚安 的小约定
   - mercury_dress：戴上、换上或摘下已经解锁的配饰
2. 每次设备连上来时，把成长情况写进提示词的 {{ dynamic_context }}（教过的东西、星星、配饰），
   并且算作"今天来看 Mercury 了"。
3. 把星星和配饰推给板子（设备上的 self.mercury.growth 工具），屏幕上的配饰和水银柱跟着变。

设计原则（给五岁孩子）：只涨不掉；按天数和教的东西长大，每天有上限，玩得久不会长得快；
几天没来也不会有任何负面变化。

数据存在 data/mercury_growth/<设备>.json（服务器的 /opt/server/data/mercury_growth/），
家长可以直接看；删掉这个文件就是从头开始。

第 2 点要挂到后端的 PromptManager 上（后端没有提供"连接建立"的插件接口）。后端镜像升级后
如果那两个方法变了，这里只打一条警告：工具照常能用，只是提示词里看不到成长情况。
"""

import asyncio
import difflib
import hashlib
import json
import os
import re
import threading
from datetime import datetime

from config.logger import setup_logging
from plugins_func.register import Action, ActionResponse, ToolType, register_function

TAG = __name__
logger = setup_logging()

DATA_DIR = os.path.join("data", "mercury_growth")

# 配饰：id -> (名字, 部位, 需要攒够的星星)。id 和顺序要和 character/gen-faces.mjs 的 ACCESSORIES 一致。
ITEMS = {
    "flower": ("小红花", "head", 5),
    "star_badge": ("星星徽章", "body", 15),
    "knit_hat": ("毛线帽", "head", 30),
    "rainbow_badge": ("彩虹徽章", "body", 50),
    "crown": ("小皇冠", "head", 80),
}
SLOT_NAMES = {"head": "头上", "body": "身上"}

# 每天最多能得的星星：来看 Mercury 1 颗，教新东西最多 3 颗，三个好习惯各 1 颗
MAX_LEARN_STARS_PER_DAY = 3
HABITS = {
    "早安": "早上和你说早安",
    "喝水": "喝了水",
    "晚安": "睡前和你说晚安",
}
LEARNED_IN_PROMPT = 8  # 提示词里列出最近教过的几件
LEARNED_KEEP = 300

_lock = threading.Lock()
_push_id = [9000]  # 发给设备的 MCP 请求 id，避开后端自己用的 1、2 和工具调用的小编号


# ---------------- 存储 ----------------

def _path(device_id):
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", device_id or "unknown")
    return os.path.join(DATA_DIR, f"{safe}.json")


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _load(device_id):
    state = {
        "stars": 0,
        "days_together": 0,
        "unlocked": [],
        "wearing": {"head": None, "body": None},
        "learned": [],
        "today": {},
        "celebrate": [],
    }
    try:
        with open(_path(device_id), encoding="utf-8") as f:
            state.update(json.load(f))
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.bind(tag=TAG).error(f"读取成长记录失败，先按新的算：{e}")
    if state["today"].get("date") != _today():
        state["today"] = {"date": _today(), "visit": False, "learned": 0, "habits": []}
    return state


def _save(device_id, state):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = _path(device_id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _award(state, n=1):
    """加星星，返回这次新解锁的配饰 id（新配饰自动戴上）。"""
    before = state["stars"]
    state["stars"] += n
    new = []
    for item_id, (_, slot, need) in ITEMS.items():
        if before < need <= state["stars"] and item_id not in state["unlocked"]:
            state["unlocked"].append(item_id)
            state["wearing"][slot] = item_id
            new.append(item_id)
    return new


def _next_item(state):
    for item_id, (name, _, need) in ITEMS.items():
        if item_id not in state["unlocked"]:
            return name, need - state["stars"]
    return None, 0


def _norm(text):
    return re.sub(r"[\s，。,.!！?？、~～]", "", text or "")


def _same_lesson(a, b):
    """大模型每次概括的说法会有点不一样（'蜗牛背着房子慢慢爬' / '蜗牛背着自己的房子慢慢爬'），按相似度算。"""
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    return a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= 0.7


def _wearing_text(state):
    parts = [f"{SLOT_NAMES[slot]}戴着{ITEMS[i][0]}" for slot, i in state["wearing"].items() if i]
    return "、".join(parts) if parts else "什么配饰也没戴"


def _unlock_text(new):
    names = "、".join(f"「{ITEMS[i][0]}」" for i in new)
    return (
        f"你刚刚长大了一点，得到了新配饰{names}，已经戴上了，她在屏幕上就能看到。"
        "开心地告诉她，谢谢她陪你长大。"
    )


# ---------------- 推给设备 ----------------

async def _push_async(conn, state, event):
    from core.providers.tools.device_mcp.mcp_handler import send_mcp_message

    # 设备刚连上时 MCP 还在初始化，等它就绪（最多 10 秒）
    for _ in range(40):
        client = getattr(conn, "mcp_client", None)
        if client is not None and await client.is_ready():
            break
        await asyncio.sleep(0.25)
    else:
        logger.bind(tag=TAG).info("设备的 MCP 没有就绪，这次不推送成长状态")
        return
    _push_id[0] += 1
    payload = {
        "jsonrpc": "2.0",
        "id": _push_id[0],
        "method": "tools/call",
        "params": {
            "name": "self.mercury.growth",
            "arguments": {
                "stars": state["stars"],
                "head": state["wearing"].get("head") or "",
                "body": state["wearing"].get("body") or "",
                "event": event,
            },
        },
    }
    await send_mcp_message(conn, payload)


def _push(conn, state, event):
    """event：sync（刚连上）、learned、habit、levelup、dress。设备按 event 让水银柱涨多少。"""
    loop = getattr(conn, "loop", None)
    if loop is None:
        return
    snapshot = json.loads(json.dumps(state))
    asyncio.run_coroutine_threadsafe(_push_async(conn, snapshot, event), loop)


# ---------------- 连接建立时：算"今天来看了"，写进提示词 ----------------

def _context_lines(state):
    lines = []
    name, left = _next_item(state)
    grown = len(state["unlocked"])
    stage = f"已经长大过 {grown} 次" if grown else "还是一支刚来的小温度计"
    nxt = f"再攒 {left} 颗就能得到「{name}」" if name else "所有配饰都得到了，还在继续长大"
    lines.append(f"Mercury 的成长：一共攒了 {state['stars']} 颗小星星，{stage}，{nxt}；现在{_wearing_text(state)}")
    if len(state["unlocked"]) > 1:
        lines.append("已经有的配饰（可以换着戴）：" + "、".join(ITEMS[i][0] for i in state["unlocked"]))
    learned = state["learned"]
    if learned:
        recent = "；".join(x["text"] for x in reversed(learned[-LEARNED_IN_PROMPT:]))
        lines.append(f"她教过你的东西（一共 {len(learned)} 件，最近的在前）：{recent}")
    else:
        lines.append("她还没有教过你东西")
    today = state["today"]
    done = [k for k in HABITS if k in today.get("habits", [])]
    lines.append(
        f"今天她已经教了你 {today.get('learned', 0)} 件新东西"
        + (f"，做到了{'、'.join(done)}的小约定" if done else "")
    )
    if state["celebrate"]:
        lines.append("刚刚：" + _unlock_text(state["celebrate"]) + "这次聊天一开口就先说这件事。")
    return lines


def on_session_start(conn):
    device_id = getattr(conn, "device_id", None)
    if not device_id:
        return ""
    with _lock:
        state = _load(device_id)
        event = "sync"
        if not state["today"]["visit"]:
            state["today"]["visit"] = True
            state["days_together"] += 1
            new = _award(state)
            if new:
                state["celebrate"] = new
                event = "levelup"
        lines = _context_lines(state)
        state["celebrate"] = []  # 已经写进这次的提示词了
        _save(device_id, state)
    _push(conn, state, event)
    return "\n".join(f"- {l}" for l in lines)


def _install_prompt_hook():
    try:
        from core.utils import prompt_manager as pm

        cls = pm.PromptManager
        orig_update = cls.update_context_info
        orig_build = cls.build_enhanced_prompt
    except Exception as e:
        logger.bind(tag=TAG).warning(f"后端的提示词管理器和预期不一样，成长情况不会写进提示词：{e}")
        return
    if getattr(cls, "_mercury_growth_hooked", False):
        return

    def update_context_info(self, conn, client_ip):
        orig_update(self, conn, client_ip)
        try:
            extra = on_session_start(conn)
            if extra:
                base = self.context_data if isinstance(self.context_data, str) else ""
                self.context_data = (base + "\n" + extra).strip()
        except Exception as e:
            logger.bind(tag=TAG).error(f"生成成长上下文失败：{e}")

    def build_enhanced_prompt(self, user_prompt, device_id, client_ip=None, *args, **kwargs):
        # 后端会把增强后的提示词按设备缓存 5 分钟；成长情况每次连接都可能变，先把旧的清掉
        try:
            h = hashlib.md5(user_prompt.encode("utf-8")).hexdigest()[:8]
            key = f"enhanced_prompt:{device_id}:{kwargs.get('emoji_enabled', True)}:{h}"
            self.cache_manager.delete(self.CacheType.DEVICE_PROMPT, key)
        except Exception:
            pass
        return orig_build(self, user_prompt, device_id, client_ip, *args, **kwargs)

    cls.update_context_info = update_context_info
    cls.build_enhanced_prompt = build_enhanced_prompt
    cls._mercury_growth_hooked = True
    logger.bind(tag=TAG).info("Mercury 养成已启用")


_install_prompt_hook()


# ---------------- 工具 ----------------

def _reply(text):
    return ActionResponse(Action.REQLLM, text, None)


mercury_learned_desc = {
    "type": "function",
    "function": {
        "name": "mercury_learned",
        "description": (
            "小朋友教了 Mercury 一样新东西时调用：告诉你一个知识、一个新词、一首儿歌、一个游戏怎么玩、"
            "一种动物或东西是什么样的，或者回答了你'这是什么呀''为什么呀'的问题。"
            "她只是聊天、提问、说心情时不要调用；她以前教过的（上下文里列着）也不要再调用。"
            "住址、电话、家人和幼儿园的名字不是知识，不要记录。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "thing": {
                    "type": "string",
                    "description": "她教你的东西，用一句十五个字以内的话概括，比如'蜗牛背着房子慢慢爬'",
                }
            },
            "required": ["thing"],
        },
    },
}


@register_function("mercury_learned", mercury_learned_desc, ToolType.SYSTEM_CTL)
def mercury_learned(conn, thing: str = ""):
    thing = (thing or "").strip()[:40]
    device_id = getattr(conn, "device_id", None)
    if not thing or not device_id:
        return _reply("没记下来。像平常一样回应她就好。")
    with _lock:
        state = _load(device_id)
        for old in state["learned"]:
            if _same_lesson(old["text"], thing):
                return _reply(
                    f"她以前（{old['date']}）就教过你「{old['text']}」。"
                    "开心地告诉她你还记得，不用再谢一遍。"
                )
        state["learned"].append({"date": _today(), "text": thing})
        state["learned"] = state["learned"][-LEARNED_KEEP:]
        n = len(state["learned"])
        new = []
        star = ""
        if state["today"]["learned"] < MAX_LEARN_STARS_PER_DAY:
            state["today"]["learned"] += 1
            new = _award(state)
            star = "你因此攒到了一颗小星星。"
        _save(device_id, state)
    _push(conn, state, "levelup" if new else "learned")
    logger.bind(tag=TAG).info(f"学会了第 {n} 件：{thing}")
    text = (
        f"记住了「{thing}」，这是她教你的第 {n} 件事。{star}"
        "用一两句话谢谢她（刚才已经谢过就不要再谢），再用你自己的话把学到的东西说一遍，让她知道你真的学会了。"
    )
    if new:
        text += _unlock_text(new)
    return _reply(text)


mercury_habit_desc = {
    "type": "function",
    "function": {
        "name": "mercury_habit",
        "description": (
            "和小朋友的好习惯小约定：早上她和你说早安（kind=早安）；她告诉你她喝了水（kind=喝水）；"
            "晚上她和你说晚安准备睡觉（kind=晚安）。说晚安时只调用这个工具，它会顺便结束聊天，"
            "不要再调用 handle_exit_intent。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": list(HABITS), "description": "哪一个小约定"}
            },
            "required": ["kind"],
        },
    },
}


@register_function("mercury_habit", mercury_habit_desc, ToolType.SYSTEM_CTL)
def mercury_habit(conn, kind: str = ""):
    device_id = getattr(conn, "device_id", None)
    if kind not in HABITS or not device_id:
        return _reply("像平常一样回应她就好。")
    if kind == "晚安":
        conn.close_after_chat = True
        tail = "用一两句温柔的话和她说晚安，说完就去睡觉了。"
    elif kind == "早安":
        tail = "用一句元气满满的话和她说早安。"
    else:
        tail = "夸夸她，说你也'喝'了一口，心情温度都升高了。"
    hour = datetime.now().hour
    if (kind == "早安" and not 5 <= hour < 12) or (kind == "晚安" and not (hour >= 18 or hour < 5)):
        return _reply("现在不是这个小约定的时间，不算星星。" + tail)
    with _lock:
        state = _load(device_id)
        if kind in state["today"]["habits"]:
            return _reply(f"今天已经做到「{kind}」这个小约定了，这次不再加星星，也不用提星星。" + tail)
        state["today"]["habits"].append(kind)
        new = _award(state)
        _save(device_id, state)
    _push(conn, state, "levelup" if new else "habit")
    text = f"她{HABITS[kind]}，你们的小约定做到了，你攒到了一颗小星星。" + tail
    if new:
        text += _unlock_text(new)
    return _reply(text)


mercury_dress_desc = {
    "type": "function",
    "function": {
        "name": "mercury_dress",
        "description": (
            "小朋友让 Mercury 戴上、换上或者摘下某个配饰时调用。配饰有：小红花、毛线帽、小皇冠（戴在头上），"
            "星星徽章、彩虹徽章（戴在身上）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "item": {
                    "type": "string",
                    "enum": [v[0] for v in ITEMS.values()],
                    "description": "哪个配饰",
                },
                "action": {"type": "string", "enum": ["戴上", "摘下"], "description": "戴上（换上）还是摘下"},
            },
            "required": ["item", "action"],
        },
    },
}


@register_function("mercury_dress", mercury_dress_desc, ToolType.SYSTEM_CTL)
def mercury_dress(conn, item: str = "", action: str = "戴上"):
    device_id = getattr(conn, "device_id", None)
    item_id = next((k for k, v in ITEMS.items() if v[0] == item), None)
    if item_id is None or not device_id:
        return _reply("没有这个配饰。告诉她你现在有哪些配饰。")
    name, slot, need = ITEMS[item_id]
    with _lock:
        state = _load(device_id)
        if item_id not in state["unlocked"]:
            left = need - state["stars"]
            return _reply(
                f"你还没有「{name}」，再攒 {left} 颗小星星才能得到。"
                "高高兴兴地告诉她再一起玩几天就有了，不要让她觉得有压力。"
            )
        if action == "摘下":
            if state["wearing"].get(slot) == item_id:
                state["wearing"][slot] = None
            text = f"你把「{name}」摘下来了。"
        else:
            state["wearing"][slot] = item_id
            text = f"你{SLOT_NAMES[slot]}换上了「{name}」，她在屏幕上就能看到。"
        _save(device_id, state)
    _push(conn, state, "dress")
    return _reply(text + "用一句开心的话回应她。")
