# Third-party components

The Windows distribution bundles CPython, PySide6 / Qt, Shiboken6, pypdf,
python-docx, lxml, olefile, typing_extensions and PyAudioWPatch/PortAudio. Their license notices are
included in the application's `_internal` directory and package metadata.

- CPython: https://www.python.org/psf/license/
- PySide6 / Shiboken6 / Qt: https://www.qt.io/licensing/open-source-lgpl-obligations
  and https://code.qt.io/cgit/pyside/pyside-setup.git/
- pypdf: https://github.com/py-pdf/pypdf
- python-docx: https://github.com/python-openxml/python-docx
- lxml: https://github.com/lxml/lxml
- olefile: https://github.com/decalage2/olefile
- typing_extensions: https://github.com/python/typing_extensions
- PyAudioWPatch (Apache-2.0), with PyAudio / PortAudio (MIT):
  https://github.com/s0d3s/PyAudioWPatch and https://www.portaudio.com/license.html
- PyInstaller bootloader: https://pyinstaller.org/en/stable/license.html

Qt is distributed as separate shared libraries. This project does not modify
these third-party components. These notices do not grant a license for the
DocumentAssistant application source itself.
