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
    overlap_min = max(48, height // 5)
    max_shift = height - overlap_min
    if max_shift < 2:
        return None
    raw_previous = raw_previous or [bytes(v * 8 for v in row) for row in previous]
    raw_current = raw_current or [bytes(v * 8 for v in row) for row in current]
    # A floating button or a small repaint must not invalidate an entire row.
    # Independent horizontal bands supply candidates; raw pixels verify them.
    positions = defaultdict(list)
    for y, row in enumerate(previous):
        for band in range(6):
            token = bytes(v // 2 for v in row[band * 12:(band + 1) * 12])
            if max(token) - min(token) >= 2:
                positions[band, token].append(y)
    votes = Counter()
    step = max(1, height // 200)
    for y in range(0, height, step):
        row = current[y]
        for band in range(6):
            token = bytes(v // 2 for v in row[band * 12:(band + 1) * 12])
            matches = positions.get((band, token), ())
            if len(matches) > 80:
                continue  # Repeated patterns are not reliable anchors.
            for old in matches:
                shift = old - y
                if shift == 0 or 2 <= abs(shift) <= max_shift:
                    votes[shift] += 1
    shifts = {0}
    for shift, count in votes.most_common(16):
        if count >= 4:
            shifts.update(s for s in (shift - 1, shift, shift + 1)
                          if s == 0 or 2 <= abs(s) <= max_shift)
    candidates = []
    for shift in shifts:
        old_start = max(0, shift); new_start = max(0, -shift)
        overlap = height - abs(shift)
        good = []; total = 0; error = 0.
        for y in range(0, overlap, max(1, overlap // 320)):
            a, b = raw_previous[old_start + y], raw_current[new_start + y]
            errors = []
            for band in range(6):
                left, right = a[band * 12:(band + 1) * 12], b[band * 12:(band + 1) * 12]
                if max(left) - min(left) >= 24 or max(right) - min(right) >= 24:
                    errors.append(sum(abs(x - z) for x, z in zip(left, right)) / 12)
            if not errors:
                continue
            errors.sort()
            retained = errors[:-1] if len(errors) >= 3 else errors
            difference = sum(retained) / len(retained)
            total += 1; error += difference
            if difference <= 5.0:
                good.append(y)
        if len(good) >= 20 and len(good) / max(1, total) >= .72 and good[-1] - good[0] >= min(96, overlap * .35):
            candidates.append((len(good) / total, -error / total, len(good), shift))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    best = candidates[0]
    # Repeated rows/patterns must not silently duplicate or skip content.
    if any(abs(other[3] - best[3]) > 2 and other[0] >= best[0] - .025 and other[1] >= best[1] - .35
           and other[2] >= best[2] * .85 for other in candidates[1:]):
        return None
    return best[3]


def frames_settled(previous, current):
    """Allow local hover/animation changes while requiring the text to stop."""
    if previous is None or previous.size() != current.size():
        return False
    if previous == current:
        return True
    left, right = row_signatures(previous, False), row_signatures(current, False)
    stable = total = 0
    for a, b in zip(left, right):
        if max(a) - min(a) >= 24 or max(b) - min(b) >= 24:
            total += 1
            stable += sum(abs(x - y) for x, y in zip(a, b)) / len(a) <= 2.5
    return total >= 20 and stable / total >= .80


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
        if frames_settled(self.previous, frame):
            return StitchResult('unchanged')
        signatures = row_signatures(frame)
        if signatures == self.signatures:
            return StitchResult('unchanged')
        raw = row_signatures(frame, False)
        shift = vertical_shift(self.signatures, signatures, self.raw_signatures, raw)
        if shift is None:
            return StitchResult('no_overlap')
        if shift == 0:
            return StitchResult('unchanged')
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
