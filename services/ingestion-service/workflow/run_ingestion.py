import argparse
import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings
from app.schemas import RunIngestionRequest
from app.service import IngestionService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ingestion workflow.")
    parser.add_argument("--raw-dir", default=None, help="Local folder containing raw files.")
    parser.add_argument(
        "--source-root-in-preprocessing",
        default=None,
        help="Path prefix visible from preprocessing-service container.",
    )
    parser.add_argument("--preprocessing-base-url", default=None)
    parser.add_argument("--embedding-base-url", default=None)
    parser.add_argument("--embedding-batch-size", type=int, default=None)
    parser.add_argument("--pattern", action="append", default=[])
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--non-recursive", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        if args.recursive and args.non_recursive:
            raise ValueError("Use only one of --recursive or --non-recursive")

        settings = Settings.from_env()
        service = IngestionService(settings=settings)

        recursive: bool | None = None
        if args.recursive:
            recursive = True
        elif args.non_recursive:
            recursive = False

        request = RunIngestionRequest(
            raw_dir=args.raw_dir,
            source_root_in_preprocessing=args.source_root_in_preprocessing,
            preprocessing_base_url=args.preprocessing_base_url,
            embedding_base_url=args.embedding_base_url,
            embedding_batch_size=args.embedding_batch_size,
            recursive=recursive,
            patterns=args.pattern or None,
            dry_run=args.dry_run,
        )

        result = service.run_ingestion(request)
        for item in result.results:
            if item.status == "ok":
                print(
                    f"[OK] {Path(item.file_path).name}: chunks={item.chunks_count} indexed={item.indexed_count}"
                )
            elif item.status == "dry_run":
                print(f"[DRY-RUN] {item.file_path} -> {item.source_path}")
            else:
                print(f"[ERROR] {Path(item.file_path).name}: {item.error}", file=sys.stderr)

        summary = {
            "documents_processed": result.documents_processed,
            "documents_failed": result.documents_failed,
            "chunks_total": result.chunks_total,
            "chunks_indexed": result.chunks_indexed,
            "failed_files": result.failed_files,
        }
        print("Ingestion summary:")
        print(json.dumps(summary, indent=2))
        return 1 if result.documents_failed else 0
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

