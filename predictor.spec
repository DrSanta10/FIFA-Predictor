# predictor.spec
# PyInstaller build specification for "FIFA Predictor.exe"
#
# Build command (run from the project root):
#   pyinstaller predictor.spec --clean
#
# Or just double-click build.bat on Windows.
#
# Output: dist/FIFA Predictor.exe   (~80-120 MB, one file, no install needed)

block_cipher = None

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=[],
    datas=[
        # Web frontend -- Flask needs these at runtime as real files,
        # not compiled into the .pyc archive. They land in sys._MEIPASS
        # at the same relative paths, and webapp/app.py resolves them
        # via sys._MEIPASS when frozen.
        ("webapp/templates", "webapp/templates"),
        ("webapp/static",    "webapp/static"),

        # Python source modules -- included as data so their relative
        # import paths resolve correctly inside the bundle.
        ("src",       "src"),
        ("config.py", "."),

        # Seed the data folder structure next to the exe so the app can
        # write to it on first run (the .gitkeep files are placeholders).
        # Actual CSV/JSON data files are downloaded at runtime; they are
        # NOT bundled (would bloat the exe and be stale immediately).
        ("data/raw/.gitkeep",       "data/raw"),
        ("data/processed/.gitkeep", "data/processed"),
    ],
    hiddenimports=[
        # scikit-learn Cython extensions -- PyInstaller misses these
        "sklearn.utils._cython_blas",
        "sklearn.neighbors._typedefs",
        "sklearn.neighbors._quad_tree",
        "sklearn.tree._utils",
        "sklearn.tree._criterion",
        "sklearn.linear_model._logistic",
        "sklearn.utils._weight_vector",
        "sklearn.utils.murmurhash",
        # Flask internals
        "flask",
        "flask.templating",
        "jinja2",
        "jinja2.ext",
        "werkzeug",
        "werkzeug.serving",
        "werkzeug.debug",
        # pystray Windows backend
        "pystray._win32",
        # PIL image modules used for the tray icon
        "PIL._imaging",
        "PIL.Image",
        "PIL.ImageDraw",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Things we definitely don't need -- shaves ~10 MB off the exe
        "tkinter",
        "matplotlib",
        "IPython",
        "jupyter",
        "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="FIFA Predictor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,          # Compress with UPX if available (reduces size ~30%)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,     # No black console window on Windows
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # To add a custom .ico file: icon="assets/icon.ico"
    # Generate one from the PIL icon code in launcher.py if needed.
)
