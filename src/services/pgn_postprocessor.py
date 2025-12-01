"""PGN postprocessor for removing comments and pruning variations."""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path

import chess.pgn

logger = logging.getLogger(__name__)


class PGNPostprocessor:
    """Postprocess PGN files by removing comments and pruning variations."""

    def __init__(
        self,
        max_depth: int | None = None,
        min_games: int = 0,
        remove_advantage: bool = False,
        remove_terminal_advantage: bool = False,
        remove_popularity: bool = False,
        remove_game_count: bool = False,
        remove_alternatives: bool = False,
        initial_lines: list[str] | None = None,
    ):
        self.max_depth = max_depth
        self.min_games = min_games
        self.remove_advantage = remove_advantage
        self.remove_terminal_advantage = remove_terminal_advantage
        self.remove_popularity = remove_popularity
        self.remove_game_count = remove_game_count
        self.remove_alternatives = remove_alternatives

        normalized_moves: list[str] = []
        display_moves: list[str] = []
        for moves in initial_lines or []:
            normalized = _normalize_initial_moves(moves)
            if normalized:
                normalized_moves.append(normalized)
                display_moves.append(" ".join(moves.split()))

        self.initial_lines = normalized_moves
        self.initial_lines_display = display_moves

    def process(self, input_path: str, output_path: str) -> list[str]:
        """Load PGN, apply transformations, write output file(s)."""
        input_file = Path(input_path)
        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        games = []
        with open(input_file, "r", encoding="utf-8") as f:
            while True:
                game = chess.pgn.read_game(f)
                if game is None:
                    break
                games.append(game)

        if not games:
            logger.warning("No games found in %s", input_path)
            return []

        selected_groups = self._select_games_by_initial_lines(games)
        selected_games_count = sum(len(group) for _, group in selected_groups)

        if self.initial_lines:
            logger.info(
                "Processing %d game(s) from %s (filtered from %d)",
                selected_games_count,
                input_path,
                len(games),
            )
        else:
            logger.info("Processing %d game(s) from %s", len(games), input_path)

        written_paths: list[str] = []
        base_output = Path(output_path)
        suffix = base_output.suffix or ".pgn"
        stem = base_output.stem if base_output.suffix else base_output.name
        parent = base_output.parent
        multi_output = len(selected_groups) > 1

        for index, (initial_moves_label, game_group) in enumerate(selected_groups):
            for game in game_group:
                self._process_game(game)

            output_file = (
                parent
                / f"{stem}-{_slugify_initial_moves(initial_moves_label, f'line-{index + 1}')}{suffix}"
                if multi_output
                else base_output
            )

            self._write_games(game_group, output_file)
            written_paths.append(str(output_file))

        logger.info("Wrote processed PGN to %s", ", ".join(written_paths))
        return written_paths

    def _select_games_by_initial_lines(
        self, games: list[chess.pgn.Game]
    ) -> list[tuple[str, list[chess.pgn.Game]]]:
        """Return game groups filtered by requested initial moves."""
        if not self.initial_lines:
            return [("", games)]

        game_data: list[tuple[chess.pgn.Game, str]] = []
        for game in games:
            header_moves = _normalize_initial_moves(
                game.headers.get("InitialMoves", "")
            )
            game_data.append((game, header_moves))

        selections: list[tuple[str, list[chess.pgn.Game]]] = []
        missing: list[str] = []

        for idx, moves_key in enumerate(self.initial_lines):
            matches: list[chess.pgn.Game] = []
            tokens_key = moves_key.split()

            for game, header_moves in game_data:
                header_match = header_moves == moves_key
                prefix_match = _game_contains_prefix(game, tokens_key)
                if header_match or prefix_match:
                    # Clone so pruning does not affect other outputs
                    clone = _clone_game(game)
                    if prefix_match and not header_match:
                        _prune_to_initial_line(clone, tokens_key)
                    matches.append(clone)

            if not matches:
                label = (
                    self.initial_lines_display[idx]
                    if idx < len(self.initial_lines_display)
                    else moves_key
                )
                missing.append(label)
                continue

            label = (
                self.initial_lines_display[idx]
                if idx < len(self.initial_lines_display)
                else moves_key
            )
            selections.append((label, matches))

        if missing:
            raise ValueError(
                f"Initial moves not found in input file: {', '.join(missing)}"
            )

        return selections

    def _process_game(self, game: chess.pgn.Game) -> None:
        """Apply all transformations to a single game."""
        # Get repertoire side from headers
        side = game.headers.get("RepertoireSide", "white")
        is_white = side == "white"

        # Get initial moves count from headers
        initial_moves_str = game.headers.get("InitialMoves", "")
        initial_ply = len(initial_moves_str.split()) if initial_moves_str.strip() else 0

        # Apply post-pruning first (needs comments for game count)
        if self.max_depth is not None or self.min_games > 0:
            self._post_prune_node(game, initial_ply, is_white)

        # Ensure lines end with the repertoire player's move
        self._prune_incomplete_player_responses(game, is_white)

        # Filter comments after pruning if any removal options are set
        if any(
            [
                self.remove_advantage,
                self.remove_terminal_advantage,
                self.remove_popularity,
                self.remove_game_count,
                self.remove_alternatives,
            ]
        ):
            self._filter_comments(game)

    def _post_prune_node(
        self, node: chess.pgn.GameNode, initial_ply: int, is_white: bool
    ) -> None:
        """Recursively prune variations based on depth and game count."""
        # Process variations in reverse to safely remove during iteration
        variations = list(node.variations)
        for variation in variations:
            # Calculate player-move depth
            # ply = total half-moves from game start
            # player_depth = number of moves made by repertoire player after initial position
            current_ply = _get_ply(variation)
            ply_after_initial = current_ply - initial_ply

            if is_white:
                # White moves on odd plies (1, 3, 5, ...) after initial
                # Player depth = ceil(ply_after_initial / 2)
                player_depth = (ply_after_initial + 1) // 2
            else:
                # Black moves on even plies (2, 4, 6, ...) after initial
                # Player depth = ply_after_initial // 2
                player_depth = ply_after_initial // 2

            should_prune = False
            prune_reason = ""

            # Check depth limit
            if self.max_depth is not None and player_depth > self.max_depth:
                should_prune = True
                prune_reason = f"depth {player_depth} > {self.max_depth}"

            # Check game count limit
            if not should_prune and self.min_games > 0:
                game_count = _parse_game_count(variation.comment)
                if game_count is not None and game_count < self.min_games:
                    should_prune = True
                    prune_reason = f"games {game_count} < {self.min_games}"

            if should_prune:
                logger.debug(
                    "Pruning variation at ply %d (player depth %d): %s",
                    current_ply,
                    player_depth,
                    prune_reason,
                )
                # Remove all children but keep this move
                variation.variations.clear()
            else:
                # Recurse into children
                self._post_prune_node(variation, initial_ply, is_white)

    def _prune_incomplete_player_responses(
        self, node: chess.pgn.GameNode, is_white: bool
    ) -> None:
        """Remove leaf variations that end on an opponent move."""
        variations = list(node.variations)
        for variation in variations:
            self._prune_incomplete_player_responses(variation, is_white)

            # If this variation is a leaf and it's the player's turn, the line ends
            # with an opponent move. Remove the variation so the line ends with the player.
            board = variation.board()
            if not variation.variations and board.turn == is_white:
                node.variations.remove(variation)

    def _filter_comments(self, node: chess.pgn.GameNode) -> None:
        """Recursively filter specific fields from comments."""
        if node.comment:
            node.comment = self._filter_comment_fields(node.comment)
        for variation in node.variations:
            self._filter_comments(variation)

    def _filter_comment_fields(self, comment: str) -> str:
        """Remove specific fields from a comment string.

        Handles both old format (A: 5.0, T: 10.0) and new format (A:5.0,T:10.0).
        """
        if not comment:
            return comment

        # Normalize whitespace around colons and commas for easier parsing
        # This handles both "A: 5.0, T: 10.0" and "A:5.0,T:10.0"
        import re

        # Strategy: Find all field:value pairs, filter them, then reconstruct
        # Fields are: A:, T:, P:, G:, Alts:

        filtered_parts = []

        # Find A: field
        if not self.remove_advantage:
            match = re.search(r"A:\s*([+-]?\d+\.?\d*)", comment)
            if match:
                filtered_parts.append(f"A:{match.group(1)}")

        # Find T: field
        if not self.remove_terminal_advantage:
            match = re.search(r"T:\s*([+-]?\d+\.?\d*)", comment)
            if match:
                filtered_parts.append(f"T:{match.group(1)}")

        # Find P: field
        if not self.remove_popularity:
            match = re.search(r"P:\s*(\d+\.?\d*%)", comment)
            if match:
                filtered_parts.append(f"P:{match.group(1)}")

        # Find G: field
        if not self.remove_game_count:
            match = re.search(r"G:\s*(\d+)", comment)
            if match:
                filtered_parts.append(f"G:{match.group(1)}")

        # Find Alts: field (can contain commas, so match until end or next capital letter field)
        if not self.remove_alternatives:
            match = re.search(r"Alts:\s*([^A-Z].*?)(?=\s*[A-Z]:|$)", comment)
            if match:
                alts_value = match.group(1).strip().rstrip(",")
                if alts_value:
                    filtered_parts.append(f"Alts:{alts_value}")

        return ",".join(filtered_parts)

    def _write_games(self, games: list[chess.pgn.Game], output_file: Path) -> None:
        """Write processed games to disk."""
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            for i, game in enumerate(games):
                exporter = chess.pgn.FileExporter(f)
                game.accept(exporter)
                if i < len(games) - 1:
                    f.write("\n")


def _get_ply(node: chess.pgn.GameNode) -> int:
    """Get the ply (half-move number) of a node."""
    ply = 0
    current = node
    while current.parent is not None:
        ply += 1
        current = current.parent
    return ply


def _parse_game_count(comment: str) -> int | None:
    """Parse game count from comment string (G: N format)."""
    if not comment:
        return None
    match = re.search(r"G:\s*(\d+)", comment)
    if match:
        return int(match.group(1))
    return None


def _normalize_initial_moves(moves: str) -> str:
    """Normalize initial move string for comparison."""
    tokens = []
    for raw_token in re.sub(r"[;,]", " ", moves).strip().split():
        token = raw_token.strip()
        if not token:
            continue

        # Drop leading move numbers (e.g., "1.", "1...") possibly attached to the move ("1.e4")
        token = re.sub(r"^\d+\.{0,3}", "", token)
        token = token.lstrip(".")
        if not token or re.fullmatch(r"\d+\.{1,3}", token):
            continue

        token = token.strip(",;").rstrip("?!+#")
        if token:
            tokens.append(token.lower())

    return " ".join(tokens)


def _game_contains_prefix(game: chess.pgn.Game, target_tokens: list[str]) -> bool:
    """Return True if any line (mainline or variation) starts with target_tokens."""
    if not target_tokens:
        return False

    board = game.board()
    return _node_contains_prefix(game, board, target_tokens, [])


def _node_contains_prefix(
    node: chess.pgn.GameNode,
    board: chess.Board,
    target_tokens: list[str],
    current_tokens: list[str],
) -> bool:
    for variation in list(node.variations):
        san_token = _normalize_initial_moves(board.san(variation.move)).split()
        if not san_token:
            continue

        token = san_token[0]
        candidate = current_tokens + [token]

        if not _tokens_match_prefix(target_tokens, candidate):
            continue

        if len(candidate) == len(target_tokens):
            return True

        board.push(variation.move)
        if _node_contains_prefix(variation, board, target_tokens, candidate):
            return True
        board.pop()

    return False


def _tokens_match_prefix(target_tokens: list[str], candidate_tokens: list[str]) -> bool:
    """Return True if candidate is a prefix of target."""
    if len(candidate_tokens) > len(target_tokens):
        return False
    return target_tokens[: len(candidate_tokens)] == candidate_tokens


def _clone_game(game: chess.pgn.Game) -> chess.pgn.Game:
    """Deep clone a PGN game via serialization."""
    buffer = io.StringIO()
    exporter = chess.pgn.FileExporter(buffer)
    game.accept(exporter)
    buffer.seek(0)
    cloned = chess.pgn.read_game(buffer)
    if cloned is None:
        raise ValueError("Failed to clone PGN game")
    return cloned


def _prune_to_initial_line(game: chess.pgn.Game, target_tokens: list[str]) -> None:
    """Prune a game's tree to keep only branches matching the target prefix."""
    board = game.board()
    _prune_node_to_prefix(game, board, target_tokens, 0)


def _prune_node_to_prefix(
    node: chess.pgn.GameNode,
    board: chess.Board,
    target_tokens: list[str],
    idx: int,
) -> bool:
    """Prune variations in place, keeping only those matching target_tokens prefix.

    Returns True if the current node still contains a path matching the target.
    """
    if idx >= len(target_tokens):
        return True

    kept = False
    for variation in list(node.variations):
        san_tokens = _normalize_initial_moves(board.san(variation.move)).split()
        move_token = san_tokens[0] if san_tokens else ""

        if move_token != target_tokens[idx]:
            node.variations.remove(variation)
            continue

        board.push(variation.move)
        if _prune_node_to_prefix(variation, board, target_tokens, idx + 1):
            kept = True
        else:
            node.variations.remove(variation)
        board.pop()

    return kept


def _slugify_initial_moves(moves: str, fallback: str) -> str:
    """Create a filesystem-friendly label from an initial move string."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", moves.strip()).strip("-").lower()
    return slug or fallback
