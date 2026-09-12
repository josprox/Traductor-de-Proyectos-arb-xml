# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

block_cipher = None

argos_datas, argos_binaries, argos_hiddenimports = collect_all('argostranslate')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=argos_binaries,
    datas=[
        ('icon/icono.ico', 'icon'),
        ('icon/icono.png', 'icon'),
        ('icon/iconC.svg', 'icon'),
        ('icon/iconR.svg', 'icon'),
    ] + argos_datas,
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'openpyxl',
        'lxml',
        'requests',
    ] + argos_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Argos usa MiniSBD+CTranslate2. Stanza/PyTorch/spaCy son alternativas de
    # segmentación innecesarias que además colisionan con las DLL de PySide6.
    excludes=['torch', 'stanza', 'spacy', 'thinc', 'srsly', 'cymem', 'preshed',
              'blis', 'confection', 'weasel', 'catalogue'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# El entorno de desarrollo puede añadir runtimes auxiliares al PATH. No son
# dependencias de la aplicación y sus DLL de sistema entran en conflicto con Qt.
a.binaries = [
    item for item in a.binaries
    if 'codex-runtimes' not in str(item[1]).casefold()
]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TraductorApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Sin ventana de consola
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon/icono.ico'  # Icono del ejecutable
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TraductorApp'
)
