"""Command-line entry point for validating and running pipeline manifests."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from apps.local_model_runtime import LocalFoundryDeploymentRuntime

from .manifest import ManifestError, load_pipeline
from .runner import PipelineRunner
from .stages import built_in_registry


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate or run a Tiger pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "run"):
        action = subparsers.add_parser(command)
        action.add_argument("manifest", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    registry = built_in_registry()
    try:
        pipeline = load_pipeline(args.manifest, registry)
        if args.command == "validate":
            print(f"{pipeline.manifest.metadata.name}: {' -> '.join(pipeline.order)}")
            return 0
        asyncio.run(
            PipelineRunner(
                pipeline,
                registry,
                services={"foundry": LocalFoundryDeploymentRuntime()},
            ).run()
        )
        return 0
    except ManifestError as error:
        print(f"Manifest error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Pipeline interrupted", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"Pipeline failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())