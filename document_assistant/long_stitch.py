"""Conservative vertical stitching: append only a uniquely matched overlap."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter


@dataclass(frozen=True)
class StitchResult:
    status: str
    added: int = 0


def row_signatures(image, quantize=True):
    # Ignore the outer edges, where scrollbars and selection borders may sit.
    gray = image.convertToFormat(QImage.Format.Format_Grayscale8)
    gray = gray.scaled(80, image.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.FastTransformation)
    data = bytes(gray.constBits()); stride = gray.bytesPerLine()
    rows = []
    for y in range(gray.height()):
        samples = data[y * stride + 4:y * stride + 76]
        rows.append(bytes(value // 8 for value in samples) if quantize else samples)
    return rows


def informative(row):
    return max(row) - min(row) >= 3


def vertical_shift(previous, current, raw_previous=None, raw_current=None):
    height = len(previous)
    overlap_min = max(48, height // 3)
    max_shift = height - overlap_min
    if max_shift < 2:
        return None
    positions = defaultdict(list)
    for y, row in enumerate(previous):
        if informative(row):
            positions[row].append(y)
    votes = Counter()
    step = max(1, height // 180)
    for y in range(0, height, step):
        row = current[y]
        if not informative(row):
            continue
        for old in positions.get(row, ()):
            shift = old - y
            if 2 <= abs(shift) <= max_shift:
                votes[shift] += 1
    candidates = []
    for shift, count in votes.most_common(12):
        if count < 4:
            continue
        old_start = max(0, shift); new_start = max(0, -shift)
        overlap = height - abs(shift)
        matched = total = 0
        for y in range(overlap):
            a, b = previous[old_start + y], current[new_start + y]
            if informative(a) or informative(b):
                total += 1
                matched += a == b
        if total >= 20 and matched / total >= .90:
            error = 0.
            if raw_previous is not None and raw_current is not None:
                count_pixels = 0
                for y in range(0, overlap, max(1, overlap // 100)):
                    a, b = raw_previous[old_start + y], raw_current[new_start + y]
                    for x in range(0, len(a), 3):
                        error += abs(a[x] - b[x]); count_pixels += 1
                error /= max(1, count_pixels)
            candidates.append((-error, matched / total, matched, shift))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    best = candidates[0]
    # Repeated rows/patterns must not silently duplicate or skip content.
    if any(abs(other[3] - best[3]) > 2 and other[0] >= best[0] - .1 and other[1] >= best[1] - .025
           and other[2] >= best[2] * .85 for other in candidates[1:]):
        return None
    return best[3]


class VerticalStitcher:
    def __init__(self, first, max_height=20000, max_pixels=24000000):
        if first.isNull() or first.width() < 80 or first.height() < 80:
            raise ValueError('长截图区域至少需要 80 × 80 像素，请重新框选')
        if first.height() > max_height or first.width() * first.height() > max_pixels:
            raise ValueError('所选区域过大，请缩小范围')
        self.previous = first.copy(); self.previous.setDevicePixelRatio(1)
        self.signatures = row_signatures(self.previous)
        self.raw_signatures = row_signatures(self.previous, False)
        self.parts = [self.previous]; self.height = first.height()
        self.max_height = max_height; self.max_pixels = max_pixels

    @property
    def width(self):
        return self.previous.width()

    def append(self, frame):
        if frame.isNull() or frame.size() != self.previous.size():
            return StitchResult('size_changed')
        if frame == self.previous:
            return StitchResult('unchanged')
        signatures = row_signatures(frame)
        if signatures == self.signatures:
            return StitchResult('unchanged')
        raw = row_signatures(frame, False)
        shift = vertical_shift(self.signatures, signatures, self.raw_signatures, raw)
        if shift is None:
            return StitchResult('no_overlap')
        if shift < 0:
            return StitchResult('upward')
        new_height = self.height + shift
        if new_height > self.max_height or self.width * new_height > self.max_pixels:
            return StitchResult('limit')
        self.parts.append(frame.copy(0, frame.height() - shift, frame.width(), shift))
        self.previous = frame.copy(); self.previous.setDevicePixelRatio(1)
        self.signatures = signatures; self.raw_signatures = raw; self.height = new_height
        return StitchResult('appended', shift)

    def image(self):
        result = QImage(self.width, self.height, QImage.Format.Format_RGB32)
        if result.isNull():
            raise MemoryError('长图过大，无法分配图片内存')
        painter = QPainter(result); y = 0
        for part in self.parts:
            painter.drawImage(0, y, part); y += part.height()
        painter.end(); result.setDevicePixelRatio(1)
        return result
