"""
launcher.py
-----------
Entry point for the FIFA Predictor desktop application.
PyInstaller compiles this into a single "FIFA Predictor.exe".

What it does:
  1. Sets FIFA_DATA_DIR so config.py knows to write data files next to the
     .exe rather than into PyInstaller's read-only bundle directory.
  2. Finds a free port (5000 or next available, in case 5000 is taken).
  3. Starts the Flask server in a background daemon thread.
  4. Waits until the server is actually accepting connections.
  5. Opens the user's default browser to the dashboard.
  6. Puts a football-icon in the Windows system tray so the user can
     re-open the dashboard or quit cleanly.

The system tray icon runs on the main thread (required by most OSes).
Flask runs on a daemon thread so it dies automatically when the tray
icon exits.
"""

import os
import sys

# -----------------------------------------------------------------------
# CRITICAL: set FIFA_DATA_DIR BEFORE any local imports so config.py
# routes all file reads/writes to a writable location (next to the
# .exe) rather than sys._MEIPASS (the read-only temp bundle dir).
# -----------------------------------------------------------------------
if getattr(sys, "frozen", False):
    _exe_dir = os.path.dirname(sys.executable)
    # Add the bundle dir to sys.path so our src/ modules are importable.
    sys.path.insert(0, sys._MEIPASS)
else:
    _exe_dir = os.path.dirname(os.path.abspath(__file__))

os.environ.setdefault("FIFA_DATA_DIR", _exe_dir)

# -----------------------------------------------------------------------
# Remaining imports (all safe now that FIFA_DATA_DIR is set)
# -----------------------------------------------------------------------
import socket
import threading
import time
import webbrowser


def find_free_port(preferred: int = 5000) -> int:
    """Return `preferred` if free, otherwise the next available port."""
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free port found in range 5000-5049")


def wait_for_server(port: int, timeout: float = 15.0) -> bool:
    """Poll until Flask is actually accepting connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def make_icon_image():
    """
    Generate the system tray icon programmatically using Pillow.
    A deep navy circle with a gold ring and three gold dots suggesting
    a football -- matches the web app's colour scheme.
    """
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Navy background disc
    draw.ellipse([1, 1, size - 2, size - 2], fill="#0B1220")
    # Gold outer ring
    draw.ellipse([1, 1, size - 2, size - 2], outline="#F5B344", width=4)
    # Inner gold ring (football seam suggestion)
    draw.ellipse([15, 15, size - 16, size - 16], outline="#F5B344", width=2)
    # Three gold pentagon dots
    for cx, cy in [(32, 22), (22, 40), (42, 40)]:
        draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill="#F5B344")

    return img


def run_tray(port: int) -> None:
    """Create and run the system tray icon (must run on the main thread)."""
    import pystray

    url = f"http://127.0.0.1:{port}"
    icon_image = make_icon_image()

    def on_open(icon, item):
        webbrowser.open(url)

    def on_quit(icon, item):
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Open Dashboard", on_open, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit FIFA Predictor", on_quit),
    )

    icon = pystray.Icon(
        name="FIFA Predictor",
        icon=icon_image,
        title="FIFA World Cup 2026 Predictor",
        menu=menu,
    )
    icon.run()


def main() -> None:
    port = find_free_port(5000)

    # Import the Flask app now (safe: FIFA_DATA_DIR already set above)
    # Use a nested import so the path fix above takes effect first.
    from webapp.app import app as flask_app

    # Disable Flask's reloader -- it spawns a second process which
    # breaks the single-exe model and the tray icon.
    flask_thread = threading.Thread(
        target=lambda: flask_app.run(
            host="127.0.0.1",
            port=port,
            debug=False,
            use_reloader=False,
        ),
        daemon=True,
        name="flask",
    )
    flask_thread.start()

    # Open the browser only once Flask is confirmed to be listening.
    if wait_for_server(port, timeout=20):
        webbrowser.open(f"http://127.0.0.1:{port}")
    else:
        # Flask took too long -- open the browser anyway and let
        # it show a loading error rather than silently doing nothing.
        webbrowser.open(f"http://127.0.0.1:{port}")

    # Tray icon runs on the main thread until the user clicks Quit.
    # When run() returns, the daemon Flask thread dies with the process.
    run_tray(port)


if __name__ == "__main__":
    main()
