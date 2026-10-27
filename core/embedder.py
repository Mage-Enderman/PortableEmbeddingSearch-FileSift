import io
import os
import tempfile
import torch
import numpy as np
from PIL import Image
from typing import List, Optional, Union, Tuple
from pathlib import Path
from core.config import MODELS_DIR, config
from core.extractors import IMAGE_EXTS, AUDIO_EXTS, VIDEO_EXTS, format_timestamp


class EmbeddingGemmaEngine:
    _instance: Optional["EmbeddingGemmaEngine"] = None

    def __init__(self, model_name: str = "google/embeddinggemma-2", dim: int = 512, preferred_device: Optional[str] = None):
        self.model_name = model_name
        self.dim = dim
        self.device = self.resolve_device(preferred_device or config.device)
        self.model = None
        self._is_loading = False
        print(f"[EmbeddingGemma] Initializing engine on device: {self.device}")

    @classmethod
    def get_instance(cls) -> "EmbeddingGemmaEngine":
        if cls._instance is None:
            cls._instance = cls(
                model_name=config.embedding_model,
                dim=config.embedding_dim,
                preferred_device=config.device,
            )
        return cls._instance

    @staticmethod
    def resolve_device(pref: str) -> str:
        pref = (pref or "auto").lower().strip()
        if pref == "cuda":
            return "cuda" if torch.cuda.is_available() else "cpu"
        elif pref == "cpu":
            return "cpu"
        else:  # "auto"
            return "cuda" if torch.cuda.is_available() else "cpu"

    def get_device_info(self) -> dict:
        cuda_avail = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if cuda_avail else None
        vram_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 1) if cuda_avail else 0
        return {
            "current_device": self.device,
            "preferred_device": config.device,
            "cuda_available": cuda_avail,
            "gpu_name": gpu_name,
            "vram_gb": vram_gb,
        }

    def switch_device(self, new_pref: str) -> str:
        resolved = self.resolve_device(new_pref)
        self.device = resolved
        config.device = new_pref
        config.save()
        if self.model is not None:
            print(f"[EmbeddingGemma] Moving model to {self.device}...")
            self.model.to(self.device)
        return self.device

    def is_loaded(self) -> bool:
        return self.model is not None

    def load_model(self) -> None:
        """Loads EmbeddingGemma 2 with selective text backbone configuration."""
        if self.model is not None or self._is_loading:
            return

        self._is_loading = True
        try:
            print(f"[EmbeddingGemma] Loading model {self.model_name}...")
            from sentence_transformers import SentenceTransformer

            # EmbeddingGemma 2 requires bfloat16 or float32 (float16 can overflow)
            dtype = torch.bfloat16 if (self.device == "cuda" and torch.cuda.is_bf16_supported()) else torch.float32

            # Load model with cache_folder in ./data/models for portability
            self.model = SentenceTransformer(
                self.model_name,
                cache_folder=str(MODELS_DIR),
                model_kwargs={"torch_dtype": dtype},
                device=self.device,
            )
            print(f"[EmbeddingGemma] Model {self.model_name} successfully loaded.")
        except Exception as e:
            print(f"[EmbeddingGemma] Error loading {self.model_name}: {e}")
            raise e
        finally:
            self._is_loading = False

    def embed_query(self, query: str, is_code: bool = False) -> np.ndarray:
        """Embeds a search query using EmbeddingGemma 2's task prompt prefix."""
        if self.model is None:
            self.load_model()

        # Official EmbeddingGemma 2 query task instructions
        if is_code:
            task_prompt = f"task: code retrieval | query: {query}"
        else:
            task_prompt = f"task: search result | query: {query}"

        # Embedding with Matryoshka dimension truncation & L2 normalization
        vec = self.model.encode(
            task_prompt,
            truncate_dim=self.dim,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vec, dtype=np.float32)

    def embed_image(self, image_input: Union[str, Path, Image.Image, bytes]) -> np.ndarray:
        """Embeds an image visually into the unified 512d embedding space."""
        if self.model is None:
            self.load_model()

        if isinstance(image_input, (str, Path)):
            img = Image.open(str(image_input)).convert("RGB")
        elif isinstance(image_input, bytes):
            img = Image.open(io.BytesIO(image_input)).convert("RGB")
        elif isinstance(image_input, Image.Image):
            img = image_input.convert("RGB")
        else:
            raise ValueError(f"Unsupported image input type: {type(image_input)}")

        vec = self.model.encode(
            img,
            truncate_dim=self.dim,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vec, dtype=np.float32)

    def embed_audio(self, audio_path: Union[str, Path]) -> np.ndarray:
        """Embeds an audio recording into the unified 512d embedding space."""
        if self.model is None:
            self.load_model()

        vec = self.model.encode(
            {"audio": str(audio_path)},
            truncate_dim=self.dim,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vec, dtype=np.float32)

    def embed_audio_slice(self, samples_16k: np.ndarray) -> np.ndarray:
        """Embeds a 16kHz mono audio slice into unified 512d space via temp wav file."""
        import soundfile as sf
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tmp_name = tf.name
        try:
            sf.write(tmp_name, samples_16k, 16000)
            return self.embed_audio(tmp_name)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass

    @staticmethod
    def extract_audio_windows(
        file_path: Union[str, Path],
        window_sec: float = 30.0,
        hop_sec: float = 15.0,
    ) -> List[Tuple[float, float, np.ndarray]]:
        """
        Extracts overlapping 30-second audio windows at 16kHz mono using PyAV.
        Works across all audio containers (.wav, .mp3, .m4a, .flac) and video soundtracks (.mp4, .mov, etc.).
        Returns list of (start_sec, end_sec, samples_16k).
        """
        import av
        try:
            container = av.open(str(file_path))
            astream = next((s for s in container.streams if s.type == "audio"), None)
            if not astream:
                container.close()
                return []

            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
            all_chunks = []
            for frame in container.decode(astream):
                res = resampler.resample(frame)
                if res:
                    items = res if isinstance(res, list) else [res]
                    for item in items:
                        all_chunks.append(item.to_ndarray())
            container.close()

            if not all_chunks:
                return []

            full_audio = np.concatenate(all_chunks, axis=1).squeeze()
            sr = 16000
            total_sec = len(full_audio) / sr

            windows = []
            t_start = 0.0
            while t_start < total_sec:
                t_end = min(total_sec, t_start + window_sec)
                idx_start = int(t_start * sr)
                idx_end = int(t_end * sr)
                slice_data = full_audio[idx_start:idx_end]
                if len(slice_data) > 0:
                    windows.append((t_start, t_end, slice_data))
                if t_end >= total_sec:
                    break
                t_start += hop_sec
            return windows
        except Exception as e:
            print(f"[EmbeddingGemma] Audio window extraction error on {file_path}: {e}")
            return []

    @staticmethod
    def extract_video_frames(
        file_path: Union[str, Path],
        interval_sec: float = 3.0,
        max_frames: int = 50,
    ) -> List[Tuple[float, Image.Image]]:
        """
        Extracts video frames every few seconds with their exact timestamp using PyAV.
        Returns list of (pts_sec, PIL.Image).
        """
        import av
        try:
            container = av.open(str(file_path))
            vstream = next((s for s in container.streams if s.type == "video"), None)
            if not vstream:
                container.close()
                return []

            frames = []
            target_time = 0.0
            for frame in container.decode(vstream):
                pts_sec = float(frame.pts * vstream.time_base) if frame.pts is not None else 0.0
                if pts_sec >= target_time:
                    frames.append((pts_sec, frame.to_image().convert("RGB")))
                    target_time += interval_sec
                    if len(frames) >= max_frames:
                        break
            container.close()
            return frames
        except Exception as e:
            print(f"[EmbeddingGemma] Video frame extraction error on {file_path}: {e}")
            return []

    def embed_video(self, video_path: Union[str, Path], num_frames: int = 4) -> np.ndarray:
        """Extracts representative frames using PyAV and embeds them into unified space."""
        frames_with_time = self.extract_video_frames(video_path, interval_sec=2.0, max_frames=num_frames)
        if not frames_with_time:
            return np.zeros(self.dim, dtype=np.float32)

        frames = [img for _, img in frames_with_time]
        frame_vecs = self.model.encode(
            frames,
            truncate_dim=self.dim,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        mean_vec = np.mean(frame_vecs, axis=0)
        norm = np.linalg.norm(mean_vec)
        if norm > 0:
            mean_vec = mean_vec / norm
        return np.asarray(mean_vec, dtype=np.float32)

    def embed_documents(self, formatted_docs: List[str], batch_size: int = 16) -> np.ndarray:
        """
        Embeds a list of document strings.
        formatted_docs should follow EmbeddingGemma 2's convention:
        'title: {title} | text: {content}'
        """
        if self.model is None:
            self.load_model()

        if not formatted_docs:
            return np.empty((0, self.dim), dtype=np.float32)

        vectors = self.model.encode(
            formatted_docs,
            batch_size=batch_size,
            truncate_dim=self.dim,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)
