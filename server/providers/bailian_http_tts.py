"""百炼原生 HTTP 语音合成（Qwen-Audio-TTS），给 xiaozhi-esp32-server 用的自定义模块。

为什么需要它：Token Plan 套餐只提供 qwen-audio-3.0-tts-plus，走的是百炼的
SpeechSynthesizer HTTP 接口（返回一个音频下载地址）；后端自带的百炼模块对不上这个接口。

挂载位置：core/providers/tts/bailian_http.py（见 docker-compose.yml），配置里写 type: bailian_http。
接口文档：https://help.aliyun.com/zh/model-studio/token-plan-speech-synthesis
"""
import requests

from config.logger import setup_logging
from core.providers.tts.base import TTSProviderBase

TAG = __name__
logger = setup_logging()


class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.api_key = config.get("api_key")
        self.api_url = config.get("api_url")
        if not self.api_key or not self.api_url:
            raise ValueError("bailian_http 语音合成需要配置 api_key 和 api_url")
        self.model = config.get("model", "qwen-audio-3.0-tts-plus")
        self.voice = config.get("private_voice") or config.get("voice", "longanlingxin")
        self.sample_rate = int(config.get("sample_rate", 24000))
        # 可选的表现力参数：留空就不传，用模型默认值
        self.instruction = (config.get("instruction") or "").strip()
        self.rate = config.get("rate")
        self.pitch = config.get("pitch")
        self.volume = config.get("volume")
        self.audio_file_type = "wav"

    async def text_to_speak(self, text, output_file):
        payload = {"text": text, "voice": self.voice, "format": "wav", "sample_rate": self.sample_rate}
        if self.instruction:
            payload["instruction"] = self.instruction
        for key in ("rate", "pitch", "volume"):
            value = getattr(self, key)
            if value not in (None, ""):
                payload[key] = float(value) if key != "volume" else int(value)
        resp = requests.post(
            self.api_url,
            json={"model": self.model, "input": payload},
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            timeout=self.tts_timeout,
        )
        if resp.status_code != 200:
            raise Exception(f"百炼 HTTP 语音合成失败: {resp.status_code} - {resp.text[:200]}")
        url = ((resp.json().get("output") or {}).get("audio") or {}).get("url")
        if not url:
            raise Exception(f"百炼 HTTP 语音合成没有返回音频地址: {resp.text[:200]}")
        audio = requests.get(url, timeout=self.tts_timeout)
        if audio.status_code != 200:
            raise Exception(f"下载合成音频失败: {audio.status_code}")
        if output_file:
            with open(output_file, "wb") as f:
                f.write(audio.content)
        else:
            return audio.content
