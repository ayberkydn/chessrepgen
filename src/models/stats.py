from dataclasses import dataclass


@dataclass
class MoveStats:
    uci: str
    san: str
    white_wins: int
    draws: int
    black_wins: int
    total_games: int

    @property
    def white_win_rate(self) -> float:
        if self.total_games == 0:
            return 0.0
        return self.white_wins / self.total_games

    @property
    def black_win_rate(self) -> float:
        if self.total_games == 0:
            return 0.0
        return self.black_wins / self.total_games

    @property
    def draw_rate(self) -> float:
        if self.total_games == 0:
            return 0.0
        return self.draws / self.total_games

    def win_rate(self, for_white: bool) -> float:
        return self.white_win_rate if for_white else self.black_win_rate

    def advantage(
        self,
        for_white: bool,
        min_games_threshold: int | None = None,
        padding_strength: int | None = None,
    ) -> float:
        """Difference between the player's and opponent's win percentages.

        If thresholds are provided, applies shrinkage towards balanced results
        for moves with low game counts.
        """
        player_win_rate = self.win_rate(for_white)
        opponent_win_rate = self.win_rate(not for_white)
        raw_advantage = player_win_rate - opponent_win_rate

        # Apply shrinkage if all conditions are met
        if (
            min_games_threshold is not None
            and padding_strength is not None
            and self.total_games < min_games_threshold
        ):
            weight = self.total_games / (self.total_games + padding_strength)
            return weight * raw_advantage

        return raw_advantage
