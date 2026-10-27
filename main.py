import sys
import argparse
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import config
from core.index_store import IndexStore
from core.indexer import IndexManager
from core.searcher import HybridSearcher


def cli_index():
    print(f"[FileSift] Starting index on chosen folders: {config.chosen_folders}")
    indexer = IndexManager.get_instance()
    indexer.start_indexing(full_reindex=False)
    while indexer.is_running():
        p = indexer.progress.to_dict()
        print(f"\r[{p['status'].upper()}] {p['files_indexed']}/{p['total_files']} files ({p['progress_pct']}%) - {p['current_file'][:40]}", end="", flush=True)
        import time
        time.sleep(0.5)
    print("\n[FileSift] Indexing complete!")


def cli_search(query: str, kind: str = "all"):
    print(f"[FileSift] Searching for: '{query}' (kind: {kind})...")
    searcher = HybridSearcher()
    results = searcher.search(query=query, kind_filter=kind, limit=10)
    if not results:
        print("[FileSift] No matches found.")
        return

    print(f"\nFound {len(results)} matches:\n")
    for idx, r in enumerate(results, 1):
        print(f"{idx}. [{r.kind.upper()}] {r.filename} ({r.score_pct}% match)")
        print(f"   Location: {r.loc_label} | Path: {r.path}")
        clean_snip = r.snippet.replace("<mark>", "**").replace("</mark>", "**")
        print(f"   Excerpt: {clean_snip}\n")


def main():
    parser = argparse.ArgumentParser(description="FileSift: Portable EmbeddingGemma 2 Semantic File Search")
    parser.add_argument("--index", action="store_true", help="Run indexing on chosen folders via CLI")
    parser.add_argument("--search", type=str, help="Search files using natural language via CLI")
    parser.add_argument("--kind", type=str, default="all", help="Filter by file kind (all, docs, code, notes, images)")
    parser.add_argument("--browser", action="store_true", help="Run in browser mode instead of native window")
    args = parser.parse_args()

    if args.index:
        cli_index()
    elif args.search:
        cli_search(args.search, args.kind)
    else:
        # Launch desktop app
        import desktop
        desktop.main()


if __name__ == "__main__":
    main()
