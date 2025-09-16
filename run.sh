#!/bin/bash

# Chess Repertoire Generator Runner Script

# Default to using config from project root
CONFIG_PATH="${CONFIG_PATH:-config.yaml}"

# Change to src directory to run the script
cd "$(dirname "$0")/src" || exit 1

# Run with uv, passing all arguments
uv run python main.py --config "../$CONFIG_PATH" "$@"