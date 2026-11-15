"""百炼原生 HTTP 语音识别（Qwen-Audio-ASR），给 xiaozhi-esp32-server 用的自定义模块。

为什么需要它：Token Plan 套餐只提供 qwen-audio-3.0-asr-flash，走的是百炼的
multimodal-generation HTTP 接口；后端自带的百炼模块对不上这个接口。

挂载位置：core/providers/asr/bailian_http.py（见 docker-compose.yml），配置里写 type: bailian_http。
接口文档：https://help.aliyun.com/zh/model-studio/token-plan-speech-recognition
"""
import asyncio
import base64
import os
from typing import List, Optional, Tuple

import requests

from config.logger import setup_logging
from core.providers.asr.base import ASRProviderBase
from core.providers.asr.dto.dto import InterfaceType

TAG = __name__
logger = setup_logging()


class ASRProvider(ASRProviderBase):
    def __init__(self, config: dict, delete_audio_file: bool):
        super().__init__()
        self.interface_type = InterfaceType.NON_STREAM
        self.api_key = config.get("api_key")
        self.api_url = config.get("api_url")
        if not self.api_key or not self.api_url:
            raise ValueError("bailian_http 语音识别需要配置 api_key 和 api_url")
        self.model = config.get("model", "qwen-audio-3.0-asr-flash")
        hints = config.get("language_hints", ["zh"])
        self.language_hints = [hints] if isinstance(hints, str) else list(hints or [])
        self.timeout = float(config.get("timeout", 20))
        self.output_dir = config.get("output_dir", "tmp/")
        self.delete_audio_file = delete_audio_file
        os.makedirs(self.output_dir, exist_ok=True)

    # 让基类把这一句话的录音存成 16kHz 单声道 wav 临时文件再交给我们
    def requires_file(self) -> bool:
        return True

    def prefers_temp_file(self) -> bool:
        return True

    def _recognize(self, wav_path: str) -> str:
        with open(wav_path, "rb") as f:
            audio = base64.b64encode(f.read()).decode("ascii")
        parameters = {"format": "wav", "sample_rate": "16000"}
        if self.language_hints:
            parameters["language_hints"] = self.language_hints
        body = {
            "model": self.model,
            "input": {"messages": [{"role": "user", "content": [
                {"type": "input_audio", "input_audio": {"data": "data:audio/wav;base64," + audio}}
            ]}]},
            "parameters": parameters,
        }
        resp = requests.post(
            self.api_url,
            json=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        return ((resp.json().get("output") or {}).get("text") or "").strip()

    async def speech_to_text(
        self, opus_data: List[bytes], session_id: str, artifacts=None
    ) -> Tuple[Optional[str], Optional[str]]:
        file_path = getattr(artifacts, "file_path", None)
        temp_path = getattr(artifacts, "temp_path", None)
        if not temp_path:
            return "", file_path
        try:
            # requests 是阻塞调用，放到线程里跑，别卡住其他连接
            text = await asyncio.to_thread(self._recognize, temp_path)
            return text, file_path
        except Exception as e:
            logger.bind(tag=TAG).error(f"百炼 HTTP 语音识别失败: {e}")
            return "", file_path
