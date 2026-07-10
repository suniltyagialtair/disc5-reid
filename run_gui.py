# run_gui.py
# PyInstaller entrypoint for the frozen Windows app. Boots the Streamlit server in-process
# against disc5_gui_app.py and opens the default browser. (The `streamlit` CLI can't be frozen
# directly; this calls its bootstrap API instead.)
import os, sys, threading, time, webbrowser

def _resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

def _open_browser(url, delay=3.0):
    time.sleep(delay)
    try: webbrowser.open(url)
    except Exception: pass

def main():
    app = _resource("disc5_gui_app.py")
    port = "8520"
    url = f"http://localhost:{port}"
    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()

    # Streamlit bootstrap (API differs slightly across versions; try modern then fallback)
    sys.argv = ["streamlit", "run", app,
                "--server.port", port,
                "--server.headless", "true",
                "--browser.gatherUsageStats", "false",
                "--global.developmentMode", "false"]
    try:
        from streamlit.web import cli as stcli
        sys.exit(stcli.main())
    except Exception:
        from streamlit import cli as stcli  # older streamlit
        sys.exit(stcli.main())

if __name__ == "__main__":
    main()
