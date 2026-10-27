"""
Deep file opener for Windows: opens files at their matched page, timestamp, or line number.
Inspired by DigUp's moments and editors modules.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple
from core.extractors import VIDEO_EXTS, AUDIO_EXTS


def find_executable(names: List[str], win_relative_paths: Optional[List[str]] = None) -> Optional[str]:
    """Finds an executable in PATH or standard Windows install directories."""
    # 1. Check PATH
    for name in names:
        p = shutil.which(name)
        if p and os.path.exists(p):
            return p

    # 2. Check standard Windows directories
    if win_relative_paths:
        prefixes = [
            os.environ.get("LOCALAPPDATA", ""),
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.environ.get("APPDATA", ""),
        ]
        for rel in win_relative_paths:
            for prefix in prefixes:
                if not prefix:
                    continue
                full = os.path.normpath(os.path.join(prefix, rel))
                if os.path.exists(full):
                    return full

    return None


def get_detected_editor() -> Optional[Tuple[str, str]]:
    """
    Detects which code editor is available.
    Returns (editor_id, executable_path).
    """
    editors = [
        ("vscode", ["code.cmd", "code.exe"], ["Programs/Microsoft VS Code/bin/code.cmd", "Microsoft VS Code/bin/code.cmd"]),
        ("cursor", ["cursor.cmd", "cursor.exe"], ["Programs/cursor/resources/app/bin/cursor.cmd"]),
        ("windsurf", ["windsurf.cmd", "windsurf.exe"], ["Programs/Windsurf/bin/windsurf.cmd"]),
        ("notepad++", ["notepad++.exe"], ["Notepad++/notepad++.exe"]),
        ("sublime", ["subl.exe"], ["Sublime Text/subl.exe", "Sublime Text 3/subl.exe"]),
        ("zed", ["zed.exe"], ["Programs/Zed/bin/zed.exe"]),
    ]

    for editor_id, names, rel_paths in editors:
        exe = find_executable(names, rel_paths)
        if exe:
            return (editor_id, exe)
    return None


def open_code_at_line(path: str, line: int) -> bool:
    """Opens source code in detected editor at specified line number."""
    detected = get_detected_editor()
    if not detected:
        return False

    editor_id, exe = detected
    try:
        if editor_id in ("vscode", "cursor", "windsurf"):
            subprocess.Popen([exe, "-g", f"{path}:{line}"])
            return True
        elif editor_id in ("sublime", "zed"):
            subprocess.Popen([exe, f"{path}:{line}"])
            return True
        elif editor_id == "notepad++":
            subprocess.Popen([exe, f"-n{line}", path])
            return True
    except Exception as e:
        print(f"[Opener] Error launching editor {editor_id}: {e}")

    return False


def get_detected_media_player() -> Optional[Tuple[str, str]]:
    """Detects available video/audio players supporting timestamp jumping."""
    players = [
        ("vlc", ["vlc.exe"], ["VideoLAN/VLC/vlc.exe"]),
        ("mpv", ["mpv.exe"], ["mpv/mpv.exe"]),
        ("mpc-hc", ["mpc-hc64.exe", "mpc-hc.exe"], ["MPC-HC/mpc-hc64.exe", "K-Lite Codec Pack/MPC-HC64/mpc-hc64.exe"]),
    ]
    for player_id, names, rel_paths in players:
        exe = find_executable(names, rel_paths)
        if exe:
            return (player_id, exe)
    return None


def open_media_at_second(path: str, seconds: float) -> bool:
    """Opens video/audio in media player at specific start time."""
    detected = get_detected_media_player()
    if not detected:
        return False

    player_id, exe = detected
    try:
        if player_id == "vlc":
            subprocess.Popen([exe, f"--start-time={seconds:.1f}", path])
            return True
        elif player_id == "mpv":
            subprocess.Popen([exe, f"--start={seconds:.1f}", path])
            return True
        elif player_id == "mpc-hc":
            ms = int(seconds * 1000)
            subprocess.Popen([exe, path, "/start", str(ms)])
            return True
    except Exception as e:
        print(f"[Opener] Error launching media player {player_id}: {e}")

    return False


def open_pdf_at_page(path: str, page: int) -> bool:
    """Opens PDF at specific page in Edge or SumatraPDF."""
    sumatra = find_executable(["sumatrapdf.exe"], ["SumatraPDF/SumatraPDF.exe"])
    if sumatra:
        try:
            subprocess.Popen([sumatra, "-page", str(page), path])
            return True
        except Exception:
            pass

    # Fallback to Microsoft Edge (native on Windows 10/11) with #page=N
    edge = find_executable(
        ["msedge.exe"],
        [
            r"Microsoft\Edge\Application\msedge.exe",
        ]
    )
    if edge:
        try:
            file_url = Path(path).as_uri() + f"#page={page}"
            subprocess.Popen([edge, file_url])
            return True
        except Exception as e:
            print(f"[Opener] Error launching Edge PDF at page: {e}")

    return False


def open_result_at(
    path: str,
    page: Optional[int] = None,
    seconds: Optional[float] = None,
    line: Optional[int] = None,
) -> bool:
    """
    Dispatches to the most specific opener available,
    falling back to standard Windows default association.
    """
    norm_path = os.path.normpath(path)
    if not os.path.exists(norm_path):
        return False

    ext = Path(norm_path).suffix.lower()

    # 1. Code line
    if line is not None and line > 0:
        if open_code_at_line(norm_path, line):
            return True

    # 2. PDF page
    if ext == ".pdf" and page is not None and page > 0:
        if open_pdf_at_page(norm_path, page):
            return True

    # 3. Media second
    if (ext in VIDEO_EXTS or ext in AUDIO_EXTS) and seconds is not None and seconds > 0:
        if open_media_at_second(norm_path, seconds):
            return True

    # 4. Standard default app
    try:
        os.startfile(norm_path)
        return True
    except Exception as e:
        print(f"[Opener] Fallback os.startfile failed: {e}")
        return False
