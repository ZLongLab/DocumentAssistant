"""Read Word 97–2003 main-story text from the MS-DOC piece table.

No Office automation, conversion, macro execution or document writes.
Spec: https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-doc/0c9df81f-98d0-454e-ad84-b612cd05b1a4
"""
import re
import struct
from pathlib import Path
import olefile


def number(data, offset, code):
    size = struct.calcsize(code)
    if offset < 0 or offset + size > len(data):
        raise ValueError('DOC 结构损坏：字段越界')
    return struct.unpack_from(code, data, offset)[0]


def span(data, offset, length):
    if offset < 0 or length < 0 or offset + length > len(data):
        raise ValueError('DOC 结构损坏：文本或片段表越界')
    return data[offset:offset + length]


COMPRESSED_MAP = dict(zip(
    (0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8A, 0x8B, 0x8C,
     0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0x9B, 0x9C, 0x9F),
    (0x201A, 0x0192, 0x201E, 0x2026, 0x2020, 0x2021, 0x02C6, 0x2030, 0x0160, 0x2039, 0x0152,
     0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2013, 0x2014, 0x02DC, 0x2122, 0x0161, 0x203A, 0x0153, 0x0178)))


def extract_doc(path: Path, limit=100_000, byte_limit=50 * 1024 * 1024):
    if not olefile.isOleFile(str(path)):
        raise ValueError('DOC 不是支持的 Word 97–2003 二进制文件；可另存为 DOCX。仍可按文件名分类归档')
    with olefile.OleFileIO(str(path), raise_defects=olefile.DEFECT_INCORRECT) as ole:
        if not ole.exists('WordDocument'):
            raise ValueError('DOC 缺少 WordDocument 正文流')
        if ole.get_size('WordDocument') > byte_limit:
            raise ValueError('DOC 正文流超过 50 MB')
        word = ole.openstream('WordDocument').read()
        if number(word, 0, '<H') != 0xA5EC or number(word, 2, '<H') < 0x00C1:
            raise ValueError('暂不支持 Word 97 之前的 DOC，请另存为 DOCX')
        flags = number(word, 10, '<H')
        if flags & 0x0100:
            raise ValueError('DOC 需要密码，未提取加密正文')
        table_name = '1Table' if flags & 0x0200 else '0Table'
        if not ole.exists(table_name) or ole.get_size(table_name) > byte_limit:
            raise ValueError('DOC 片段表缺失或超过大小限制')
        table = ole.openstream(table_name).read()
    # Variable-length FIB sections; do not assume a fixed byte offset for fcClx.
    after_words = 34 + 2 * number(word, 32, '<H')
    long_count = number(word, after_words, '<H')
    if long_count < 4:
        raise ValueError('DOC 字符计数缺失')
    longs = after_words + 2
    main_characters = number(word, longs + 12, '<I')
    pairs = longs + 4 * long_count
    pair_count = number(word, pairs, '<H')
    if pair_count < 34:
        raise ValueError('DOC 不含标准正文片段表')
    span(word, pairs + 2, pair_count * 8)
    clx_offset = number(word, pairs + 2 + 33 * 8, '<I')
    clx_size = number(word, pairs + 6 + 33 * 8, '<I')
    clx = span(table, clx_offset, clx_size)
    cursor = 0
    while cursor < len(clx) and clx[cursor] == 1:
        cursor += 3 + number(clx, cursor + 1, '<H')
    if cursor >= len(clx) or clx[cursor] != 2:
        raise ValueError('DOC 正文片段表无法识别')
    plc = span(clx, cursor + 5, number(clx, cursor + 1, '<I'))
    if len(plc) < 4 or (len(plc) - 4) % 12:
        raise ValueError('DOC 正文片段表长度异常')
    count = (len(plc) - 4) // 12
    positions = [number(plc, i * 4, '<I') for i in range(count + 1)]
    if positions[0] != 0 or positions[-1] < main_characters or any(a > b for a, b in zip(positions, positions[1:])):
        raise ValueError('DOC 正文字符位置异常')
    end = min(main_characters, limit)
    chunks = []
    for index in range(count):
        start = positions[index]
        if start >= end:
            break
        characters = min(positions[index + 1], end) - start
        fc = number(plc, (count + 1) * 4 + index * 8 + 2, '<I')
        offset = fc & 0x3FFFFFFF
        if fc & 0x40000000:
            raw = span(word, offset // 2, characters)
            chunk = ''.join(chr(COMPRESSED_MAP.get(b, b)) for b in raw).encode('utf-16-le')
        else:
            chunk = span(word, offset, characters * 2)
        chunks.append(chunk)
    raw_text = b''.join(chunks)
    # A character limit may split a UTF-16 surrogate pair; drop the final half.
    if main_characters > limit and len(raw_text) >= 2 and 0xD800 <= number(raw_text, len(raw_text) - 2, '<H') <= 0xDBFF:
        raw_text = raw_text[:-2]
    text = raw_text.decode('utf-16-le')
    text = re.sub(r'\x13[^\x13\x14\x15]*\x14([^\x13\x15]*)\x15', r'\1', text)
    text = text.replace('\r', '\n').replace('\x07', ' | ').replace('\x0b', '\n').replace('\x0c', '\n')
    text = re.sub(r'[\x00-\x06\x08\x0e-\x1f]', '', text)
    return text, main_characters > limit
