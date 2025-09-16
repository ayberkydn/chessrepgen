# Chess Repertoire Generator

A modular, maintainable chess repertoire generator that analyzes Lichess and master games data to build optimal opening repertoires.

## Features

- Generates chess repertoires based on actual game statistics from Lichess and master databases
- Selects best moves using expected score (wins + 0.5 * draws)
- Caches API responses in SQLite for faster subsequent runs
- Outputs repertoires as PGN files with variation branches
- Highly configurable via YAML files and command-line arguments
- Supports both white and black repertoires

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd chessrepgen
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. **IMPORTANT: Set up Lichess API key** (Highly Recommended):
   
   ⚠️ **Without an API key, you will experience severe rate limiting!**
   
   - Get your FREE API key from: https://lichess.org/account/oauth/token
   - Copy `.env.example` to `.env` and add your key:
```bash
cp .env.example .env
# Edit .env and add your API key: LICHESS_API_KEY=your_key_here
```
   
   The tool will warn you if no API key is detected at startup.

## Configuration

The generator uses a layered configuration system:
1. Default values
2. YAML configuration file (`config.yaml`)
3. Command-line arguments (highest priority)

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `side` | Side to generate repertoire for (`white` or `black`) | `white` |
| `initial_moves` | Starting positions in SAN notation | `["e4"]` |
| `time_control` | Time controls to consider | `["rapid", "blitz"]` |
| `depth` | Maximum depth of repertoire tree | `10` |
| `min_rating` | Minimum rating for Lichess games | `1600` |
| `max_rating` | Maximum rating for Lichess games | `2200` |
| `min_popularity` | Minimum popularity for opponent moves (0-1) | `0.1` |
| `min_master_popularity` | Minimum popularity for player moves in master games (0-1) | `0.1` |
| `output_file` | Output PGN file path | `repertoire.pgn` |
| `cache_file` | SQLite cache database path | `chess_cache.db` |
| `cache_expiry_days` | Days before cache entries expire | `30` |

## Usage

### Basic Usage

Generate a repertoire using the default configuration:
```bash
python src/main.py
```

### With Custom Configuration File

```bash
python src/main.py --config my_config.yaml
```

### Command-Line Override Examples

Generate a black repertoire:
```bash
python src/main.py --side black --initial-moves "e4 e5" "d4 d5"
```

Adjust rating range and depth:
```bash
python src/main.py --min-rating 1800 --max-rating 2400 --depth 12
```

Specify output file:
```bash
python src/main.py --output my_repertoire.pgn
```

### Full Example

```bash
python src/main.py \
  --side white \
  --initial-moves "e4 e5 Nf3" "e4 c5" \
  --time-control rapid blitz classical \
  --depth 8 \
  --min-rating 2000 \
  --max-rating 2500 \
  --min-popularity 0.05 \
  --min-master-popularity 0.15 \
  --output white_repertoire.pgn
```

## How It Works

1. **Starting Position**: Begin from specified initial moves
2. **Data Fetching**: Query Lichess Explorer API for position statistics
3. **Move Selection**:
   - **Player's Turn**: Select moves from master games with popularity ≥ `min_master_popularity`, choosing best by expected score
   - **Opponent's Turn**: Include all moves with popularity ≥ `min_popularity`
4. **Tree Building**: Recursively analyze positions until termination conditions are met
5. **Output**: Generate PGN file with all variations

### Termination Conditions

The repertoire tree stops expanding when any of these conditions are met:
- Maximum depth is reached
- Less than 200 master games at the position
- Less than 1000 Lichess games at the position
- No master games data available

## Output

The generator produces a PGN file with:
- Main variations and sub-variations
- Move annotations with win rates and game counts
- Headers with repertoire metadata
- Statistics summary in console output

## Project Structure

```
chessrepgen/
├── src/
│   ├── config.py              # Configuration handling
│   ├── lichess_client.py      # Lichess API client
│   ├── cache.py               # SQLite caching
│   ├── evaluator.py           # Move evaluation logic
│   ├── repertoire_builder.py  # Tree building logic
│   ├── pgn_writer.py          # PGN output formatting
│   └── main.py                # Main entry point
├── config.yaml                # Default configuration
├── .env.example               # Example environment file
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

## Requirements

- Python 3.7+
- Internet connection for Lichess API access
- (Optional) Lichess API key for better rate limits

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.