#!/usr/bin/env python3

import sys
import logging
from pathlib import Path
from config import load_config
from repertoire_builder import RepertoireBuilder
from pgn_writer import PGNWriter


def setup_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Loading configuration...")
        config = load_config()
        
        # Check for API key
        import os
        if not os.getenv("LICHESS_API_KEY"):
            print("\n" + "="*60)
            print("⚠️  WARNING: No Lichess API key detected!")
            print("Without an API key, you may experience rate limiting.")
            print("To get an API key:")
            print("1. Visit: https://lichess.org/account/oauth/token")
            print("2. Create a .env file in the project root")
            print("3. Add: LICHESS_API_KEY=your_key_here")
            print("="*60 + "\n")
        
        logger.info(f"Building {config.side} repertoire...")
        logger.info(f"Initial moves: {config.initial_moves}")
        logger.info(f"Depth: {config.depth}")
        logger.info(f"Rating range: {config.min_rating}-{config.max_rating}")
        logger.info(f"Time controls: {config.time_control}")
        
        builder = RepertoireBuilder(config)
        
        logger.info("Building repertoire tree...")
        roots = builder.build_repertoire()
        
        if not roots:
            logger.error("No repertoire could be built")
            return 1
        
        writer = PGNWriter(config)
        
        logger.info(f"Writing repertoire to {config.output_file}...")
        writer.write_repertoire(roots, config.output_file)
        
        print(writer.get_statistics_summary(roots))
        
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