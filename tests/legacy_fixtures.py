"""Synthetic CFB/DOC containers with controlled piece-table text; no real documents."""
import struct
from pathlib import Path

FREE, END, FAT = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD


def make_doc(path: Path, pieces=('项目实施方案\r任务分配：整理示例数据。\r',), encrypted=False, table_one=True):
    word = bytearray(4096)
    struct.pack_into('<HH', word, 0, 0xA5EC, 0x00C1)
    struct.pack_into('<H', word, 10, 0x1000 | (0x0200 if table_one else 0) | (0x0100 if encrypted else 0))
    struct.pack_into('<H', word, 32, 14)
    struct.pack_into('<H', word, 62, 22)
    struct.pack_into('<H', word, 152, 93)
    positions, records, cursor = [0], [], 1024
    for piece in pieces:
        compressed = isinstance(piece, bytes)
        data = piece if compressed else piece.encode('utf-16-le')
        count = len(data) if compressed else len(data) // 2
        if cursor + len(data) > 4096:
            raise ValueError('Fixture exceeds fixed stream size')
        word[cursor:cursor + len(data)] = data
        fc = (cursor * 2) | 0x40000000 if compressed else cursor
        records.append(struct.pack('<HIH', 0, fc, 0))
        positions.append(positions[-1] + count)
        cursor += len(data) + 8
    struct.pack_into('<I', word, 76, positions[-1])
    plc = struct.pack('<' + 'I' * len(positions), *positions) + b''.join(records)
    clx = b'\x02' + struct.pack('<I', len(plc)) + plc
    table = clx.ljust(4096, b'\0')
    struct.pack_into('<II', word, 418, 0, len(clx))
    header = bytearray(512)
    header[:8] = bytes.fromhex('D0CF11E0A1B11AE1')
    struct.pack_into('<HHHHH', header, 24, 0x3E, 3, 0xFFFE, 9, 6)
    struct.pack_into('<IIIIIIIII', header, 40, 0, 1, 0, 0, 4096, END, 0, END, 0)
    struct.pack_into('<109I', header, 76, 17, *([FREE] * 108))

    def directory(name, kind, start, size, left=FREE, right=FREE, child=FREE):
        entry = bytearray(128)
        encoded = (name + '\0').encode('utf-16-le')
        entry[:len(encoded)] = encoded
        struct.pack_into('<HBBIII', entry, 64, len(encoded), kind, 1, left, right, child)
        struct.pack_into('<IQ', entry, 116, start, size)
        return entry

    directory_stream = (directory('Root Entry', 5, END, 0, child=1) +
                        directory('WordDocument', 2, 1, 4096, left=2) +
                        directory('1Table' if table_one else '0Table', 2, 9, 4096) + bytearray(128))
    fat = [FREE] * 128
    fat[0] = END
    for start in (1, 9):
        for sector in range(start, start + 7):
            fat[sector] = sector + 1
        fat[start + 7] = END
    fat[17] = FAT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + directory_stream + word + table + struct.pack('<128I', *fat))
    return path
