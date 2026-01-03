#!/usr/bin/env python3

import logging
import os
import sys
from pathlib import Path

# Add the src directory to Python path to enable imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import load_config
from services.pgn_writer import PGNWriter
from services.repertoire_builder import RepertoireBuilder


class ConfigLogger:
    """Handles configuration and environment logging."""

    def __init__(self, logger=None, env=None):
        self.logger = logger or logging.getLogger(__name__)
        self.env = env or os.environ

    def log_environment_warnings(self) -> None:
        if self.env.get("LICHESS_API_KEY"):
            return

        print("\n" + "=" * 60)
        print("⚠️  WARNING: No Lichess API key detected!")
        print("Without an API key, you may experience rate limiting.")
        print("To get an API key:")
        print("1. Visit: https://lichess.org/account/oauth/token")
        print("2. Create a .env file in the project root")
        print("3. Add: LICHESS_API_KEY=your_key_here")
        print("=" * 60 + "\n")

    def log_configuration(self, config) -> None:
        self.logger.info(f"Rating brackets: {', '.join(map(str, config.ratings))}")
        self.logger.info(f"Time controls: {config.time_control}")


def setup_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def _output_path_for_side(base_path: str, side: str) -> str:
    """Return the base output path (side is now handled in PGNWriter)."""
    path = Path(base_path)
    if not path.is_absolute():
        path = Path("outputs") / path

    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def run_for_side(config, side: str, initial_moves):
    logger = logging.getLogger(__name__)
    side_label = side.capitalize()

    logger.info(f"Building {side} repertoire...")
    logger.info(f"Initial moves: {initial_moves}")

    builder = RepertoireBuilder(config, side=side)
    logger.info(f"Building {side} repertoire tree...")
    repertoire_lines = builder.build_repertoire()

    if not repertoire_lines:
        return False

    roots = [line.root for line in repertoire_lines]
    realized_initial_moves = [line.initial_moves for line in repertoire_lines]

    if len(repertoire_lines) != len(initial_moves):
        remaining = realized_initial_moves.copy()
        skipped = []
        for sequence in initial_moves:
            if sequence in remaining:
                remaining.remove(sequence)
            else:
                skipped.append(sequence)
        if skipped:
            logger.warning(
                "Skipped %d initial sequences due to build errors or transpositions: %s",
                len(skipped),
                skipped,
            )

    writer = PGNWriter(config, side=side)
    output_path = _output_path_for_side(config.output_file, side)
    if roots:
        builder.compute_terminal_advantages(roots)
        builder.evaluate_and_combine_terminal_scores(roots)
    logger.info(
        "Writing %s repertoire (one PGN per initial move) using base %s...",
        side,
        output_path,
    )
    output_paths = writer.write_repertoire(roots, output_path, realized_initial_moves)
    if output_paths:
        logger.info("Created %d PGN file(s) for %s", len(output_paths), side)

    print(f"{side_label} Repertoire Statistics:")
    print(writer.get_statistics_summary(roots, realized_initial_moves))
    return True


def main():
    from config import parse_arguments

    args = parse_arguments()

    log_level = getattr(logging, args.log_level.upper())
    setup_logging(log_level)
    logger = logging.getLogger(__name__)

    try:
        logger.info("Loading configuration...")
        config = load_config(args)

        config_logger = ConfigLogger(logger)
        config_logger.log_environment_warnings()
        config_logger.log_configuration(config)

        if config.initial_moves_white:
            run_for_side(config, "white", config.initial_moves_white)

        if config.initial_moves_black:
            run_for_side(config, "black", config.initial_moves_black)

        if not config.initial_moves_white and not config.initial_moves_black:
            logger.error(
                "No repertoires to build - both initial_moves_white and initial_moves_black are empty"
            )
            return 1

        logger.info("Repertoire generation complete!")
        return 0

    except KeyboardInterrupt:
        logger.info("Generation interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Error generating repertoire: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
