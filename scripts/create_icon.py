"""Package the current transparent PNG into multi-resolution Windows ICO assets."""
import struct
from pathlib import Path
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage


def main():
    assets = Path(__file__).resolve().parents[1] / 'document_assistant'
    image = QImage(str(assets / 'app-icon.png'))
    if image.isNull():
        raise SystemExit('Missing or invalid document_assistant/app-icon.png')
    if image.width() != image.height():
        raise SystemExit('Source icon must be square; no automatic cropping is performed')
    images = []
    for size in (16, 20, 24, 32, 40, 48, 64, 96, 128, 256):
        scaled = image.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not scaled.save(buffer, 'PNG'):
            raise OSError('PNG encoding failed')
        images.append((size, bytes(data)))
    offset = 6 + 16 * len(images)
    entries = []
    for size, data in images:
        entries.append(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    payload=struct.pack('<HHH', 0, 1, len(images)) + b''.join(entries) + b''.join(data for _, data in images)
    for name in ('documentassistant.ico','documentassistant-glass.ico'):
        icon=assets/name;icon.write_bytes(payload);print(icon)


if __name__ == '__main__':
    main()
