#!/usr/bin/env python3
"""CLI entry point for PGN postprocessing."""

import logging
import os
import sys

# Add the src directory to Python path to enable imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import load_postprocess_config, parse_postprocess_arguments
from services.pgn_postprocessor import PGNPostprocessor


def setup_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    args = parse_postprocess_arguments()

    log_level = getattr(logging, args.log_level.upper())
    setup_logging(log_level)
    logger = logging.getLogger(__name__)

    try:
        logger.info("Loading configuration...")
        config = load_postprocess_config(args)

        logger.info("Input file: %s", config.input_file)
        if config.initial_lines:
            logger.info("Filtering initial moves: %s", ", ".join(config.initial_lines))
        if config.max_depth is not None:
            logger.info("Max depth: %d", config.max_depth)
        if config.min_games > 0:
            logger.info("Min games: %d", config.min_games)

        # Log granular comment removal options
        granular_options = []
        if config.remove_advantage:
            granular_options.append("advantage")
        if config.remove_terminal_advantage:
            granular_options.append("terminal advantage")
        if config.remove_popularity:
            granular_options.append("popularity")
        if config.remove_game_count:
            granular_options.append("game count")
        if config.remove_alternatives:
            granular_options.append("alternatives")
        if granular_options:
            logger.info("Removing comment fields: %s", ", ".join(granular_options))

        if config.add_move_indicators:
            logger.info(
                "Adding opponent move indicators based on terminal advantage deltas"
            )
        if config.prune_non_best_moves:
            logger.info("Pruning non-best repertoire moves before export")

        processor = PGNPostprocessor(
            max_depth=config.max_depth,
            min_games=config.min_games,
            prune_non_best_moves=config.prune_non_best_moves,
            remove_advantage=config.remove_advantage,
            remove_terminal_advantage=config.remove_terminal_advantage,
            remove_popularity=config.remove_popularity,
            remove_game_count=config.remove_game_count,
            remove_alternatives=config.remove_alternatives,
            initial_lines=config.initial_lines,
            add_move_indicators=config.add_move_indicators,
            good_threshold=config.good_threshold,
            inaccuracy_threshold=config.inaccuracy_threshold,
            mistake_threshold=config.mistake_threshold,
            blunder_threshold=config.blunder_threshold,
            use_nag_codes=config.use_nag_codes,
        )

        processor.process(
            config.input_file, config.input_file.replace(".pgn", "_processed.pgn")
        )

        logger.info("Postprocessing complete!")
        return 0

    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Error processing PGN: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
