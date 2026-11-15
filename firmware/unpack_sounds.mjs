// 把 make_sounds.py 输出的 JSON 行解成 firmware/sounds/<名字>.ogg。用法见 make_sounds.py 开头。
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const input = process.argv[2];
if (!input) {
  console.error('用法：node firmware/unpack_sounds.mjs <sounds.jsonl>');
  process.exit(1);
}
const outDir = join(dirname(fileURLToPath(import.meta.url)), 'sounds');
mkdirSync(outDir, { recursive: true });
const lines = readFileSync(input, 'utf8').split('\n').filter((l) => l.trim());
if (lines.length === 0) {
  console.error(`${input} 是空的，合成没有成功`);
  process.exit(1);
}
for (const line of lines) {
  const { name, text, ms, ogg } = JSON.parse(line);
  const data = Buffer.from(ogg, 'base64');
  if (data.subarray(0, 4).toString() !== 'OggS') {
    console.error(`${name} 不是 Ogg 文件`);
    process.exit(1);
  }
  writeFileSync(join(outDir, `${name}.ogg`), data);
  console.log(`${name}.ogg  ${String(data.length).padStart(5)} 字节  ${ms}ms  ${text}`);
}
