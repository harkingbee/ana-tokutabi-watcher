from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO", fmt: str = "json") -> None:
    lvl = getattr(logging, level.upper(), logging.INFO)
    if fmt == "json":
        try:
            import structlog

            structlog.configure(
                processors=[
                    structlog.contextvars.merge_contextvars,
                    structlog.processors.add_log_level,
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.JSONRenderer(ensure_ascii=False),
                ],
                wrapper_class=structlog.make_filtering_bound_logger(lvl),
                logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
                cache_logger_on_first_use=True,
            )
            # 標準loggingもstructlog経由に
            logging.basicConfig(level=lvl, stream=sys.stdout, force=True)
        except ImportError:
            logging.basicConfig(level=lvl, stream=sys.stdout, force=True)
    else:
        logging.basicConfig(
            level=lvl,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stdout,
            force=True,
        )


def get_logger(name: str):
    try:
        import structlog

        return structlog.get_logger(name)
    except ImportError:
        return logging.getLogger(name)
