# Build with: python -m PyInstaller packaging/DocumentAssistant.spec
from pathlib import Path
import sys
from PyInstaller.utils.hooks import copy_metadata
root = Path(SPECPATH).parent
assets = [(str(path), 'document_assistant') for path in (root / 'document_assistant').iterdir()
          if path.suffix in ('.svg', '.ico', '.png')]
assets += [(str(root / 'THIRD_PARTY_NOTICES.md'), '.'), (str(Path(sys.base_prefix) / 'LICENSE.txt'), '.')]
assets += [(str(root / 'packaging' / 'licenses'), 'licenses')]
for package in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'PySide6_Pdf', 'shiboken6',
                'pypdf', 'python-docx', 'lxml', 'olefile', 'typing_extensions', 'numpy', 'PyAudioWPatch'):
    assets += copy_metadata(package)
a = Analysis([str(root / 'desktop.py')], pathex=[str(root)], binaries=[], datas=assets,
             hiddenimports=['document_assistant.extractor', 'pyaudiowpatch'],
             excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
                       'PySide6.QtQml', 'PySide6.QtQuick', 'tkinter', 'PIL', 'unittest', 'pytest'])
# Windows 10+ supplies the Universal CRT and API-set contracts. Shipping copies
# from the build host can select incompatible exports on the destination machine.
a.binaries = [entry for entry in a.binaries
              if not Path(entry[0]).name.lower().startswith(('api-ms-win-', 'ext-ms-win-'))
              and Path(entry[0]).name.lower() != 'ucrtbase.dll']
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='DocumentAssistant', console=False,
          icon=str(root / 'document_assistant' / 'documentassistant.ico'),
          version=str(root / 'packaging' / 'version-info.py'), upx=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='DocumentAssistant')
