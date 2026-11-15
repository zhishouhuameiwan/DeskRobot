"""用 Mercury 现在的音色合成触摸时的短音效，存成 firmware/sounds/*.ogg（编译时打包进固件）。

这个脚本要在服务器的 xiaozhi-esp32-server 容器里运行：那里有百炼的 Key、语音合成配置和 ffmpeg。
在这台电脑上（Git Bash）执行：

    ssh -i ~/.ssh/mercury_deploy_ed25519 root@<SERVER_IP> \
        'docker exec -i xiaozhi-esp32-server python -' < firmware/make_sounds.py > firmware/generated/sounds.jsonl
    node firmware/unpack_sounds.mjs firmware/generated/sounds.jsonl

想换句子或语气就改下面的 CLIPS，名字不要改（固件按名字找）。
输出：每行一个 JSON，{"name", "text", "ms", "ogg"(base64)}，Ogg Opus 16kHz 单声道、60ms 帧，和服务器下发的语音同一规格。
"""
import base64
import json
import os
import subprocess
import sys
import tempfile

import requests

try:
    import yaml

    def load_yaml(path):
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
except ImportError:  # 后端有的版本只带 ruamel
    from ruamel.yaml import YAML

    def load_yaml(path):
        with open(path, encoding="utf-8") as f:
            return YAML(typ="safe").load(f)

# 名字: (要说的话, 语气补充)
CLIPS = {
    "hehe": ("嘿嘿！", "被摸了一下脑袋，开心地笑"),
    "wow": ("哇哦！", "有点惊喜，俏皮"),
    "tickle1": ("哈哈，好痒呀！", "被挠痒痒，笑着说"),
    "tickle2": ("嘻嘻，别挠啦！", "被挠痒痒，笑着撒娇"),
    "comfy": ("嗯，好舒服呀。", "被轻轻摸头，舒服、懒洋洋的"),
    "dizzy": ("哎呀，头好晕呀。", "被戳得晕乎乎的，可爱地抱怨"),
    "awake": ("我醒啦！", "刚睡醒，开心有精神"),
}


def main():
    cfg = load_yaml("data/.config.yaml")
    module = cfg["selected_module"]["TTS"]
    tts = cfg["TTS"][module]
    if tts.get("type") != "bailian_http":
        sys.exit(f"当前语音合成是 {module}（{tts.get('type')}），这个脚本只支持 bailian_http")
    base_instruction = (tts.get("instruction") or "").strip().rstrip("。")
    sys.stderr.write(f"voice={tts.get('voice')} model={tts.get('model')}\n")

    for name, (text, mood) in CLIPS.items():
        instruction = f"{base_instruction}，{mood}" if base_instruction else mood
        payload = {
            "text": text,
            "voice": tts.get("private_voice") or tts.get("voice"),
            "format": "wav",
            "sample_rate": int(tts.get("sample_rate", 24000)),
            "instruction": instruction,
        }
        resp = requests.post(
            tts["api_url"],
            json={"model": tts.get("model", "qwen-audio-3.0-tts-plus"), "input": payload},
            headers={"Authorization": f"Bearer {tts['api_key']}", "Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        url = resp.json()["output"]["audio"]["url"]
        wav = requests.get(url, timeout=30).content

        with tempfile.TemporaryDirectory() as tmp:
            src, dst = os.path.join(tmp, "in.wav"), os.path.join(tmp, "out.ogg")
            with open(src, "wb") as f:
                f.write(wav)
            # 去掉首尾静音，让声音一摸就出来；转成和服务器下发语音相同的规格
            trim = ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                    "silenceremove=start_periods=1:start_threshold=-45dB,areverse")
            subprocess.run(
                ["ffmpeg", "-loglevel", "error", "-y", "-i", src, "-af", trim, "-ac", "1", "-ar", "16000",
                 "-c:a", "libopus", "-b:a", "32k", "-frame_duration", "60", "-application", "voip", dst],
                check=True,
            )
            ms = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", dst],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            with open(dst, "rb") as f:
                ogg = f.read()
        print(json.dumps({"name": name, "text": text, "ms": int(float(ms) * 1000),
                          "ogg": base64.b64encode(ogg).decode()}, ensure_ascii=False), flush=True)
        sys.stderr.write(f"{name}: {text} {len(ogg)} bytes\n")


if __name__ == "__main__":
    main()
