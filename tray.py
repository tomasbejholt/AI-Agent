import os
import sys
import threading
import webbrowser
import winreg

from PIL import Image, ImageDraw
import pystray

FLASK_PORT = 5000
APP_NAME = "Tomas Chat"
CHAT_URL = f"http://127.0.0.1:{FLASK_PORT}"


def create_icon_image():
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill=(99, 102, 241))
    draw.ellipse([size - 20, size - 20, size - 6, size - 6], fill=(99, 102, 241))
    draw.text((18, 14), "G", fill="white")
    return img


def start_flask():
    import logging
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    from app import app
    app.run(port=FLASK_PORT, debug=False, use_reloader=False)


def open_chat(icon=None, item=None):
    webbrowser.open(CHAT_URL)


def get_pythonw():
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return pythonw if os.path.exists(pythonw) else sys.executable


def is_autostart_enabled():
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ,
        )
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False


def set_autostart(enabled):
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE,
    )
    if enabled:
        exe = get_pythonw()
        script = os.path.abspath(__file__)
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe}" "{script}"')
    else:
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
    winreg.CloseKey(key)


def toggle_autostart(icon, item):
    set_autostart(not is_autostart_enabled())
    icon.update_menu()


def quit_app(icon, item):
    icon.stop()
    os._exit(0)


def build_menu():
    return pystray.Menu(
        pystray.MenuItem("Öppna chat", open_chat, default=True),
        pystray.MenuItem(
            "Starta med Windows",
            toggle_autostart,
            checked=lambda item: is_autostart_enabled(),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Avsluta", quit_app),
    )


def main():
    set_autostart(True)

    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    icon = pystray.Icon(APP_NAME, create_icon_image(), APP_NAME, build_menu())
    icon.run()


if __name__ == "__main__":
    main()
