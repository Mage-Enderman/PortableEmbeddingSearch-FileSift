import json
import os
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

# Determine portable root directory (the parent of core)
APP_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = APP_ROOT / "data"
MODELS_DIR = DATA_DIR / "models"
DB_PATH = DATA_DIR / "index.sqlite"
CONFIG_FILE = DATA_DIR / "config.json"

# Ensure data directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Set HF cache to portable folder so weights stay inside the app directory
os.environ["HF_HOME"] = str(MODELS_DIR)
os.environ["TORCH_HOME"] = str(MODELS_DIR)

DEFAULT_EXCLUDED_PATTERNS = [
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
    ".tox",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".cache",
    "$RECYCLE.BIN",
    "System Volume Information",
]

DEFAULT_EXTENSIONS = [
    # Text and Documents
    ".txt", ".md", ".markdown", ".rst", ".org", ".typ", ".rtf", ".odt", ".html", ".htm",
    ".pdf", ".docx",
    # Spreadsheets and Presentations
    ".xlsx", ".ods", ".pptx", ".odp", ".csv", ".tsv",
    # Programming & Web
    ".py", ".js", ".ts", ".jsx", ".tsx", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".xml", ".sql",
    ".rs", ".go", ".c", ".cpp", ".h", ".hpp", ".cs", ".java", ".kt", ".swift",
    ".sh", ".bash", ".ps1", ".bat", ".cmd", ".env.example",
    # Images (modern & standard formats)
    ".png", ".jpg", ".jpeg", ".webp", ".avif", ".jxl", ".heic", ".heif", ".bmp", ".gif", ".tiff", ".tif",
    # Audio
    ".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac",
    # Video
    ".mp4", ".mkv", ".avi", ".mov", ".webm"
]


class AppConfig(BaseModel):
    chosen_folders: List[str] = Field(default_factory=list)
    excluded_patterns: List[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDED_PATTERNS))
    allowed_extensions: List[str] = Field(default_factory=lambda: list(DEFAULT_EXTENSIONS))
    embedding_model: str = "google/embeddinggemma-2"
    embedding_dim: int = 512  # 256, 512, or 768 (EmbeddingGemma 2 Matryoshka dimension)
    batch_size: int = 16
    max_file_size_mb: int = 25
    auto_reindex_on_startup: bool = True
    theme: str = "dark"
    device: str = "auto"  # "auto", "cuda", or "cpu"

    @classmethod
    def load(cls) -> "AppConfig":
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls(**data)
            except Exception as e:
                print(f"[Config] Error loading config file, using defaults: {e}")
        config = cls()
        config.save()
        return config

    def save(self) -> None:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.model_dump(), f, indent=2)
        except Exception as e:
            print(f"[Config] Error saving config: {e}")

    def add_folder(self, folder_path: str) -> bool:
        normalized = os.path.normpath(os.path.abspath(folder_path))
        if os.path.isdir(normalized) and normalized not in self.chosen_folders:
            self.chosen_folders.append(normalized)
            self.save()
            return True
        return False

    def remove_folder(self, folder_path: str) -> bool:
        normalized = os.path.normpath(os.path.abspath(folder_path))
        if normalized in self.chosen_folders:
            self.chosen_folders.remove(normalized)
            self.save()
            return True
        return False


# Global config instance
config = AppConfig.load()
