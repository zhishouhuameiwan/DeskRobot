// 没有硬件时测试服务端整条链路：模拟设备连上网关，说一句话，看 Mercury 会不会回话。
// 用法（需要 Node 22+）：
//   node server/selftest.mjs              发送唤醒词"你好Mercury"
//   node server/selftest.mjs "你是谁呀"    发送任意一句话（跳过语音识别，直接当作识别结果）
// 会假装支持 MCP，服务器推给板子的成长状态（self.mercury.growth）会打印出来。
// 服务器地址和密钥路径从同目录的 .env 读取，不会打印出来。
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const env = Object.fromEntries(
  readFileSync(join(here, '.env'), 'utf8')
    .split(/\r?\n/)
    .map((l) => l.match(/^([A-Z_]+)=(.*)$/))
    .filter(Boolean)
    .map((m) => [m[1], m[2].trim()]),
);
for (const k of ['PUBLIC_HOST', 'SECRET_PATH']) {
  if (!env[k]) throw new Error(`server/.env 里缺少 ${k}`);
}
const url =
  `ws://${env.PUBLIC_HOST}:${env.GATEWAY_PORT || 18080}/${env.SECRET_PATH}/xiaozhi/v1/` +
  `?device-id=AA:BB:CC:00:00:01&client-id=mercury-selftest`;
const text = process.argv[2] ?? '你好Mercury';
const TIMEOUT_MS = 45_000;

const t0 = Date.now();
const at = () => `${((Date.now() - t0) / 1000).toFixed(1)}s`;
const result = { emotion: null, sentences: [], audioFrames: 0, audioBytes: 0, firstAudioAt: null };

const ws = new WebSocket(url);
ws.binaryType = 'arraybuffer';
const timer = setTimeout(() => finish(`超时（${TIMEOUT_MS / 1000} 秒内没有收到完整回复）`), TIMEOUT_MS);

function finish(problem) {
  clearTimeout(timer);
  try { ws.close(); } catch {}
  console.log('\n===== 结果 =====');
  console.log(`表情指令：${result.emotion ?? '（没有收到）'}`);
  console.log(`Mercury 说：${result.sentences.join('') || '（没有收到文字）'}`);
  console.log(`语音：${result.audioFrames} 帧，${result.audioBytes} 字节` + (result.firstAudioAt ? `，首帧在 ${result.firstAudioAt}` : ''));
  const ok = !problem && result.sentences.length > 0 && result.audioFrames > 0;
  console.log(ok ? '链路正常：大模型有回复，语音合成有音频。' : `有问题：${problem ?? '回复不完整'}`);
  process.exit(ok ? 0 : 1);
}

ws.onopen = () => {
  console.log(`[${at()}] 已连接，发送 hello`);
  ws.send(JSON.stringify({
    type: 'hello',
    version: 1,
    transport: 'websocket',
    features: { mcp: true },
    audio_params: { format: 'opus', sample_rate: 16000, channels: 1, frame_duration: 60 },
  }));
};
ws.onerror = () => finish('WebSocket 连接出错（端口没放行、密钥路径不对，或服务没启动）');
ws.onclose = (e) => { if (!result.sentences.length) finish(`连接被关闭（code ${e.code}）`); };
ws.onmessage = (ev) => {
  if (typeof ev.data !== 'string') {
    result.audioFrames += 1;
    result.audioBytes += ev.data.byteLength;
    result.firstAudioAt ??= at();
    return;
  }
  let msg;
  try { msg = JSON.parse(ev.data); } catch { return; }
  if (msg.type === 'hello') {
    console.log(`[${at()}] 服务器应答 hello，发送一句话："${text}"`);
    ws.send(JSON.stringify({ session_id: msg.session_id, type: 'listen', state: 'detect', text }));
  } else if (msg.type === 'stt') {
    console.log(`[${at()}] 服务器把输入当作：${msg.text}`);
  } else if (msg.type === 'llm') {
    result.emotion = `${msg.text ?? ''} ${msg.emotion ?? ''}`.trim();
    console.log(`[${at()}] 表情：${result.emotion}`);
  } else if (msg.type === 'tts') {
    if (msg.state === 'sentence_start' && msg.text) {
      result.sentences.push(msg.text);
      console.log(`[${at()}] 说：${msg.text}`);
    } else if (msg.state === 'stop') {
      console.log(`[${at()}] 说完了`);
      finish();
    } else {
      console.log(`[${at()}] 语音合成状态：${msg.state}`);
    }
  } else if (msg.type === 'mcp') {
    onMcp(msg.payload ?? {});
  } else {
    console.log(`[${at()}] 其他消息：${ev.data.slice(0, 160)}`);
  }
};

// 假装自己是板子上的 MCP：回应初始化和工具列表，打印服务器推过来的成长状态（养成，见 plugins/mercury_growth.py）
function onMcp(p) {
  const reply = (result) => ws.send(JSON.stringify({ type: 'mcp', payload: { jsonrpc: '2.0', id: p.id, result } }));
  if (p.method === 'initialize') {
    reply({ protocolVersion: '2024-11-05', capabilities: { tools: {} }, serverInfo: { name: 'mercury-selftest', version: '1' } });
  } else if (p.method === 'tools/list') {
    reply({ tools: [] });
  } else if (p.method === 'tools/call') {
    console.log(`[${at()}] 板子收到：${p.params?.name} ${JSON.stringify(p.params?.arguments ?? {})}`);
    reply({ content: [{ type: 'text', text: 'true' }], isError: false });
  }
}
