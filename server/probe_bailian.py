"""在后端镜像里运行的探测：用 .env 里的百炼 Key 实际走一遍各条语音通路，看哪条真的能出结果。

两套通路都测，因为不同类型的 Key 能用的不一样：
  ws   —— 流式接口（paraformer-realtime-v2 识别 + cosyvoice-v2 合成），普通百炼 Key 可用，有童声
  http —— 原生 HTTP 接口（qwen-audio-3.0 识别 + 合成），Token Plan 套餐用这一套

每条通路都跑到"真的拿到结果"为止（合成拿到音频、识别任务正常结束），只合成几个字，用量可以忽略。
由 deploy.sh 通过 `docker run ... python -` 调用，输入来自环境变量，输出四行 name=ok 或 name=fail <原因>。
不会打印 Key。
"""
import asyncio
import base64
import io
import json
import os
import urllib.error
import urllib.request
import uuid
import wave

import websockets

KEY = os.environ["BL_KEY"]
HOST = os.environ["BL_HOST"]
WS_VOICE = os.environ.get("BL_WS_VOICE", "longjielidou_v2")
HTTP_VOICE = os.environ.get("BL_HTTP_VOICE", "longanlingxin")
WS_URL = f"wss://{HOST}/api-ws/v1/inference"
HTTP_TTS = f"https://{HOST}/api/v1/services/audio/tts/SpeechSynthesizer"
HTTP_ASR = f"https://{HOST}/api/v1/services/aigc/multimodal-generation/generation"
AUTH = {"Authorization": f"Bearer {KEY}"}
TEXT = "你好"


def brief(text):
    return " ".join(str(text).split())[:140]


def silent_wav(seconds=0.6, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * int(rate * seconds))
    return buf.getvalue()


# ---------- 流式接口 ----------
async def ws_task(payload, after_start, done):
    """发起一个任务；after_start 在任务受理后发送数据；done(event, is_binary) 返回 True 表示成功。"""
    task_id = uuid.uuid4().hex
    head = {"task_id": task_id, "streaming": "duplex"}
    try:
        async with websockets.connect(WS_URL, additional_headers=AUTH, open_timeout=10, close_timeout=3) as ws:
            await ws.send(json.dumps({"header": {"action": "run-task", **head}, "payload": payload}))
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                if isinstance(msg, bytes):
                    if done(None, True):
                        return "ok"
                    continue
                h = json.loads(msg).get("header", {})
                event = h.get("event")
                if event == "task-failed":
                    return "fail " + brief(f"{h.get('error_code')}: {h.get('error_message')}")
                if event == "task-started":
                    await after_start(ws, head)
                if done(event, False):
                    return "ok"
    except Exception as exc:
        return "fail " + brief(f"{type(exc).__name__}: {exc}")


async def ws_tts():
    async def send_text(ws, head):
        await ws.send(json.dumps({"header": {"action": "continue-task", **head}, "payload": {"input": {"text": TEXT}}}))
        await ws.send(json.dumps({"header": {"action": "finish-task", **head}, "payload": {"input": {}}}))

    payload = {
        "task_group": "audio", "task": "tts", "function": "SpeechSynthesizer", "model": "cosyvoice-v2",
        "parameters": {"text_type": "PlainText", "voice": WS_VOICE, "format": "pcm", "sample_rate": 24000,
                       "volume": 50, "rate": 1, "pitch": 1},
        "input": {},
    }
    return await ws_task(payload, send_text, lambda event, is_binary: is_binary)  # 拿到音频才算成功


async def ws_asr():
    async def send_audio(ws, head):
        await ws.send(b"\0\0" * 9600)  # 0.6 秒静音
        await ws.send(json.dumps({"header": {"action": "finish-task", **head}, "payload": {"input": {}}}))

    payload = {
        "task_group": "audio", "task": "asr", "function": "recognition", "model": "paraformer-realtime-v2",
        "parameters": {"format": "pcm", "sample_rate": 16000},
        "input": {},
    }
    return await ws_task(payload, send_audio, lambda event, is_binary: event == "task-finished")


# ---------- 原生 HTTP 接口 ----------
def http_post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={**AUTH, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def http_tts():
    try:
        status, data = http_post(HTTP_TTS, {"model": "qwen-audio-3.0-tts-plus", "input": {
            "text": TEXT, "voice": HTTP_VOICE, "format": "wav", "sample_rate": 16000}})
        url = ((data.get("output") or {}).get("audio") or {}).get("url")
        if status != 200 or not url:
            return "fail " + brief(f"HTTP {status} {data.get('code')}: {data.get('message')}"), None
        audio = urllib.request.urlopen(url, timeout=40).read()
        return ("ok", audio) if audio[:4] == b"RIFF" else ("fail 返回的不是 wav 音频", None)
    except Exception as exc:
        return "fail " + brief(f"{type(exc).__name__}: {exc}"), None


def http_asr(audio):
    try:
        data_uri = "data:audio/wav;base64," + base64.b64encode(audio or silent_wav()).decode()
        status, data = http_post(HTTP_ASR, {
            "model": "qwen-audio-3.0-asr-flash",
            "input": {"messages": [{"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": data_uri}}]}]},
            "parameters": {"format": "wav", "sample_rate": "16000", "language_hints": ["zh"]},
        })
        if status != 200 or "output" not in data:
            return "fail " + brief(f"HTTP {status} {data.get('code')}: {data.get('message')}")
        return "ok"
    except Exception as exc:
        return "fail " + brief(f"{type(exc).__name__}: {exc}")


async def main():
    print("ws_asr=" + await ws_asr(), flush=True)
    print("ws_tts=" + await ws_tts(), flush=True)
    tts_result, audio = await asyncio.to_thread(http_tts)
    print("http_tts=" + tts_result, flush=True)
    print("http_asr=" + await asyncio.to_thread(http_asr, audio), flush=True)


asyncio.run(main())
