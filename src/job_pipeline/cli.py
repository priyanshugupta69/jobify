"""Subprocess entry point for heavy scheduled stages.

The scheduler shells out to ``python -m job_pipeline.cli <stage>`` so it
can wrap the call in ``subprocess.run(..., timeout=N)`` and SIGKILL on
timeout. Each subcommand simply imports the matching service function
and calls it — no logic duplication.
"""
from __future__ import annotations

import sys

from job_pipeline.logging_config import configure_logging


def _run_full() -> None:
    from job_pipeline.services import full
    full.run_full()


def _run_discover() -> None:
    from job_pipeline.services import discover
    discover.run()


def _run_score() -> None:
    from job_pipeline.services import score
    score.run()


def _run_tailor() -> None:
    from job_pipeline.services import tailor
    tailor.run()


def _run_extract_urls() -> None:
    from job_pipeline.services import extract_urls
    extract_urls.run()


def _run_cleanup() -> None:
    from job_pipeline.services import cleanup
    cleanup.run()


def _run_batch() -> None:
    from job_pipeline.services import batch
    batch.run()


def _run_report() -> None:
    from job_pipeline.services import report
    report.send_daily()


COMMANDS: dict[str, callable] = {
    "full": _run_full,
    "discover": _run_discover,
    "score": _run_score,
    "tailor": _run_tailor,
    "extract-urls": _run_extract_urls,
    "cleanup": _run_cleanup,
    "batch": _run_batch,
    "report": _run_report,
}


def main() -> None:
    configure_logging()
    from job_pipeline.patches import apply_patches
    apply_patches()
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(
            f"Usage: python -m job_pipeline.cli <{'|'.join(COMMANDS)}>",
            file=sys.stderr,
        )
        sys.exit(2)
    COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()
