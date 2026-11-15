#!/usr/bin/env python3
"""从一份 NVS 分区镜像里删除一个键，做法和设备自己执行 nvs_erase_key 一样：
只把该条目在页内"状态位图"里的状态从 WRITTEN(0b10) 改成 ERASED(0b00)，其余字节原样保留。

    python nvs_remove_key.py <输入.bin> <输出.bin> <命名空间> <键>

用途：这块板子以前配置过别的服务器，NVS 里的 wifi:ota_url 会盖过编进固件的地址。
删掉它之后固件就会使用内置地址，已保存的 Wi-Fi 不受影响。
"""
import sys

PAGE = 4096
ENTRY = 32
ENTRIES_PER_PAGE = 126
WRITTEN = 0b10
PAGE_ACTIVE = 0xFFFFFFFE
PAGE_FULL = 0xFFFFFFFC


def main(src, dst, namespace, key):
    data = bytearray(open(src, "rb").read())
    if len(data) % PAGE:
        sys.exit(f"镜像大小 {len(data)} 不是 {PAGE} 的整数倍")
    pages = [p for p in range(len(data) // PAGE)
             if int.from_bytes(data[p * PAGE:p * PAGE + 4], "little") in (PAGE_ACTIVE, PAGE_FULL)]

    def state(p, i):
        return (data[p * PAGE + 32 + i // 4] >> ((i % 4) * 2)) & 0b11

    def mark_erased(p, i):
        data[p * PAGE + 32 + i // 4] &= ~(0b11 << ((i % 4) * 2)) & 0xFF

    def written_entries():
        for p in pages:
            i = 0
            while i < ENTRIES_PER_PAGE:
                if state(p, i) != WRITTEN:
                    i += 1
                    continue
                off = p * PAGE + 64 + i * ENTRY
                e = bytes(data[off:off + ENTRY])
                span = max(1, e[2])
                name = e[8:24].split(b"\0", 1)[0].decode("ascii", "replace")
                yield p, i, span, e[0], e[1], name, e[24]
                i += span

    ns_index = next((value for _, _, _, ns, _, name, value in written_entries() if ns == 0 and name == namespace), None)
    if ns_index is None:
        sys.exit(f"没有找到命名空间 {namespace}")

    hits = [(p, i, span) for p, i, span, ns, _, name, _ in written_entries() if ns == ns_index and name == key]
    if not hits:
        print(f"{namespace}:{key} 不存在，镜像未改动")
    for p, i, span in hits:
        for j in range(i, i + span):
            mark_erased(p, j)
        print(f"已删除 {namespace}:{key}（第 {p} 页，条目 {i}，占 {span} 格）")
    open(dst, "wb").write(data)


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    main(*sys.argv[1:])
