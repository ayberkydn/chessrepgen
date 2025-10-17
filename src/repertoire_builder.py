import logging
import chess


from dataclasses import dataclass
from collections import deque
from lichess_client import LichessClient
from cache import ChessCache
from evaluator import MoveEvaluator, MoveStats

logger = logging.getLogger(__name__)


@dataclass
class RepertoireNode:
    board: chess.Board
    move: chess.Move | None
    move_san: str | None
    stats: MoveStats | None
    depth: int
    is_player_turn: bool
    termination_reason: str | None
    children: list["RepertoireNode"]
    comment: str = ""
    position_stats: dict | None = None  # Store position statistics for terminal nodes

    def add_child(self, child: "RepertoireNode"):
        self.children.append(child)


class RepertoireBuilder:
    def __init__(self, config, side: str):
        self.config = config
        self.side = side
        proxies = [
            "http://opsmwgon:c9splz41ut21@142.111.48.253:7030",
            "http://opsmwgon:c9splz41ut21@31.59.20.176:6754",
            "http://opsmwgon:c9splz41ut21@38.170.176.177:5572",
            "http://opsmwgon:c9splz41ut21@198.23.239.134:6540",
            "http://opsmwgon:c9splz41ut21@45.38.107.97:6014",
            "http://opsmwgon:c9splz41ut21@107.172.163.27:6543",
            "http://opsmwgon:c9splz41ut21@64.137.96.74:6641",
            "http://opsmwgon:c9splz41ut21@216.10.27.159:6837",
            "http://opsmwgon:c9splz41ut21@142.111.67.146:5611",
            "http://opsmwgon:c9splz41ut21@142.147.128.93:6593",
        ]
        self.client = LichessClient(proxies=proxies)
        self.cache = ChessCache(config.cache_file)
        self.evaluator = MoveEvaluator(config, self.cache, side)
        self.is_white = side == "white"
        self.visited_positions: set[str] = set()

    def parse_initial_moves(self, moves_str: str) -> list[chess.Move]:
        board = chess.Board()
        moves = []

        move_parts = moves_str.strip().split()
        for move_str in move_parts:
            try:
                move = board.parse_san(move_str)
                moves.append(move)
                board.push(move)
            except:
                try:
                    move = chess.Move.from_uci(move_str)
                    if move in board.legal_moves:
                        moves.append(move)
                        board.push(move)
                    else:
                        logger.error(f"Illegal move: {move_str}")
                        raise ValueError(f"Illegal move: {move_str}")
                except:
                    logger.error(f"Invalid move format: {move_str}")
                    raise ValueError(f"Invalid move format: {move_str}")

        return moves

    def _augment_master_games(self, fen: str, master_data: dict) -> dict:
        """Augment master games with high-rated Lichess games."""
        if not self.config.augment_master_games or not master_data:
            return master_data

        # Calculate total master games count
        total_master_games = (
            master_data.get("white", 0)
            + master_data.get("draws", 0)
            + master_data.get("black", 0)
        )

        # Only augment if master games count is lower than min_master_games
        if total_master_games >= self.config.min_master_games:
            logger.debug(
                f"Skipping augmentation - sufficient master games ({total_master_games} >= {self.config.min_master_games})"
            )
            return master_data

        # Get high-rated Lichess games for augmentation
        augment_data = self.cache.get_lichess_stats(
            fen,
            self.config.augment_min_rating,
            3000,  # Max rating for augmentation
            self.config.augment_time_controls,
        )

        if not augment_data:
            # Fetch from API if not cached
            augment_data = self.client.get_lichess_games(
                fen,
                [
                    self.config.augment_min_rating + i * 200
                    for i in range((3000 - self.config.augment_min_rating) // 200 + 1)
                ],
                self.config.augment_time_controls,
            )

            if augment_data:
                self.cache.set_lichess_stats(
                    fen,
                    augment_data,
                    self.config.augment_min_rating,
                    3000,
                    self.config.augment_time_controls,
                )

        if not augment_data:
            return master_data

        # Combine master and augmentation data
        augmented_data = master_data.copy()

        # Add augmentation games to totals
        augmented_data["white"] = master_data.get("white", 0) + augment_data.get(
            "white", 0
        )
        augmented_data["draws"] = master_data.get("draws", 0) + augment_data.get(
            "draws", 0
        )
        augmented_data["black"] = master_data.get("black", 0) + augment_data.get(
            "black", 0
        )

        # Combine moves
        master_moves = {move["uci"]: move for move in master_data.get("moves", [])}
        augment_moves = {move["uci"]: move for move in augment_data.get("moves", [])}

        combined_moves = {}
        for uci in set(master_moves.keys()) | set(augment_moves.keys()):
            master_move = master_moves.get(uci, {})
            augment_move = augment_moves.get(uci, {})

            combined_move = {
                "uci": uci,
                "san": master_move.get("san") or augment_move.get("san"),
                "white": master_move.get("white", 0) + augment_move.get("white", 0),
                "draws": master_move.get("draws", 0) + augment_move.get("draws", 0),
                "black": master_move.get("black", 0) + augment_move.get("black", 0),
            }
            combined_moves[uci] = combined_move

        augmented_data["moves"] = list(combined_moves.values())

        logger.debug(
            f"Augmented master games for {fen[:20]}... (insufficient: {total_master_games} < {self.config.min_master_games}) with {len(augment_moves)} high-rated moves"
        )

        return augmented_data

    def get_position_data(self, fen: str) -> dict:
        cached_master = self.cache.get_master_stats(fen)
        cached_lichess = self.cache.get_lichess_stats(
            fen,
            self.config.min_rating,
            self.config.max_rating,
            self.config.time_control,
        )

        if cached_master and cached_lichess:
            # Check if we need to augment master games
            if self.config.augment_master_games:
                cached_master = self._augment_master_games(fen, cached_master)
            return {"master": cached_master, "lichess": cached_lichess}

        api_data = self.client.get_position_stats(
            fen,
            self.config.min_rating,
            self.config.max_rating,
            self.config.time_control,
        )

        if not cached_master and api_data["master"]:
            self.cache.set_master_stats(fen, api_data["master"])

        if not cached_lichess and api_data["lichess"]:
            self.cache.set_lichess_stats(
                fen,
                api_data["lichess"],
                self.config.min_rating,
                self.config.max_rating,
                self.config.time_control,
            )

        master_data = cached_master or api_data["master"]

        # Augment master games if enabled
        if self.config.augment_master_games and master_data:
            master_data = self._augment_master_games(fen, master_data)

        return {"master": master_data, "lichess": cached_lichess or api_data["lichess"]}

    def _set_no_candidate_moves_termination(
        self,
        node: RepertoireNode,
        master_data: dict | None,
        lichess_data: dict | None,
        is_player_turn: bool,
    ) -> None:
        """Annotate node when no candidate moves are available."""
        total_master_games = 0
        if master_data and master_data.get("moves"):
            for move_data in master_data["moves"]:
                total_master_games += move_data.get("games", 0)

        if is_player_turn:
            if total_master_games < self.config.min_master_games:
                reason = f"Insufficient master games ({total_master_games} < {self.config.min_master_games})"
            elif total_master_games > 0:
                reason = "No master moves meet popularity threshold"
            else:
                reason = "No master game data available"
        else:
            has_lichess_moves = bool(lichess_data and lichess_data.get("moves"))
            has_master_moves = bool(master_data and master_data.get("moves"))
            if not has_lichess_moves:
                if not has_master_moves:
                    reason = "No opponent move data available"
                else:
                    reason = "No opponent moves meet popularity threshold"
            else:
                reason = "No opponent moves meet popularity threshold"

        node.termination_reason = reason
        if node.comment:
            if reason not in node.comment:
                node.comment = f"{node.comment} | {reason}"
        else:
            node.comment = reason

    def build_repertoire(self) -> list[RepertoireNode]:
        roots = []

        initial_moves_list = (
            self.config.initial_moves_white
            if self.side == "white"
            else self.config.initial_moves_black
        )

        try:
            for initial_moves_str in initial_moves_list:
                logger.info(f"Building repertoire for: {initial_moves_str}")

                try:
                    board = chess.Board()
                    initial_moves = self.parse_initial_moves(initial_moves_str)

                    for move in initial_moves:
                        board.push(move)

                    root = self.build_node_breadth_first(board)
                    if root:
                        roots.append(root)

                except Exception as e:
                    logger.error(
                        f"Error building repertoire for {initial_moves_str}: {e}"
                    )
                    continue
        finally:
            pass  # No Stockfish engine to clean up

        return roots

    def build_node_breadth_first(self, board: chess.Board) -> RepertoireNode | None:
        """Build repertoire tree using breadth-first search approach."""
        fen = board.fen()
        if fen in self.visited_positions:
            logger.debug(f"Position already visited: {fen[:20]}...")
            return None

        self.visited_positions.add(fen)
        is_player_turn = (board.turn == chess.WHITE) == self.is_white

        # Create root node
        root = RepertoireNode(
            board=board.copy(),
            move=None,
            move_san=None,
            stats=None,
            depth=0,
            is_player_turn=is_player_turn,
            termination_reason=None,
            children=[],
        )

        # Check for immediate termination conditions
        if board.is_game_over():
            result = board.result()
            root.termination_reason = f"Game over: {result}"
            root.comment = f"Game ends: {result}"
            return root

        position_data = self.get_position_data(fen)
        master_data = position_data["master"]
        lichess_data = position_data["lichess"]
        root.position_stats = {"master": master_data, "lichess": lichess_data}

        should_stop, reason = self.evaluator.should_terminate(
            0, master_data, lichess_data, board
        )

        if should_stop:
            root.termination_reason = reason
            root.comment = reason
            return root

        queue = deque([root])

        while queue:
            node = queue.popleft()

            if node.termination_reason:
                continue

            current_board = node.board.copy()
            current_is_player_turn = node.is_player_turn

            # Get candidate moves for this position
            candidate_moves = self.evaluator.evaluate_position(
                node.position_stats["master"],
                node.position_stats["lichess"],
                current_is_player_turn,
                current_board,
                node.depth,
            )

            if not candidate_moves:
                master_data = node.position_stats["master"]
                lichess_data = node.position_stats["lichess"]
                self._set_no_candidate_moves_termination(
                    node, master_data, lichess_data, current_is_player_turn
                )
                continue

            # Process each candidate move
            child_added = False
            for move_stats in candidate_moves:
                try:
                    child_board = current_board.copy()
                    move = chess.Move.from_uci(move_stats.uci)

                    if move not in child_board.legal_moves:
                        logger.warning(f"Illegal move from API: {move_stats.uci}")
                        continue

                    san = child_board.san(move)
                    child_board.push(move)

                    child_fen = child_board.fen()
                    if child_fen in self.visited_positions:
                        logger.debug(
                            f"Child position already visited: {child_fen[:20]}..."
                        )
                        continue

                    self.visited_positions.add(child_fen)

                    # Calculate child depth (only increment on player's turn)
                    child_depth = node.depth
                    if current_is_player_turn:
                        child_depth += 1

                    # Create child node
                    child_is_player_turn = (
                        child_board.turn == chess.WHITE
                    ) == self.is_white
                    child_node = RepertoireNode(
                        board=child_board.copy(),
                        move=move,
                        move_san=san,
                        stats=move_stats,
                        depth=child_depth,
                        is_player_turn=child_is_player_turn,
                        termination_reason=None,
                        children=[],
                    )

                    # Check termination conditions for child
                    child_terminated = False

                    if child_board.is_game_over():
                        result = child_board.result()
                        child_node.termination_reason = f"Game over: {result}"
                        child_node.comment = f"Game ends: {result}"
                        child_terminated = True
                    else:
                        child_position_data = self.get_position_data(child_fen)
                        child_node.position_stats = {
                            "master": child_position_data["master"],
                            "lichess": child_position_data["lichess"],
                        }

                        should_stop_child, reason_child = (
                            self.evaluator.should_terminate(
                                child_depth,
                                child_position_data["master"],
                                child_position_data["lichess"],
                                child_board,
                            )
                        )

                        if should_stop_child:
                            child_node.termination_reason = reason_child
                            child_node.comment = reason_child
                            child_terminated = True

                    # Add statistics comment
                    score = move_stats.expected_score(self.is_white)
                    stats_comment = f"Score: {score:.1%}"
                    if child_node.termination_reason:
                        child_node.comment = (
                            f"{stats_comment} | {child_node.termination_reason}"
                        )
                    else:
                        child_node.comment = stats_comment

                    # Add child to parent
                    node.add_child(child_node)
                    child_added = True

                    # If child is not terminated and we haven't exceeded max depth, continue exploring
                    if not child_terminated and child_depth <= self.config.depth:
                        queue.append(child_node)

                except Exception as e:
                    logger.error(f"Error processing move {move_stats.uci}: {e}")
                    continue

            if not child_added and not node.termination_reason:
                node.termination_reason = "Transposes to previously analyzed line"
                if node.comment:
                    if node.termination_reason not in node.comment:
                        node.comment = f"{node.comment} | {node.termination_reason}"
                else:
                    node.comment = node.termination_reason

        return root
