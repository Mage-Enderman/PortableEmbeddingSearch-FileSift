import os
import sys
import time
import socket
import threading
import subprocess
import webbrowser
import uvicorn
from pathlib import Path


def find_free_port(start_port: int = 8501) -> int:
    for port in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start_port


def start_server(port: int):
    # Ensure current dir is in sys.path
    root_dir = str(Path(__file__).resolve().parent)
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)

    from server.api import app
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def launch_edge_app(url: str, width: int = 860, height: int = 740) -> bool:
    """Launches Microsoft Edge in dedicated standalone App Mode (looks like a native window)."""
    edge_paths = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for p in edge_paths:
        if os.path.exists(p):
            cmd = [p, f"--app={url}", f"--window-size={width},{height}"]
            try:
                subprocess.Popen(cmd)
                return True
            except Exception as e:
                print(f"[Desktop] Failed to launch Edge app mode: {e}")
    return False


def main():
    port = find_free_port(8501)
    url = f"http://127.0.0.1:{port}"

    # Start FastAPI backend in background thread
    server_thread = threading.Thread(target=start_server, args=(port,), daemon=True)
    server_thread.start()

    # Wait for server to bind
    for _ in range(30):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
        except Exception:
            pass
        time.sleep(0.1)

    print(f"=======================================================")
    print(f"  FileSift • Portable Embedding Search is running!    ")
    print(f"  URL: {url}                                          ")
    print(f"  Powered by Google DeepMind's EmbeddingGemma 2       ")
    print(f"=======================================================")

    # Check if user requested browser-only mode
    if "--browser" in sys.argv:
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down FileSift...")
            sys.exit(0)

    # Try pywebview first for native embedded window
    opened = False
    try:
        import webview
        # pywebview on Windows uses WebView2 natively
        window = webview.create_window(
            "FileSift • Semantic File Search",
            url=url,
            width=860,
            height=740,
            min_size=(600, 500),
            background_color="#0d0f12",
        )
        opened = True
        webview.start(gui="edgechromium")
    except Exception as e:
        print(f"[Desktop] pywebview not active ({e}), falling back to Edge App Mode...")
        opened = False

    if not opened:
        # Launch standalone Edge App Window
        if not launch_edge_app(url):
            # Fallback to standard browser
            webbrowser.open(url)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down FileSift...")
            sys.exit(0)


if __name__ == "__main__":
    main()
