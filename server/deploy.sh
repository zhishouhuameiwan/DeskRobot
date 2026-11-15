#!/usr/bin/env bash
# Mercury 服务端一键部署 / 更新脚本。在阿里云服务器上、server 目录里运行：
#   bash deploy.sh                部署或更新（改了 .env 或配置模板后重跑即可）
#   bash deploy.sh --render-only  只生成 data/.config.yaml，不联网、不碰 Docker（本地检查用）
set -euo pipefail
cd "$(dirname "$0")"

RENDER_ONLY=0
[ "${1:-}" = "--render-only" ] && RENDER_ONLY=1

BACKEND_IMAGE=ghcr.nju.edu.cn/xinnan-tech/xiaozhi-esp32-server:server_latest
BACKEND=xiaozhi-esp32-server
BL_DEFAULT_HOST=dashscope.aliyuncs.com
ASR_SOURCE=/opt/xiaozhi-esp32-server/core/providers/asr/aliyunbl_stream.py
MIN_FUNASR_MB=3500

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m注意：%s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m错误：%s\033[0m\n' "$*" >&2; exit 1; }

# ---------- 读取 .env（只按 KEY=VALUE 解析，不当脚本执行） ----------
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  die "已生成 server/.env。请先填好 PUBLIC_HOST 和 DEEPSEEK_API_KEY，再重新运行本脚本。"
fi
chmod 600 .env 2>/dev/null || true
sed -i 's/\r$//' .env   # .env 可能在 Windows 上编辑过，去掉行尾的回车

getv() { local v; v=$(grep -m1 "^$1=" .env | cut -d= -f2- || true); printf '%s' "$v"; }
set_env() {
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else printf '%s=%s\n' "$1" "$2" >> .env; fi
}
rand_hex() { head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; }

PUBLIC_HOST=$(getv PUBLIC_HOST)
DEEPSEEK_API_KEY=$(getv DEEPSEEK_API_KEY)
DASHSCOPE_API_KEY=$(getv DASHSCOPE_API_KEY)
CHILD_NAME=$(getv CHILD_NAME);     CHILD_NAME=${CHILD_NAME:-小朋友}
TTS_VOICE=$(getv TTS_VOICE);       TTS_VOICE=${TTS_VOICE:-longjielidou_v2}
QWEN_TTS_VOICE=$(getv QWEN_TTS_VOICE); QWEN_TTS_VOICE=${QWEN_TTS_VOICE:-longanlingxin}
GATEWAY_PORT=$(getv GATEWAY_PORT); GATEWAY_PORT=${GATEWAY_PORT:-18080}
SECRET_PATH=$(getv SECRET_PATH)
AUTH_KEY=$(getv AUTH_KEY)
NGINX_IMAGE=$(getv NGINX_IMAGE)
QWEATHER_API_HOST=$(getv QWEATHER_API_HOST)
QWEATHER_API_KEY=$(getv QWEATHER_API_KEY)

[ -n "$PUBLIC_HOST" ] || die ".env 里的 PUBLIC_HOST 还没填（服务器公网 IP）。"
if [ -z "$DEEPSEEK_API_KEY" ]; then
  [ "$RENDER_ONLY" = 1 ] || die ".env 里的 DEEPSEEK_API_KEY 还没填。"
  warn "DEEPSEEK_API_KEY 为空（仅渲染检查，继续）。"
fi
if [ -z "$SECRET_PATH" ]; then SECRET_PATH="p$(rand_hex 12)"; set_env SECRET_PATH "$SECRET_PATH"; fi
if [ -z "$AUTH_KEY" ];    then AUTH_KEY="$(rand_hex 24)";     set_env AUTH_KEY "$AUTH_KEY"; fi
printf '%s' "$SECRET_PATH" | grep -Eq '^[A-Za-z0-9_-]{12,}$' || die "SECRET_PATH 只能是 12 位以上的字母、数字、下划线或短横线。"
printf '%s' "$GATEWAY_PORT" | grep -Eq '^[0-9]+$' || die "GATEWAY_PORT 必须是数字。"
printf '%s' "$TTS_VOICE" | grep -Eq '^[A-Za-z0-9_-]+$' || die "TTS_VOICE 只能是字母、数字、下划线或短横线。"
printf '%s' "$QWEN_TTS_VOICE" | grep -Eq '^[A-Za-z0-9._-]+$' || die "QWEN_TTS_VOICE 只能是字母、数字、点、下划线或短横线。"

# ---------- 百炼接入地址 ----------
# 普通的百炼 Key 用默认地址；Token Plan / 业务空间的 Key 要在 .env 里填专属的 DASHSCOPE_BASE_URL。
DASHSCOPE_BASE_URL=$(getv DASHSCOPE_BASE_URL)
DASHSCOPE_BASE_URL=${DASHSCOPE_BASE_URL:-https://$BL_DEFAULT_HOST/compatible-mode/v1}
DASHSCOPE_BASE_URL=${DASHSCOPE_BASE_URL%/}
BL_HOST=$(printf '%s' "$DASHSCOPE_BASE_URL" | sed -E 's#^[a-z]+://([^/]+).*#\1#')
DASHSCOPE_WS_URL="wss://$BL_HOST/api-ws/v1/inference"
BL_HTTP_ASR_URL="https://$BL_HOST/api/v1/services/aigc/multimodal-generation/generation"
BL_HTTP_TTS_URL="https://$BL_HOST/api/v1/services/audio/tts/SpeechSynthesizer"
CUSTOM_ENDPOINT=0
[ "$BL_HOST" != "$BL_DEFAULT_HOST" ] && CUSTOM_ENDPOINT=1

# ---------- 选方案：默认是不依赖百炼的备用方案，实测通过的项目再换成百炼 ----------
ASR=FunASR; TTS=EdgeTTS; VLLM=DeepSeekVLLM
KEY_PROBLEMS=""
http_code() { curl -s -o /dev/null -m 15 -w '%{http_code}' "$@" 2>/dev/null || true; }
show() { if [ "$1" = ok ]; then printf '可用'; else printf '不可用（%s）' "${1#fail }"; fi; }

if [ "$RENDER_ONLY" = 1 ]; then
  # 本地渲染检查不联网、不使用 Key：有百炼 Key 就按"全部可用"来渲染
  # （专属地址按 Token Plan 的原生 HTTP 通路渲染，默认地址按流式通路渲染）
  if [ -n "$DASHSCOPE_API_KEY" ]; then
    if [ "$CUSTOM_ENDPOINT" = 1 ]; then
      ASR=BailianHttpASR; TTS=BailianHttpTTS
    else
      ASR=AliyunBLStreamASR; TTS=AliBLTTS; VLLM=QwenVLVLLM
    fi
  fi
else
  command -v docker >/dev/null 2>&1 || die "没有找到 docker。可用阿里云镜像源安装：
    curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
  装好后重新运行本脚本。"
  docker compose version >/dev/null 2>&1 || die "没有找到 docker compose 插件（需要 Docker 20.10+ 自带的 compose v2）。"

  say "准备后端镜像"
  docker pull -q "$BACKEND_IMAGE" >/dev/null || die "拉取后端镜像失败：$BACKEND_IMAGE"
  # 先停掉旧的后端：腾出内存给下面的探测，也避免它带着旧配置反复重启
  docker stop "$BACKEND" >/dev/null 2>&1 || true

  say "检查 API Key（只看结果，不打印 Key）"
  c=$(http_code -H "Authorization: Bearer $DEEPSEEK_API_KEY" https://api.deepseek.com/models)
  if [ "$c" = 200 ]; then echo "  DeepSeek 大模型：可用"; else echo "  DeepSeek 大模型：不可用（HTTP ${c:-无响应}）"; fi
  case "$c" in 401|403) KEY_PROBLEMS="$KEY_PROBLEMS DeepSeek" ;; esac

  if [ -n "$DASHSCOPE_API_KEY" ]; then
    echo "  百炼接入地址：$DASHSCOPE_BASE_URL"
    # 在后端镜像里把两套语音通路都真实跑一遍（合成拿到音频、识别正常结束才算可用）：
    #   流式通路有童声、延迟低，普通百炼 Key 可用；原生 HTTP 通路是 Token Plan 套餐用的
    probe=$(BL_KEY="$DASHSCOPE_API_KEY" BL_HOST="$BL_HOST" BL_WS_VOICE="$TTS_VOICE" BL_HTTP_VOICE="$QWEN_TTS_VOICE" \
            timeout 150 docker run --rm -i -e BL_KEY -e BL_HOST -e BL_WS_VOICE -e BL_HTTP_VOICE \
            --entrypoint python "$BACKEND_IMAGE" - < probe_bailian.py 2>/dev/null || true)
    pick() { local v; v=$(printf '%s\n' "$probe" | sed -n "s/^$1=//p"); printf '%s' "${v:-fail 探测没有返回结果}"; }
    r_ws_asr=$(pick ws_asr); r_ws_tts=$(pick ws_tts); r_http_asr=$(pick http_asr); r_http_tts=$(pick http_tts)
    c_llm=$(http_code -H "Authorization: Bearer $DASHSCOPE_API_KEY" "$DASHSCOPE_BASE_URL/models")
    echo "  流式识别 paraformer-realtime-v2：$(show "$r_ws_asr")"
    echo "  流式合成 cosyvoice-v2 / $TTS_VOICE：$(show "$r_ws_tts")"
    echo "  HTTP 识别 qwen-audio-3.0-asr-flash：$(show "$r_http_asr")"
    echo "  HTTP 合成 qwen-audio-3.0-tts-plus / $QWEN_TTS_VOICE：$(show "$r_http_tts")"
    if [ "$r_ws_asr" = ok ]; then ASR=AliyunBLStreamASR; elif [ "$r_http_asr" = ok ]; then ASR=BailianHttpASR; fi
    if [ "$r_ws_tts" = ok ]; then TTS=AliBLTTS; elif [ "$r_http_tts" = ok ]; then TTS=BailianHttpTTS; fi
    # 看图只在默认地址上换成通义；专属地址下有哪些模型不确定，保留 DeepSeek
    if [ "$c_llm" = 200 ] && [ "$CUSTOM_ENDPOINT" = 0 ]; then VLLM=QwenVLVLLM; fi
    if [ "$ASR" = FunASR ] && [ "$TTS" = EdgeTTS ]; then KEY_PROBLEMS="$KEY_PROBLEMS 阿里云百炼"; fi
  fi

  if [ "$ASR" = FunASR ]; then
    mem_mb=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)
    if [ "$mem_mb" -gt 0 ] && [ "$mem_mb" -lt "$MIN_FUNASR_MB" ]; then
      die "没有可用的语音识别方案：百炼识别不可用，而本地识别需要约 4G 内存，这台服务器只有 ${mem_mb}MB（硬启动会被系统反复杀掉）。
  可以：1) 换一把能用于语音识别的百炼 Key；2) 给服务器升级内存。
  旧的后端已停止，修正后重新运行 bash deploy.sh。"
    fi
  fi
fi

# 专属地址下，百炼识别需要给后端打一个一行的补丁（见 docker-compose.bailian-asr.yml）
PATCH_ASR=0
if [ "$ASR" = AliyunBLStreamASR ] && [ "$CUSTOM_ENDPOINT" = 1 ]; then PATCH_ASR=1; fi

describe() {
  case "$1" in
    AliyunBLStreamASR) echo "百炼 Paraformer 流式识别" ;;
    BailianHttpASR)    echo "百炼 Qwen-Audio 识别（HTTP）" ;;
    BailianHttpTTS)    echo "百炼 Qwen-Audio 合成（HTTP，音色 $QWEN_TTS_VOICE）" ;;
    FunASR)            echo "本地 FunASR（首次要下载 900MB 模型）" ;;
    AliBLTTS)          echo "百炼 CosyVoice 童声（$TTS_VOICE）" ;;
    EdgeTTS)           echo "EdgeTTS（免费，成人女声）" ;;
    QwenVLVLLM)        echo "通义千问" ;;
    DeepSeekVLLM)      echo "DeepSeek" ;;
  esac
}
say "本次使用的方案"
echo "  语音识别：$(describe "$ASR")"
echo "  语音合成：$(describe "$TTS")"
echo "  看图：$(describe "$VLLM")"

COMPOSE_FILE="docker-compose.yml"
[ "$ASR" = FunASR ] && COMPOSE_FILE="$COMPOSE_FILE:docker-compose.funasr.yml"
[ "$PATCH_ASR" = 1 ] && COMPOSE_FILE="$COMPOSE_FILE:docker-compose.bailian-asr.yml"
set_env COMPOSE_FILE "$COMPOSE_FILE"
export COMPOSE_FILE

# ---------- 渲染配置 ----------
say "生成 data/.config.yaml"
esc() { printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'; }
mkdir -p data music
# 天气：项目自带的共用 Key 已失效，只有填了自己的和风天气 Key 才启用，否则整段去掉
if [ -n "$QWEATHER_API_HOST" ] && [ -n "$QWEATHER_API_KEY" ]; then
  WEATHER="已启用"
  WEATHER_SED=(-e "s|__QWEATHER_API_HOST__|$(esc "$QWEATHER_API_HOST")|g" -e "s|__QWEATHER_API_KEY__|$(esc "$QWEATHER_API_KEY")|g" -e 's/ *# __WEATHER_ONLY__$//')
  PROMPT_SED=(-e '')
else
  WEATHER="未启用（.env 里没有和风天气 Key）"
  WEATHER_SED=(-e '/__WEATHER_ONLY__/d')
  PROMPT_SED=(-e '/{{weather_info}}/d' -e '/get_weather/d')
fi
echo "天气查询：$WEATHER"
(
  umask 077
  sed "${WEATHER_SED[@]}" \
      -e "s|__PUBLIC_HOST__|$(esc "$PUBLIC_HOST")|g" \
      -e "s|__GATEWAY_PORT__|$(esc "$GATEWAY_PORT")|g" \
      -e "s|__SECRET_PATH__|$(esc "$SECRET_PATH")|g" \
      -e "s|__AUTH_KEY__|$(esc "$AUTH_KEY")|g" \
      -e "s|__DEEPSEEK_API_KEY__|$(esc "$DEEPSEEK_API_KEY")|g" \
      -e "s|__DASHSCOPE_API_KEY__|$(esc "$DASHSCOPE_API_KEY")|g" \
      -e "s|__DASHSCOPE_BASE_URL__|$(esc "$DASHSCOPE_BASE_URL")|g" \
      -e "s|__DASHSCOPE_WS_URL__|$(esc "$DASHSCOPE_WS_URL")|g" \
      -e "s|__CHILD_NAME__|$(esc "$CHILD_NAME")|g" \
      -e "s|__TTS_VOICE__|$TTS_VOICE|g" \
      -e "s|__QWEN_TTS_VOICE__|$QWEN_TTS_VOICE|g" \
      -e "s|__BL_HTTP_ASR_URL__|$(esc "$BL_HTTP_ASR_URL")|g" \
      -e "s|__BL_HTTP_TTS_URL__|$(esc "$BL_HTTP_TTS_URL")|g" \
      -e "s|__ASR__|$ASR|g" -e "s|__TTS__|$TTS|g" -e "s|__VLLM__|$VLLM|g" \
      config.template.yaml > data/.config.yaml
)
sed "${PROMPT_SED[@]}" prompt/mercury-prompt-template.txt > data/mercury-prompt-template.txt
if grep -n -E '__[A-Z_]+__' data/.config.yaml; then die "配置里还有没替换掉的占位符（见上）。"; fi

OTA_URL="http://${PUBLIC_HOST}:${GATEWAY_PORT}/${SECRET_PATH}/xiaozhi/ota/"
if [ "$RENDER_ONLY" = 1 ]; then
  echo "渲染完成（--render-only，未启动任何服务）。"
  exit 0
fi

# ---------- 百炼识别的地址补丁 ----------
if [ "$PATCH_ASR" = 1 ]; then
  say "让百炼语音识别走专属接入地址"
  mkdir -p data/patches
  docker run --rm --entrypoint cat "$BACKEND_IMAGE" "$ASR_SOURCE" > data/patches/aliyunbl_stream.orig.py \
    || die "没能从后端镜像里取出识别模块。"
  sed -E 's|^( *)self\.ws_url = "(wss://dashscope\.aliyuncs\.com/api-ws/v1/inference)"|\1self.ws_url = config.get("ws_url") or "\2"|' \
    data/patches/aliyunbl_stream.orig.py > data/patches/aliyunbl_stream.py
  n=$(grep -c 'config.get("ws_url")' data/patches/aliyunbl_stream.py || true)
  [ "$n" = 1 ] || die "后端镜像里的识别模块和预期不一样（地址那一行没匹配上），补丁没有生效。请把这条信息发给维护者。"
  echo "  已生成 data/patches/aliyunbl_stream.py（只改了接入地址那一行）"
fi

# ---------- 本地识别模型 ----------
if [ "$ASR" = FunASR ]; then
  model=models/SenseVoiceSmall/model.pt
  [ -d "$model" ] && rmdir "$model"   # 之前没下模型就启动过的话，Docker 会建出一个同名空目录
  if [ ! -s "$model" ]; then
    say "下载语音识别模型 SenseVoiceSmall（约 900MB，支持断点续传）"
    mkdir -p "$(dirname "$model")"
    curl -L --fail -C - -o "$model.part" \
      "https://modelscope.cn/models/iic/SenseVoiceSmall/resolve/master/model.pt" \
      || die "模型下载失败，重新运行本脚本可以续传。"
    mv "$model.part" "$model"
  fi
fi

# ---------- 网关镜像（国内直连 Docker Hub 常常不通，依次尝试镜像站） ----------
if [ -z "$NGINX_IMAGE" ]; then
  say "准备 nginx 网关镜像"
  candidates="nginx:1.27-alpine docker.m.daocloud.io/library/nginx:1.27-alpine docker.nju.edu.cn/library/nginx:1.27-alpine"
  # 先看本机有没有现成的，没有再逐个去拉
  for img in $candidates; do
    if docker image inspect "$img" >/dev/null 2>&1; then NGINX_IMAGE=$img; break; fi
  done
  if [ -z "$NGINX_IMAGE" ]; then
    for img in $candidates; do
      if timeout 180 docker pull -q "$img" >/dev/null 2>&1; then NGINX_IMAGE=$img; break; fi
      echo "  拉取失败：$img"
    done
  fi
  [ -n "$NGINX_IMAGE" ] || die "拉不到 nginx 镜像。请给 Docker 配置镜像加速器后重试，或在 .env 里把 NGINX_IMAGE 设为你能拉到的 nginx 镜像地址。"
  set_env NGINX_IMAGE "$NGINX_IMAGE"
fi
echo "网关镜像：$NGINX_IMAGE"

# ---------- 启动 ----------
say "启动服务"
docker compose up -d --force-recreate --remove-orphans

say "等待服务就绪（最多三分钟）"
local_url="http://127.0.0.1:${GATEWAY_PORT}/${SECRET_PATH}/xiaozhi/ota/"
ok=""
for _ in $(seq 1 60); do
  if out=$(curl -fsS --max-time 3 "$local_url" 2>/dev/null); then ok=1; break; fi
  sleep 3
done
if [ -z "$ok" ]; then
  docker compose ps || true
  echo "----- 后端最近的日志 -----"
  docker logs --tail 40 "$BACKEND" 2>&1 || true
  die "三分钟内服务没有就绪（上面是后端最近的日志）。"
fi
echo "$out"

cat <<EOF

========================================================
 部署完成。

 阿里云安全组需要放行入方向 TCP ${GATEWAY_PORT}。设备访问的地址是：

    ${OTA_URL}

 用 firmware/build_firmware.py 编译的固件已经内置了这个地址；
 如果刷的是别的固件，在设备配网页面的「高级选项 / Custom OTA URL」里填它。
 地址里的那串随机字符就是访问密钥，不要发给别人。
 常用命令：
    docker logs -f ${BACKEND}     # 看对话日志
    bash deploy.sh                          # 改了 .env 或配置后重新部署
========================================================
EOF

if [ -n "$KEY_PROBLEMS" ]; then
  warn "以下服务的 Key 没有通过检查：$KEY_PROBLEMS"
  cat <<'EOF'
  DeepSeek 不通过：Mercury 无法回话，请核对 .env 里的 DEEPSEEK_API_KEY。
  百炼不通过：已经自动改用备用方案（见上面"本次使用的方案"）。
    想用百炼的话，到控制台核对 Key 和接入地址：https://bailian.console.aliyun.com/?apiKey=1#/api-key
    Token Plan / 业务空间的 Key 要在 .env 里填专属的 DASHSCOPE_BASE_URL。
  改完 .env 后重新运行 bash deploy.sh 即可。
EOF
fi
