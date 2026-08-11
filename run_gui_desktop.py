# run_gui_desktop.py
# v1.3 desktop entrypoint: boots the unchanged Streamlit engine on 127.0.0.1:8520 in a background
# thread, waits for the port, then opens a native pywebview (WebView2) window on it. Window close
# = clean shutdown. Prefers the bundled WebView2 Fixed Version runtime (webview2_fixed\) so the
# app is browser-less and air-gap self-contained; falls back to an installed Evergreen runtime
# only if the bundle is absent. Set DISC5_FORCE_BUNDLED_WEBVIEW=1 to make that fallback a hard
# failure (used in the browser-less verification test).

import os, sys, socket, threading, time, traceback

PORT = 8520
URL = f"http://127.0.0.1:{PORT}"
TITLE = "DISC5 Re-ID"
WAIT_S = 120  # first CPU launch loads torch; be generous


def _base_dir():
    # onedir: exe folder (for logs, webview user-data); _MEIPASS for bundled resources
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def _log(msg):
    try:
        with open(os.path.join(_base_dir(), "disc5_desktop_log.txt"), "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg + "\n")
    except Exception:
        pass


def _find_bundled_webview2():
    """Return the folder containing msedgewebview2.exe inside the bundled Fixed Version
    runtime, handling both flat layout and the one-level versioned subfolder the .cab
    expansion produces. None if not bundled."""
    root = _resource("webview2_fixed")
    if not os.path.isdir(root):
        return None
    if os.path.isfile(os.path.join(root, "msedgewebview2.exe")):
        return root
    for entry in sorted(os.listdir(root)):
        sub = os.path.join(root, entry)
        if os.path.isfile(os.path.join(sub, "msedgewebview2.exe")):
            return sub
    return None


def _configure_webview2():
    """Point the WebView2 loader at the bundled runtime and a writable user-data folder.
    Must run before pywebview creates the window."""
    bundled = _find_bundled_webview2()
    if bundled:
        os.environ["WEBVIEW2_BROWSER_EXECUTABLE_FOLDER"] = bundled
        _log(f"Using bundled WebView2 Fixed Version runtime: {bundled}")
    else:
        if os.environ.get("DISC5_FORCE_BUNDLED_WEBVIEW") == "1":
            raise RuntimeError(
                "Bundled WebView2 runtime (webview2_fixed\\) not found and "
                "DISC5_FORCE_BUNDLED_WEBVIEW=1 forbids Evergreen fallback.")
        _log("Bundled WebView2 runtime not found; relying on installed Evergreen runtime.")
    # Writable browser profile dir â€” never inside the (possibly read-only) install folder.
    udf = os.path.join(os.environ.get("LOCALAPPDATA", _base_dir()), "DISC5_ReID", "webview2_data")
    os.makedirs(udf, exist_ok=True)
    os.environ["WEBVIEW2_USER_DATA_FOLDER"] = udf


def _run_streamlit():
    # Streamlit's bootstrap installs a SIGTERM handler, which Python forbids outside the
    # main thread. Neuter signal.signal inside this thread; shutdown is os._exit anyway.
    import signal as _signal
    _orig_signal = _signal.signal
    def _safe_signal(sig, handler):
        try:
            return _orig_signal(sig, handler)
        except ValueError:
            return None
    _signal.signal = _safe_signal
    app = _resource("disc5_gui_app.py")
    sys.argv = ["streamlit", "run", app,
                "--server.port", str(PORT),
                "--server.address", "127.0.0.1",   # local only: the login gate is an
                # accountability control, not a network-security boundary â€” do not expose it
                "--server.headless", "true",
                "--server.fileWatcherType", "none",
                "--client.toolbarMode", "minimal",
                "--browser.gatherUsageStats", "false",
                "--global.developmentMode", "false"]
    try:
        try:
            from streamlit.web import cli as stcli
        except Exception:
            from streamlit import cli as stcli  # older streamlit
        stcli.main()
    except SystemExit:
        pass  # streamlit calls sys.exit(); swallow it inside the thread
    except Exception:
        _log("Streamlit thread crashed:\n" + traceback.format_exc())


def _wait_for_port(timeout_s=WAIT_S):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def main():
    _log("=== launch ===")
    _configure_webview2()

    t = threading.Thread(target=_run_streamlit, daemon=True)
    t.start()

    if not _wait_for_port():
        _log(f"Server did not open port {PORT} within {WAIT_S}s â€” aborting.")
        os._exit(1)

    import webview  # import late so env vars above are set first
    webview.settings["ALLOW_DOWNLOADS"] = True  # CSV/PNG export buttons are dead without this
    webview.create_window(TITLE, URL, width=1280, height=820,
                          resizable=True, confirm_close=False)
    webview.start(debug=False)  # blocks until the window is closed

    _log("Window closed â€” shutting down.")
    os._exit(0)  # daemon streamlit thread dies with the process; no console lingers


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _log("Launcher crashed:\n" + traceback.format_exc())
        os._exit(1)


