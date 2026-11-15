// 温度计宠物 Mercury 的表情素材生成器。
// 形态（phase）是整套形象，每套都有全部 21 个表情：
//   mercury（默认）：按家长提供的参考图画的 Mercury，水银管高度随心情变化
//   glass / warm / frost / star / rainbow：原创的"水银球脸"形象及其换装
//
// 用法：node gen-faces.mjs [横屏用的输出尺寸，默认 160]
// 产物：out/<形态>/png/<表情>.png（横屏用）、out/<形态>/png-portrait/<表情>.png（竖屏用，224px）、
//       out/<形态>/svg/<表情>.svg、out/sheet-<形态>.png、out/phases.png
// 表情文件名必须是下面 EMOTIONS 里的 21 个名字——固件和服务端只认这些。
// 想换成自己画的形象：把同名 PNG（透明底、统一尺寸）放进一个目录，交给固件打包即可。

import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const INK = '#27324A';
const MOUTH_DARK = '#7A1F2B';
const TONGUE = '#FF8FA3';
const stroke = (w = 6) =>
  `fill="none" stroke="${INK}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"`;

// ---------- 眼睛 ----------
const EYES = {
  dot: (x, y) =>
    `<circle cx="${x}" cy="${y}" r="9" fill="${INK}"/><circle cx="${x + 3}" cy="${y - 3}" r="3" fill="#fff"/>`,
  happy: (x, y) => `<path d="M${x - 11} ${y + 4} Q${x} ${y - 12} ${x + 11} ${y + 4}" ${stroke()}/>`,
  closed: (x, y) => `<path d="M${x - 11} ${y - 2} Q${x} ${y + 9} ${x + 11} ${y - 2}" ${stroke()}/>`,
  wide: (x, y) =>
    `<circle cx="${x}" cy="${y}" r="13" fill="#fff" stroke="${INK}" stroke-width="4"/><circle cx="${x}" cy="${y}" r="5" fill="${INK}"/>`,
  tiny: (x, y) =>
    `<circle cx="${x}" cy="${y}" r="13" fill="#fff" stroke="${INK}" stroke-width="4"/><circle cx="${x}" cy="${y}" r="2.5" fill="${INK}"/>`,
  heart: (x, y, tint) => heart(x, y, 12, tint ?? '#fff'),
  gt: (x, y) => `<path d="M${x - 8} ${y - 9} L${x + 8} ${y} L${x - 8} ${y + 9}" ${stroke()}/>`,
  lt: (x, y) => `<path d="M${x + 8} ${y - 9} L${x - 8} ${y} L${x + 8} ${y + 9}" ${stroke()}/>`,
  up: (x, y) =>
    `<circle cx="${x + 3}" cy="${y - 4}" r="9" fill="${INK}"/><circle cx="${x + 6}" cy="${y - 7}" r="3" fill="#fff"/>`,
};
// 眉毛：dir=1 表示向中间压低（生气），dir=-1 表示向中间抬高（委屈）
const brow = (x, y, side, dir) => {
  const inner = x + side * -10;
  const outer = x + side * 12;
  return `<path d="M${outer} ${y - 15 - dir * 4} L${inner} ${y - 15 + dir * 4}" ${stroke(5)}/>`;
};

// ---------- 嘴巴（中心 MX,MY）----------
const MX = 120;
const MY = 172;
const MOUTHS = {
  smile: `<path d="M${MX - 14} ${MY - 2} Q${MX} ${MY + 14} ${MX + 14} ${MY - 2}" ${stroke()}/>`,
  open:
    `<path d="M${MX - 18} ${MY - 4} Q${MX} ${MY + 28} ${MX + 18} ${MY - 4} Z" fill="${MOUTH_DARK}" stroke="${INK}" stroke-width="4" stroke-linejoin="round"/>` +
    `<path d="M${MX - 9} ${MY + 9} Q${MX} ${MY + 3} ${MX + 9} ${MY + 9} Q${MX} ${MY + 17} ${MX - 9} ${MY + 9} Z" fill="${TONGUE}"/>`,
  o: `<circle cx="${MX}" cy="${MY + 3}" r="7" fill="${MOUTH_DARK}" stroke="${INK}" stroke-width="4"/>`,
  bigo: `<ellipse cx="${MX}" cy="${MY + 5}" rx="11" ry="15" fill="${MOUTH_DARK}" stroke="${INK}" stroke-width="4"/>`,
  flat: `<path d="M${MX - 10} ${MY + 3} H${MX + 10}" ${stroke()}/>`,
  frown: `<path d="M${MX - 13} ${MY + 9} Q${MX} ${MY - 5} ${MX + 13} ${MY + 9}" ${stroke()}/>`,
  wavy: `<path d="M${MX - 15} ${MY + 4} q5 -8 10 0 t10 0 t10 0" ${stroke(5)}/>`,
  kiss: `<path d="M${MX - 3} ${MY - 6} q10 4 0 8 q10 4 0 8" ${stroke(5)}/>`,
  tongue:
    `<path d="M${MX - 14} ${MY - 2} Q${MX} ${MY + 14} ${MX + 14} ${MY - 2}" ${stroke()}/>` +
    `<path d="M${MX - 3} ${MY + 5} q-1 15 8 14 q8 -2 5 -15 Z" fill="${TONGUE}" stroke="${INK}" stroke-width="3" stroke-linejoin="round"/>`,
  teeth:
    `<rect x="${MX - 16}" y="${MY - 4}" width="32" height="14" rx="5" fill="#fff" stroke="${INK}" stroke-width="4"/>` +
    `<path d="M${MX - 5} ${MY - 4} v14 M${MX + 5} ${MY - 4} v14" ${stroke(3)}/>`,
  smirk: `<path d="M${MX - 12} ${MY + 3} Q${MX + 2} ${MY + 11} ${MX + 15} ${MY - 5}" ${stroke()}/>`,
  wail: `<path d="M${MX - 14} ${MY + 14} Q${MX} ${MY - 14} ${MX + 14} ${MY + 14} Z" fill="${MOUTH_DARK}" stroke="${INK}" stroke-width="4" stroke-linejoin="round"/>`,
  yum:
    `<path d="M${MX - 14} ${MY - 2} Q${MX} ${MY + 14} ${MX + 14} ${MY - 2}" ${stroke()}/>` +
    `<ellipse cx="${MX + 11}" cy="${MY + 7}" rx="6" ry="5" fill="${TONGUE}" stroke="${INK}" stroke-width="3"/>`,
};

// ---------- 小道具 ----------
function heart(x, y, s, fill, extra = '') {
  return `<path d="M${x} ${y + s * 0.9} C${x - s * 1.4} ${y - s * 0.1} ${x - s * 0.7} ${y - s * 1.2} ${x} ${y - s * 0.4} C${x + s * 0.7} ${y - s * 1.2} ${x + s * 1.4} ${y - s * 0.1} ${x} ${y + s * 0.9} Z" fill="${fill}" ${extra}/>`;
}
const zed = (x, y, s) => `<path d="M${x} ${y} h${s} l${-s} ${s} h${s}" ${stroke(Math.max(3, s / 3))}/>`;
const sparkle = (x, y, s, fill = '#FFD93B') => {
  const k = s * 0.25;
  return `<path d="M${x} ${y - s} L${x + k} ${y - k} L${x + s} ${y} L${x + k} ${y + k} L${x} ${y + s} L${x - k} ${y + k} L${x - s} ${y} L${x - k} ${y - k} Z" fill="${fill}" stroke="${INK}" stroke-width="2.5" stroke-linejoin="round"/>`;
};
const drop = (x, y, s = 1) =>
  `<path d="M${x} ${y - 12 * s} q${9 * s} ${12 * s} 0 ${18 * s} q${-9 * s} ${-6 * s} 0 ${-18 * s} Z" fill="#8FD3FF" stroke="${INK}" stroke-width="3" stroke-linejoin="round"/>`;
const EXTRAS = {
  steam:
    `<g fill="#fff" stroke="${INK}" stroke-width="3"><circle cx="72" cy="36" r="10"/><circle cx="60" cy="20" r="6.5"/>` +
    `<circle cx="168" cy="36" r="10"/><circle cx="180" cy="20" r="6.5"/></g>`,
  zzz: zed(168, 66, 15) + zed(190, 42, 11) + zed(206, 24, 8),
  hearts:
    heart(182, 58, 10, '#FF6FA3', `stroke="${INK}" stroke-width="2.5"`) +
    heart(56, 72, 7, '#FF6FA3', `stroke="${INK}" stroke-width="2.5"`) +
    heart(200, 92, 6, '#FF9FC0', `stroke="${INK}" stroke-width="2.5"`),
  sweat: drop(176, 118),
  tears:
    `<g fill="#BFE6FF" stroke="${INK}" stroke-width="3"><rect x="91" y="154" width="14" height="46" rx="7"/><rect x="135" y="154" width="14" height="46" rx="7"/></g>`,
  tear: drop(150, 172, 0.7),
  question:
    `<path d="M170 54 q0 -14 12 -14 q12 0 12 11 q0 8 -11 13 v8" ${stroke()}/><circle cx="183" cy="86" r="4" fill="${INK}"/>`,
  exclaim: `<path d="M184 30 v26" ${stroke(7)}/><circle cx="184" cy="70" r="4.5" fill="${INK}"/>`,
  exclaim2:
    `<path d="M178 30 v26 M196 30 v26" ${stroke(7)}/><circle cx="178" cy="70" r="4.5" fill="${INK}"/><circle cx="196" cy="70" r="4.5" fill="${INK}"/>`,
  dots:
    `<g fill="#fff" stroke="${INK}" stroke-width="3"><circle cx="170" cy="86" r="4.5"/><circle cx="184" cy="68" r="6.5"/><circle cx="204" cy="44" r="10"/></g>`,
  note:
    `<ellipse cx="178" cy="78" rx="8" ry="6" transform="rotate(-20 178 78)" fill="${INK}"/><path d="M185 76 V46 q12 2 14 14" ${stroke(5)}/>`,
  sparkles: sparkle(182, 58, 12) + sparkle(54, 78, 8),
  shades:
    `<g fill="${INK}" stroke="${INK}" stroke-width="4" stroke-linejoin="round"><rect x="80" y="134" width="34" height="22" rx="8"/><rect x="126" y="134" width="34" height="22" rx="8"/></g>` +
    `<path d="M114 140 H126 M80 140 L66 134 M160 140 L174 134" ${stroke(4)}/>` +
    `<path d="M88 140 l6 8 M134 140 l6 8" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/>`,
};

// ---------- 手臂 ----------
const ARMS = {
  down: `<path d="M62 162 Q46 168 44 184 M178 162 Q194 168 196 184" ${stroke(9)}/>`,
  up: `<path d="M64 150 Q44 140 40 118 M176 150 Q196 140 200 118" ${stroke(9)}/>`,
  hips: `<path d="M62 158 Q36 170 58 190 M178 158 Q204 170 182 190" ${stroke(9)}/>`,
  wave: `<path d="M62 162 Q46 168 44 184 M176 150 Q196 140 204 120" ${stroke(9)}/>`,
};

// ---------- 形态（phase）：整套换装 ----------
const hex2rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const mix = (a, b, t) => {
  const [ra, rb] = [hex2rgb(a), hex2rgb(b)];
  return '#' + ra.map((v, i) => Math.round(v + (rb[i] - v) * t).toString(16).padStart(2, '0')).join('');
};
const snow = (x, y, s) =>
  `<path d="M${x - s} ${y} h${2 * s} M${x - s * 0.5} ${y - s * 0.87} l${s} ${s * 1.74} M${x + s * 0.5} ${y - s * 0.87} l${-s} ${s * 1.74}" fill="none" stroke="#7CCBFF" stroke-width="3.5" stroke-linecap="round"/>`;
const confetti = (x, y, r, fill) =>
  `<rect x="${x - 5}" y="${y - 3}" width="10" height="6" rx="2" transform="rotate(${r} ${x} ${y})" fill="${fill}" stroke="${INK}" stroke-width="2"/>`;

export const PHASES = {
  // 默认形态：按家长提供的参考图画的 Mercury（圆脑袋、蓝条纹围巾、带刻度的身体、红色水银管）。
  // 这是同人性质的家用素材；如果要把项目或图片公开发布，请先征得原角色作者同意，或换用下面的原创形态。
  mercury: { title: 'Mercury', layout: 'ref' },
  // 原创形态之一：磨砂玻璃的身体，红色水银只在管子里，围一条小围巾。
  // 身体不再整体变色，心情色体现在水银柱、腮红和身体里的一圈光晕上。
  glass: {
    title: '玻璃',
    tint: (c) => c,
    pale: '#EEF0FA',
    over:
      `<path d="M88 106 L70 128 L83 136 L100 110 Z" fill="#5CC8A8" stroke="${INK}" stroke-width="5" stroke-linejoin="round"/>` +
      `<path d="M73 129 l-4 6 M79 133 l-4 6" ${stroke(3)}/>` +
      `<path d="M88 92 Q120 103 152 92 L155 108 Q120 120 85 108 Z" fill="#5CC8A8" stroke="${INK}" stroke-width="5" stroke-linejoin="round"/>` +
      `<path d="M89 100 Q120 111 152 100" fill="none" stroke="#FFF4D6" stroke-width="4" stroke-linecap="round"/>`,
  },
  // 暖暖形态：整个身体就是心情色
  warm: { title: '暖暖', tint: (c) => c },
  // 冰雪形态：整体偏冰蓝，管顶积了一小团雪
  frost: {
    title: '冰雪',
    tint: (c) => mix(c, '#A9DFFF', 0.78),
    hat: `<path d="M94 24 q-4 -22 26 -22 q30 0 26 22 q-8 6 -14 0 q-6 7 -12 0 q-6 7 -12 0 q-6 6 -14 0 Z" fill="#fff" stroke="${INK}" stroke-width="5" stroke-linejoin="round"/>`,
    deco: snow(22, 30, 9) + snow(20, 124, 6) + snow(216, 208, 8) + snow(26, 210, 6),
  },
  // 星夜形态：偏紫蓝，戴小睡帽，适合睡前
  star: {
    title: '星夜',
    tint: (c) => mix(c, '#7C6CF2', 0.5),
    hat:
      `<path d="M98 20 Q110 -16 150 0 Q160 5 159 13 Q147 8 142 20 Z" fill="#5B4BD6" stroke="${INK}" stroke-width="5" stroke-linejoin="round"/>` +
      `<rect x="92" y="16" width="56" height="11" rx="5.5" fill="#fff" stroke="${INK}" stroke-width="5"/>` +
      `<circle cx="160" cy="15" r="6" fill="#fff" stroke="${INK}" stroke-width="4"/>`,
    deco:
      sparkle(22, 30, 8, '#FFE680') + sparkle(20, 124, 5, '#FFE680') + sparkle(216, 208, 7, '#FFE680') +
      `<path d="M30 198 a11 11 0 1 0 10 16 a9 9 0 1 1 -10 -16 Z" fill="#FFE680" stroke="${INK}" stroke-width="2.5" stroke-linejoin="round"/>`,
  },
  // 彩虹派对形态：彩虹水银 + 派对帽
  rainbow: {
    title: '彩虹派对',
    tint: (c) => c,
    gradient: ['#FF6B6B', '#FFB03B', '#FFE14D', '#7ED957', '#4DB8FF', '#B58CFF'],
    hat:
      `<path d="M100 22 L120 -7 L140 22 Z" fill="#FFD93B" stroke="${INK}" stroke-width="5" stroke-linejoin="round"/>` +
      `<path d="M112 8 L131 12 M106 17 L137 20" fill="none" stroke="#FF6FA3" stroke-width="4" stroke-linecap="round"/>` +
      `<circle cx="120" cy="-8" r="5.5" fill="#FF6FA3" stroke="${INK}" stroke-width="4"/>`,
    deco:
      confetti(22, 30, 25, '#FF6FA3') + confetti(20, 124, -30, '#4DB8FF') + confetti(216, 208, 40, '#FFD93B') +
      confetti(28, 210, -15, '#7ED957') + confetti(218, 128, 10, '#B58CFF'),
  },
};

// ---------- 表情表：颜色 = 心情色，level = 水银高度(0~1) ----------
// 名称与小智固件/服务端使用的 21 个 emotion 一一对应。
export const EMOTIONS = {
  neutral: { color: '#FF7A6B', level: 0.5, eyes: ['dot', 'dot'], mouth: 'smile', arms: 'down' },
  happy: { color: '#FF6B5E', level: 0.72, eyes: ['happy', 'happy'], mouth: 'open', arms: 'up' },
  laughing: { color: '#FF5A4D', level: 0.88, eyes: ['gt', 'lt'], mouth: 'open', arms: 'up' },
  funny: { color: '#FF8A4D', level: 0.75, eyes: ['happy', 'dot'], mouth: 'tongue', arms: 'wave', extras: ['note'] },
  sad: { color: '#6BA8FF', level: 0.2, eyes: ['dot', 'dot'], brows: -1, mouth: 'frown', arms: 'down', extras: ['tear'] },
  angry: { color: '#F23C3C', level: 1, eyes: ['dot', 'dot'], brows: 1, mouth: 'teeth', arms: 'hips', extras: ['steam'] },
  crying: { color: '#5B9BFF', level: 0.1, eyes: ['closed', 'closed'], brows: -1, mouth: 'wail', arms: 'down', extras: ['tears'] },
  loving: { color: '#FF6FA3', level: 0.82, eyes: ['heart', 'heart'], mouth: 'smile', arms: 'up', extras: ['hearts'] },
  embarrassed: { color: '#FF8FA0', level: 0.65, eyes: ['closed', 'closed'], mouth: 'wavy', arms: 'down', extras: ['sweat'], blush: 1 },
  surprised: { color: '#FFB03B', level: 0.9, eyes: ['wide', 'wide'], mouth: 'o', arms: 'up', extras: ['exclaim'] },
  shocked: { color: '#B58CFF', level: 0.96, eyes: ['tiny', 'tiny'], mouth: 'bigo', arms: 'up', extras: ['exclaim2'] },
  thinking: { color: '#5CC8C0', level: 0.45, eyes: ['up', 'up'], mouth: 'flat', arms: 'down', extras: ['dots'] },
  winking: { color: '#FF7A6B', level: 0.65, eyes: ['dot', 'happy'], mouth: 'smile', arms: 'wave', extras: ['sparkles'] },
  cool: { color: '#4DB8FF', level: 0.55, eyes: [null, null], mouth: 'smirk', arms: 'hips', extras: ['shades'] },
  relaxed: { color: '#7ED6A5', level: 0.4, eyes: ['closed', 'closed'], mouth: 'smile', arms: 'down', extras: ['note'] },
  delicious: { color: '#FF9F45', level: 0.7, eyes: ['happy', 'happy'], mouth: 'yum', arms: 'up' },
  kissy: { color: '#FF7BAC', level: 0.75, eyes: ['closed', 'happy'], mouth: 'kiss', arms: 'down', extras: ['hearts'] },
  confident: { color: '#FF6B5E', level: 0.8, eyes: ['dot', 'dot'], brows: 1, mouth: 'smirk', arms: 'hips', extras: ['sparkles'] },
  sleepy: { color: '#9FB4D9', level: 0.15, eyes: ['closed', 'closed'], mouth: 'o', arms: 'down', extras: ['zzz'] },
  silly: { color: '#FFA24D', level: 0.7, eyes: ['wide', 'gt'], mouth: 'tongue', arms: 'up' },
  confused: { color: '#C7A6FF', level: 0.5, eyes: ['dot', 'wide'], mouth: 'wavy', arms: 'down', extras: ['question'] },
};

// ====================== 参考图布局（mercury 形态） ======================
// 头在上：白色外圈 + 淡紫灰的脸 + 一对大黑眼；脖子围蓝条纹围巾；
// 身体是带刻度的白色梯形，中间一根红色水银管，水银高度随心情变化。
const LID = '#B7B4D4';
const PUPIL = '#0E0E12';
const EYE_R = 24;
const EYE_L = 95;
const EYE_RX = 145;
const EYE_Y = 86;

// 眼睛。spec 为字符串时是闭眼/符号眼；为对象时是睁开的大眼睛：
//   { lid: 'low'|'top'|'heavy'|'angry'|'sad', pr: 瞳孔半径, dx, dy: 瞳孔偏移, type: 'heart' }
function refEye(cx, cy, spec, side, uid) {
  if (spec === 'arcUp') return `<path d="M${cx - 19} ${cy + 7} Q${cx} ${cy - 16} ${cx + 19} ${cy + 7}" ${stroke(6)}/>`;
  if (spec === 'arcDown') return `<path d="M${cx - 19} ${cy - 3} Q${cx} ${cy + 16} ${cx + 19} ${cy - 3}" ${stroke(6)}/>`;
  if (spec === 'gt') return `<path d="M${cx - 13} ${cy - 15} L${cx + 13} ${cy} L${cx - 13} ${cy + 15}" ${stroke(6)}/>`;
  if (spec === 'lt') return `<path d="M${cx + 13} ${cy - 15} L${cx - 13} ${cy} L${cx + 13} ${cy + 15}" ${stroke(6)}/>`;
  const t = spec ?? {};
  const id = `eye-${uid}-${side < 0 ? 'l' : 'r'}`;
  const L = cx - 30;
  const R = cx + 30;
  // 靠近鼻梁一侧（inner）和外侧（outer）的眼睑高度，用来画生气/委屈的斜眼睑
  const slant = (innerY, outerY) => {
    const [yl, yr] = side < 0 ? [outerY, innerY] : [innerY, outerY];
    return `M${L} ${cy - 30} H${R} V${yr} L${L} ${yl} Z`;
  };
  const lids = {
    low: `M${L} ${cy + 12} Q${cx} ${cy - 2} ${R} ${cy + 12} V${cy + 30} H${L} Z`,
    top: `M${L} ${cy - 30} H${R} V${cy - 7} Q${cx} ${cy + 2} ${L} ${cy - 7} Z`,
    heavy: `M${L} ${cy - 30} H${R} V${cy + 5} Q${cx} ${cy + 14} ${L} ${cy + 5} Z`,
    angry: slant(cy - 2, cy - 21),
    sad: slant(cy - 21, cy - 2),
  };
  let s = `<circle cx="${cx}" cy="${cy}" r="${EYE_R}" fill="#fff" stroke="${INK}" stroke-width="4"/>`;
  s += `<clipPath id="${id}"><circle cx="${cx}" cy="${cy}" r="${EYE_R - 2}"/></clipPath><g clip-path="url(#${id})">`;
  s += t.type === 'heart'
    ? heart(cx, cy + 1, 13, '#FF5A8A')
    : `<circle cx="${cx + (t.dx ?? 0)}" cy="${cy + (t.dy ?? 0)}" r="${t.pr ?? 16}" fill="${PUPIL}"/>`;
  if (lids[t.lid]) s += `<path d="${lids[t.lid]}" fill="${LID}" stroke="${INK}" stroke-width="3" stroke-linejoin="round"/>`;
  return s + '</g>';
}

// 眉毛：side=-1 左眼，1 右眼。外端 / 内端 / 中间控制点的高度决定神态
function refBrow(cx, cy, side, kind) {
  const h = { soft: [31, 32, 37], angry: [35, 28, 35], sad: [29, 36, 37], raised: [34, 34, 42] }[kind];
  if (!h) return '';
  const [outer, inner, mid] = h;
  return `<path d="M${cx + side * 11} ${cy - outer} Q${cx} ${cy - mid} ${cx - side * 11} ${cy - inner}" ${stroke(3.5)}/>`;
}

const REF_MOUTHS = {
  refsmile: `<path d="M109 118 Q120 134 131 118 Z" fill="${PUPIL}" stroke="${INK}" stroke-width="3" stroke-linejoin="round"/>`,
  reffrown: `<path d="M109 127 Q120 115 131 127" ${stroke(5)}/>`,
};
const outline = `stroke="${INK}" stroke-width="2.5"`;
const REF_EXTRAS = {
  steam:
    `<g fill="#fff" stroke="${INK}" stroke-width="3"><circle cx="32" cy="32" r="10"/><circle cx="20" cy="16" r="6.5"/>` +
    `<circle cx="208" cy="32" r="10"/><circle cx="220" cy="16" r="6.5"/></g>`,
  zzz: zed(194, 40, 14) + zed(210, 22, 10) + zed(222, 8, 7),
  hearts: heart(206, 30, 10, '#FF6FA3', outline) + heart(224, 60, 6, '#FF9FC0', outline) + heart(30, 40, 7, '#FF6FA3', outline),
  sweat: drop(160, 50, 0.8),
  tears:
    `<g fill="#BFE6FF" stroke="${INK}" stroke-width="3"><rect x="89" y="96" width="12" height="34" rx="6"/><rect x="139" y="96" width="12" height="34" rx="6"/></g>`,
  tear: drop(153, 121, 0.7),
  question: `<path d="M196 24 q0 -14 12 -14 q12 0 12 11 q0 8 -11 13 v8" ${stroke()}/><circle cx="209" cy="56" r="4" fill="${INK}"/>`,
  exclaim: `<path d="M208 8 v26" ${stroke(7)}/><circle cx="208" cy="48" r="4.5" fill="${INK}"/>`,
  exclaim2:
    `<path d="M202 8 v26 M220 8 v26" ${stroke(7)}/><circle cx="202" cy="48" r="4.5" fill="${INK}"/><circle cx="220" cy="48" r="4.5" fill="${INK}"/>`,
  dots:
    `<g fill="#fff" stroke="${INK}" stroke-width="3"><circle cx="192" cy="46" r="4.5"/><circle cx="204" cy="30" r="6.5"/><circle cx="220" cy="14" r="9"/></g>`,
  note:
    `<ellipse cx="204" cy="46" rx="8" ry="6" transform="rotate(-20 204 46)" fill="${INK}"/><path d="M211 44 V14 q12 2 14 14" ${stroke(5)}/>`,
  sparkles: sparkle(206, 28, 12) + sparkle(30, 44, 8),
  shades:
    `<g fill="${INK}" stroke="${INK}" stroke-width="4" stroke-linejoin="round"><rect x="72" y="72" width="46" height="29" rx="10"/><rect x="122" y="72" width="46" height="29" rx="10"/></g>` +
    `<path d="M118 80 H122 M72 80 L66 76 M168 80 L174 76" ${stroke(4)}/>` +
    `<path d="M82 79 l7 9 M132 79 l7 9" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/>`,
};

// 21 个表情在参考图布局下的画法。eyes: [左, 右]；brow 可以是一个名字或 [左, 右]
const REF_FACES = {
  neutral: { eyes: [{ lid: 'low' }, { lid: 'low' }], brow: 'soft', mouth: 'refsmile', level: 0.45 },
  happy: { eyes: ['arcUp', 'arcUp'], brow: 'soft', mouth: 'open', level: 0.72, blush: 0.6 },
  laughing: { eyes: ['gt', 'lt'], mouth: 'open', level: 0.88, blush: 0.6 },
  funny: { eyes: ['arcUp', { lid: 'low' }], brow: 'soft', mouth: 'tongue', level: 0.75, extras: ['note'] },
  sad: { eyes: [{ lid: 'sad', dy: 3 }, { lid: 'sad', dy: 3 }], brow: 'sad', mouth: 'reffrown', level: 0.2, extras: ['tear'] },
  angry: { eyes: [{ lid: 'angry' }, { lid: 'angry' }], brow: 'angry', mouth: 'reffrown', level: 1, extras: ['steam'] },
  crying: { eyes: ['arcDown', 'arcDown'], brow: 'sad', mouth: 'wail', level: 0.1, extras: ['tears'] },
  loving: { eyes: [{ type: 'heart' }, { type: 'heart' }], mouth: 'smile', level: 0.82, blush: 0.8, extras: ['hearts'] },
  embarrassed: { eyes: [{ lid: 'low', dx: 5 }, { lid: 'low', dx: 5 }], brow: 'sad', mouth: 'wavy', level: 0.65, blush: 0.95, extras: ['sweat'] },
  surprised: { eyes: [{ pr: 9 }, { pr: 9 }], brow: 'raised', mouth: 'o', level: 0.9, extras: ['exclaim'] },
  shocked: { eyes: [{ pr: 4 }, { pr: 4 }], brow: 'raised', mouth: 'bigo', level: 0.96, extras: ['exclaim2'] },
  thinking: { eyes: [{ pr: 12, dx: 6, dy: -6 }, { pr: 12, dx: 6, dy: -6 }], brow: 'raised', mouth: 'flat', level: 0.45, extras: ['dots'] },
  winking: { eyes: [{ lid: 'low' }, 'arcUp'], brow: 'soft', mouth: 'smile', level: 0.65, extras: ['sparkles'] },
  cool: { eyes: [null, null], mouth: 'smirk', level: 0.55, extras: ['shades'] },
  relaxed: { eyes: ['arcDown', 'arcDown'], mouth: 'smile', level: 0.4, extras: ['note'] },
  delicious: { eyes: ['arcUp', 'arcUp'], mouth: 'yum', level: 0.7, blush: 0.6 },
  kissy: { eyes: ['arcDown', 'arcUp'], mouth: 'kiss', level: 0.75, blush: 0.8, extras: ['hearts'] },
  confident: { eyes: [{ lid: 'angry' }, { lid: 'angry' }], brow: 'angry', mouth: 'smirk', level: 0.8, extras: ['sparkles'] },
  sleepy: { eyes: [{ lid: 'heavy' }, { lid: 'heavy' }], mouth: 'o', level: 0.15, extras: ['zzz'] },
  silly: { eyes: [{ pr: 9, dx: 7 }, 'gt'], mouth: 'tongue', level: 0.7 },
  confused: { eyes: [{ pr: 13 }, { pr: 8 }], brow: ['raised', 'sad'], mouth: 'wavy', level: 0.5, extras: ['question'] },
};

// tube: 'level' 按表情画水银柱（预览图、svg 用）；'empty' 只画空玻璃管——给固件用，
// 固件按"今天的心情温度"自己把水银柱画上去（见 firmware/board/mercury_display.h）
function refInner(name, phase, tube = 'level') {
  const f = REF_FACES[name];
  const uid = `${phase}-${name}`;
  const RED = '#F5333F';
  const GLASS = '#DDDDF0';
  const stripes = (id, angle) =>
    `<pattern id="${id}-${uid}" width="30" height="30" patternUnits="userSpaceOnUse" patternTransform="rotate(${angle})">` +
    `<rect width="30" height="30" fill="#A8F0FF"/><rect width="30" height="15" fill="#1593FF"/></pattern>`;
  const scarfPart = (id, d) =>
    `<path d="${d}" fill="url(#${id}-${uid})" stroke="${INK}" stroke-width="4" stroke-linejoin="round"/>`;
  const p = [stripes('sa', 30), stripes('sb', 43), stripes('sc', 82)];

  // 身体 + 两侧刻度
  p.push(`<path d="M88 146 L152 146 L170 230 L70 230 Z" fill="#fff" stroke="${INK}" stroke-width="5" stroke-linejoin="round"/>`);
  const ticks = [176, 188, 200, 212, 222]
    .map((y, i) => {
      const inset = ((y - 146) * 18) / 84;
      const len = i % 2 ? 8 : 13;
      return `M${88 - inset} ${y} h${len} M${152 + inset} ${y} h${-len}`;
    })
    .join(' ');
  p.push(`<path d="${ticks}" fill="none" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>`);
  // 水银管：高度 = 心情温度
  const top = 200 - f.level * 30;
  p.push(`<rect x="113" y="160" width="14" height="48" rx="7" fill="${GLASS}" stroke="${INK}" stroke-width="4"/>`);
  if (tube === 'level') p.push(`<rect x="115" y="${top}" width="10" height="${208 - top}" fill="${RED}"/>`);
  p.push(`<circle cx="120" cy="210" r="14" fill="${RED}" stroke="${INK}" stroke-width="4"/>`);
  // 围巾垂下来的两条尾巴 + 流苏
  p.push(scarfPart('sb', 'M72 150 L26 198 L42 212 L88 162 Z'));
  p.push(`<path d="M29 201 l-7 7 M34 205 l-7 7 M39 209 l-7 7" ${stroke(3)}/>`);
  p.push(scarfPart('sa', 'M84 160 L52 214 L70 224 L102 168 Z'));
  p.push(`<path d="M56 216 l-5 9 M62 219 l-5 9 M67 222 l-5 9" ${stroke(3)}/>`);
  // 头：白色外圈 + 淡紫灰的脸
  p.push(`<circle cx="120" cy="80" r="66" fill="#fff" stroke="${INK}" stroke-width="5"/>`);
  p.push(`<circle cx="120" cy="80" r="54" fill="${GLASS}" stroke="${INK}" stroke-width="4"/>`);
  // 围脖
  p.push(scarfPart('sc', 'M74 134 Q120 154 166 134 Q174 146 168 158 Q120 186 72 158 Q66 146 74 134 Z'));
  // 脸
  if (f.blush) {
    p.push(`<clipPath id="face-${uid}"><circle cx="120" cy="80" r="52"/></clipPath>`);
    p.push(`<g clip-path="url(#face-${uid})" fill="#FF9DB5" opacity="${f.blush}"><ellipse cx="87" cy="121" rx="10" ry="5"/><ellipse cx="153" cy="121" rx="10" ry="5"/></g>`);
  }
  if (f.extras?.includes('tears')) p.push(REF_EXTRAS.tears);
  const [le, re] = f.eyes;
  if (le) p.push(refEye(EYE_L, EYE_Y, le, -1, uid));
  if (re) p.push(refEye(EYE_RX, EYE_Y, re, 1, uid));
  const [bl, br] = Array.isArray(f.brow) ? f.brow : [f.brow, f.brow];
  p.push(refBrow(EYE_L, EYE_Y, -1, bl) + refBrow(EYE_RX, EYE_Y, 1, br));
  p.push(REF_MOUTHS[f.mouth] ?? `<g transform="translate(120 119) scale(0.75) translate(-120 -172)">${MOUTHS[f.mouth]}</g>`);
  for (const x of f.extras ?? []) if (x !== 'tears') p.push(REF_EXTRAS[x]);
  return `<g>\n${p.join('\n')}\n</g>`;
}

// 生成一个表情的 SVG 内部内容（坐标系 240x240，外面再整体缩到 90% 留出帽子和描边的边距）
export function faceInner(name, phase = 'mercury', tube = 'level') {
  const ph = PHASES[phase];
  if (ph.layout === 'ref') return refInner(name, phase, tube);
  const e = EMOTIONS[name];
  const uid = `${phase}-${name}`;
  const color = ph.tint(e.color);
  const fill = ph.gradient ? `url(#g-${uid})` : color;
  const liquidTop = 96 - e.level * 76;
  const [le, re] = e.eyes;
  const eyeY = 146;
  const parts = [];
  if (ph.gradient) {
    const stops = ph.gradient.map((c, i) => `<stop offset="${i / (ph.gradient.length - 1)}" stop-color="${c}"/>`).join('');
    parts.push(`<linearGradient id="g-${uid}" x1="0" y1="0" x2="0" y2="1">${stops}</linearGradient>`);
  }
  // 脚、手（在球体后面）
  parts.push(`<ellipse cx="98" cy="216" rx="17" ry="9" fill="${INK}"/><ellipse cx="142" cy="216" rx="17" ry="9" fill="${INK}"/>`);
  parts.push(ARMS[e.arms ?? 'down']);
  // 玻璃管 + 水银柱 + 刻度
  parts.push(`<rect x="98" y="8" width="44" height="112" rx="22" fill="#F4F9FF" stroke="${INK}" stroke-width="6"/>`);
  parts.push(`<clipPath id="tube-${uid}"><rect x="105" y="15" width="30" height="110" rx="15"/></clipPath>`);
  parts.push(`<rect x="100" y="${liquidTop}" width="40" height="130" rx="15" fill="${fill}" clip-path="url(#tube-${uid})"/>`);
  parts.push(`<path d="M128 30 h9 M131 46 h6 M128 62 h9 M131 78 h6" fill="none" stroke="${INK}" stroke-width="3" stroke-linecap="round" opacity=".55"/>`);
  parts.push(`<path d="M110 24 V52" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" opacity=".8"/>`);
  if (ph.hat) parts.push(ph.hat);
  // 水银球（脸）
  parts.push(`<circle cx="120" cy="150" r="62" fill="${ph.pale ?? fill}" stroke="${INK}" stroke-width="6"/>`);
  if (ph.pale) parts.push(`<circle cx="120" cy="150" r="53" fill="none" stroke="${color}" stroke-width="10" opacity=".22"/>`);
  if (ph.gradient) parts.push(`<circle cx="120" cy="150" r="59" fill="${e.color}" opacity=".3"/>`);
  parts.push(`<ellipse cx="90" cy="116" rx="17" ry="9" transform="rotate(-32 90 116)" fill="#fff" opacity=".38"/>`);
  if (ph.over) parts.push(ph.over);
  // 腮红：浅色身体上用心情色，彩色身体上用粉色
  const blush = ph.pale ? (e.blush ? 0.8 : 0.5) : e.blush ? 0.95 : 0.6;
  parts.push(`<g fill="${ph.pale ? color : '#FFC2CF'}" opacity="${blush}"><ellipse cx="80" cy="168" rx="11" ry="7"/><ellipse cx="160" cy="168" rx="11" ry="7"/></g>`);
  // 五官（爱心眼在浅色身体上要换成粉色，否则白色看不见）
  const eyeTint = ph.pale ? '#FF5A8A' : undefined;
  if (e.extras?.includes('tears')) parts.push(EXTRAS.tears);
  if (le) parts.push(EYES[le](98, eyeY, eyeTint));
  if (re) parts.push(EYES[re](142, eyeY, eyeTint));
  if (e.brows) parts.push(brow(98, eyeY, -1, e.brows) + brow(142, eyeY, 1, e.brows));
  parts.push(MOUTHS[e.mouth]);
  for (const x of e.extras ?? []) if (x !== 'tears') parts.push(EXTRAS[x]);
  if (ph.deco) parts.push(ph.deco);
  return `<g transform="translate(12 18) scale(0.9)">\n${parts.join('\n')}\n</g>`;
}

// 白色"贴纸描边"：保证在深色/浅色屏幕背景上都清晰
const STICKER = `<filter id="sticker" x="-10%" y="-10%" width="120%" height="120%">
<feMorphology in="SourceAlpha" operator="dilate" radius="4" result="d"/>
<feFlood flood-color="#fff"/><feComposite in2="d" operator="in" result="o"/>
<feMerge><feMergeNode in="o"/><feMergeNode in="SourceGraphic"/></feMerge></filter>`;

export function faceSvg(name, phase = 'mercury', size = 160, tube = 'level') {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 240 240">
<defs>${STICKER}</defs>
<g filter="url(#sticker)">
${faceInner(name, phase, tube)}
</g>
</svg>
`;
}

// 总览图：把若干 [形态, 表情] 排成网格，深浅背景交替，方便检查两种屏幕主题
function sheetSvg(items, cols, cell = 160) {
  const rows = Math.ceil(items.length / cols);
  const cells = items
    .map(([phase, name], i) => {
      const x = (i % cols) * cell;
      const y = Math.floor(i / cols) * cell;
      const bg = (i + Math.floor(i / cols)) % 2 ? '#101418' : '#EEF2F6';
      return `<rect x="${x}" y="${y}" width="${cell}" height="${cell}" fill="${bg}"/>
<svg x="${x}" y="${y}" width="${cell}" height="${cell}" viewBox="0 0 240 240"><g filter="url(#sticker)">${faceInner(name, phase)}</g></svg>`;
    })
    .join('\n');
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${cols * cell}" height="${rows * cell}" viewBox="0 0 ${cols * cell} ${rows * cell}"><defs>${STICKER}</defs>${cells}</svg>`;
}

// 竖屏（240x320）上表情的尺寸：顶栏约 30px、底部字幕栏约 40px，中间还剩约 250px 高
const PORTRAIT_SIZE = 224;

// ---------- 养成：配饰（只给 mercury 形态画） ----------
// 孩子攒小星星解锁，固件把它们叠在表情图上面（所以每个表情都能戴）。坐标和表情同一个 240x240 坐标系。
// slot：head 头上一件、body 身上一件。box：裁剪范围（要留出白色贴纸描边的 4px）。
// id 和顺序要和服务端 server/plugins/mercury_growth.py 的 ITEMS 一致。
const flowerArt = (() => {
  const [cx, cy] = [64, 30];
  const petals = [0, 72, 144, 216, 288]
    .map((a) => {
      const r = (a * Math.PI) / 180;
      return `<circle cx="${(cx + Math.sin(r) * 10).toFixed(1)}" cy="${(cy - Math.cos(r) * 10).toFixed(1)}" r="8.5"/>`;
    })
    .join('');
  return (
    `<path d="M${cx + 6} ${cy + 10} q14 4 18 16 q-14 0 -18 -16 Z" fill="#6CCB5F" stroke="${INK}" stroke-width="3" stroke-linejoin="round"/>` +
    `<g fill="#FF6F91" stroke="${INK}" stroke-width="3">${petals}</g>` +
    `<circle cx="${cx}" cy="${cy}" r="6.5" fill="#FFD23F" stroke="${INK}" stroke-width="3"/>`
  );
})();
const star5 = (cx, cy, R, r) =>
  Array.from({ length: 10 }, (_, i) => {
    const a = (i * Math.PI) / 5;
    const d = i % 2 ? r : R;
    return `${(cx + Math.sin(a) * d).toFixed(1)} ${(cy - Math.cos(a) * d).toFixed(1)}`;
  }).join(' L');
const badge = (inner) =>
  `<circle cx="144" cy="186" r="15" fill="#fff" stroke="${INK}" stroke-width="3.5"/>` + inner;
export const ACCESSORIES = {
  flower: { name: '小红花', slot: 'head', box: [36, 2, 64, 62], svg: flowerArt },
  star_badge: {
    name: '星星徽章',
    slot: 'body',
    box: [123, 165, 42, 42],
    svg: badge(`<path d="M${star5(144, 187, 11, 4.6)} Z" fill="#FFD23F" stroke="${INK}" stroke-width="2.5" stroke-linejoin="round"/>`),
  },
  knit_hat: {
    name: '毛线帽',
    slot: 'head',
    box: [56, 0, 128, 60],
    svg:
      `<path d="M68 48 C64 8 176 8 172 48 Z" fill="#FF6B6B" stroke="${INK}" stroke-width="4" stroke-linejoin="round"/>` +
      `<path d="M96 20 q4 12 2 24 M120 14 v30 M144 20 q-4 12 -2 24" fill="none" stroke="#E04848" stroke-width="3" stroke-linecap="round"/>` +
      `<path d="M62 52 Q120 24 178 52 L174 40 Q120 12 66 40 Z" fill="#FFD23F" stroke="${INK}" stroke-width="4" stroke-linejoin="round"/>` +
      `<circle cx="120" cy="12" r="9" fill="#fff" stroke="${INK}" stroke-width="3.5"/>`,
  },
  rainbow_badge: {
    name: '彩虹徽章',
    slot: 'body',
    box: [123, 165, 42, 42],
    svg: badge(
      ['#FF5A5A', '#FFB13B', '#FFE14D', '#5FCB6E', '#4AA8FF']
        .map((c, i) => `<path d="M${133 + i * 2} 192 a${11 - i * 2} ${11 - i * 2} 0 0 1 ${22 - i * 4} 0" fill="none" stroke="${c}" stroke-width="2.4"/>`)
        .join('') +
        `<path d="M133 192 a11 11 0 0 1 22 0" fill="none" stroke="${INK}" stroke-width="0"/>`,
    ),
  },
  crown: {
    name: '小皇冠',
    slot: 'head',
    box: [84, 0, 72, 44],
    svg:
      `<path d="M92 34 L90 10 L105 22 L120 4 L135 22 L150 10 L148 34 Q120 40 92 34 Z" fill="#FFD23F" stroke="${INK}" stroke-width="4" stroke-linejoin="round"/>` +
      `<circle cx="120" cy="27" r="4.5" fill="#FF5A7A" stroke="${INK}" stroke-width="2.5"/>` +
      `<circle cx="104" cy="29" r="3.2" fill="#4AA8FF" stroke="${INK}" stroke-width="2"/><circle cx="136" cy="29" r="3.2" fill="#4AA8FF" stroke="${INK}" stroke-width="2"/>`,
  },
};

// 配饰在 size 像素的表情图上的位置和像素（ARGB8888，LVGL 的字节序是 B G R A，非预乘）
function renderAccessory(Resvg, item, size) {
  const s = size / 240;
  const [bx, by, bw, bh] = item.box;
  const x = Math.floor(bx * s);
  const y = Math.floor(by * s);
  const w = Math.ceil((bx + bw) * s) - x;
  const h = Math.ceil((by + bh) * s) - y;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="${x / s} ${y / s} ${w / s} ${h / s}">
<defs>${STICKER}</defs><g filter="url(#sticker)">${item.svg}</g></svg>`;
  const img = new Resvg(svg).render();
  const rgba = img.pixels; // resvg 给的是预乘 alpha 的 RGBA
  const bgra = Buffer.alloc(w * h * 4);
  for (let i = 0; i < w * h * 4; i += 4) {
    const a = rgba[i + 3];
    const un = (c) => (a ? Math.min(255, Math.round((c * 255) / a)) : 0);
    bgra[i] = un(rgba[i + 2]);
    bgra[i + 1] = un(rgba[i + 1]);
    bgra[i + 2] = un(rgba[i]);
    bgra[i + 3] = a;
  }
  return { x, y, w, h, bgra, png: img.asPng() };
}

// 固件用的 C 头文件：每种表情尺寸一份，build_firmware.py 按屏幕方向挑一份复制成 mercury_growth_art.h
function accessoryHeader(Resvg, size) {
  const lines = [
    `// 由 character/gen-faces.mjs 生成，不要手改。Mercury 的养成配饰，叠在 ${size}px 的表情图上。`,
    '#pragma once',
    '',
    '#include <cstdint>',
    '',
    'namespace mercury_art {',
    '',
    `constexpr int kFaceSize = ${size};`,
    '',
    'struct Accessory {',
    '    const char* id;',
    '    const char* slot;  // "head" 或 "body"',
    '    int16_t x, y;      // 在表情图里的左上角',
    '    uint16_t w, h;',
    '    const uint8_t* argb8888;',
    '};',
    '',
  ];
  const entries = [];
  for (const [id, item] of Object.entries(ACCESSORIES)) {
    const r = renderAccessory(Resvg, item, size);
    lines.push(`static const uint8_t k_${id}[] = {${Array.from(r.bgra).join(',')}};  // ${item.name}`);
    entries.push(`    {"${id}", "${item.slot}", ${r.x}, ${r.y}, ${r.w}, ${r.h}, k_${id}},`);
  }
  lines.push('', 'static const Accessory kAccessories[] = {', ...entries, '};', '', '}  // namespace mercury_art', '');
  return lines.join('\n');
}

// 预览：中性表情 + 不同心情温度 + 每件配饰
function growthPreviewSvg() {
  const cell = 160;
  const looks = [
    { mood: 0.3, wear: [] },
    { mood: 0.6, wear: ['flower', 'star_badge'] },
    { mood: 0.8, wear: ['knit_hat', 'rainbow_badge'] },
    { mood: 1, wear: ['crown', 'star_badge'] },
  ];
  const cells = looks
    .map(({ mood, wear }, i) => {
      const top = 194 - mood * 26;
      const bar = `<rect x="115" y="${top}" width="10" height="${194 - top}" fill="#F5333F"/>`;
      const bg = i % 2 ? '#101418' : '#EEF2F6';
      return `<rect x="${i * cell}" y="0" width="${cell}" height="${cell}" fill="${bg}"/>
<svg x="${i * cell}" y="0" width="${cell}" height="${cell}" viewBox="0 0 240 240"><g filter="url(#sticker)">${faceInner('neutral', 'mercury', 'empty')}</g>${bar}${wear
        .map((id) => `<g filter="url(#sticker)">${ACCESSORIES[id].svg}</g>`)
        .join('')}</svg>`;
    })
    .join('\n');
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${looks.length * cell}" height="${cell}"><defs>${STICKER}</defs>${cells}</svg>`;
}

async function main() {
  const size = Number(process.argv[2] ?? 160);
  const out = join(HERE, 'out');
  rmSync(out, { recursive: true, force: true });
  const { Resvg } = await import('@resvg/resvg-js');
  const png = (svg) => new Resvg(svg).render().asPng();
  const names = Object.keys(EMOTIONS);
  for (const phase of Object.keys(PHASES)) {
    mkdirSync(join(out, phase, 'svg'), { recursive: true });
    mkdirSync(join(out, phase, 'png'), { recursive: true });
    mkdirSync(join(out, phase, 'png-portrait'), { recursive: true });
    // mercury 形态给固件的 PNG 是空玻璃管，水银柱由固件按今天的心情温度画
    const tube = phase === 'mercury' ? 'empty' : 'level';
    for (const name of names) {
      const svg = faceSvg(name, phase, size);
      writeFileSync(join(out, phase, 'svg', `${name}.svg`), svg);
      writeFileSync(join(out, phase, 'png', `${name}.png`), png(faceSvg(name, phase, size, tube)));
      writeFileSync(join(out, phase, 'png-portrait', `${name}.png`), png(faceSvg(name, phase, PORTRAIT_SIZE, tube)));
    }
    writeFileSync(join(out, `sheet-${phase}.png`), png(sheetSvg(names.map((n) => [phase, n]), 7)));
  }
  const preview = ['neutral', 'happy', 'loving', 'surprised', 'sad', 'angry', 'sleepy'];
  writeFileSync(
    join(out, 'phases.png'),
    png(sheetSvg(Object.keys(PHASES).flatMap((p) => preview.map((n) => [p, n])), preview.length)),
  );
  console.log(`generated ${Object.keys(PHASES).length} phases x ${names.length} faces at ${size}px -> ${out}`);

  const growth = join(out, 'mercury', 'growth');
  mkdirSync(growth, { recursive: true });
  for (const sz of [size, PORTRAIT_SIZE]) {
    writeFileSync(join(growth, `growth_art_${sz}.h`), accessoryHeader(Resvg, sz));
  }
  for (const [id, item] of Object.entries(ACCESSORIES)) {
    writeFileSync(join(growth, `${id}.png`), renderAccessory(Resvg, item, PORTRAIT_SIZE).png);
  }
  writeFileSync(join(out, 'growth-preview.png'), png(growthPreviewSvg()));
  console.log(`generated ${Object.keys(ACCESSORIES).length} accessories -> ${growth}`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) await main();
