from blaseball_mike import chronicler
from typing import Any, Dict, Iterable, List, Optional, Tuple, cast

# Aliases for SIBR structures
Game = Dict[str, Any]  # Chronicler game data object
Player = Dict[str, Any]  # Reference player data object
StatGroup = Dict[str, Any]  # Reference stats group (group/type/totalSplits/splits)
StatSplit = Dict[str, Any]  # Reference stats split; e.g. StatGroup['splits'][0]
PlayerStats = Dict[str, Any]  # Reference player stats object; e.g. StatSplit['stat']

# Aliases for Blaseball structures
ItemTier = Dict[str, int]  # contains 'price' and 'amount' values
UpgradeData = Dict[str, List[ItemTier]]  # e.g. blackHoleTiers -> List[ItemTier]

# Mapping of snacks to number owned.
Snaxfolio = Dict[str, int]
# Analysis of a Batter's payouts; ('hits', 'home_runs', 'stolen_bases', 'total')
BatterPayout = Dict[str, int]
# Full analysis of a payout.
BatterAnalysis = Tuple[BatterPayout, StatSplit, Player]
# Upgrade analysis dict (cost, dx, ratio, etc.)
PurchaseAnalysis = Dict[str, Any]

class Bets:
    def __init__(self) -> None:
        self.games = chronicler.get_games(season=13, finished=True, order='asc')

    @classmethod
    def betting_coefficient(cls, odds: float) -> float:
        """Return the betting coefficient for given odds"""
        if odds <= 0.5:
            return 2.0 + 0.0015 * ((100 * (0.5 - odds)) ** 2.2)
        return (3.206 / (1 + (0.443 * (odds - 0.5)) ** 0.95) - 1.206)

    @classmethod
    def betting_payout(cls, odds: float, bet: int) -> int:
        """Return the payout for winning a bet with the given odds."""
        return round(bet * cls.betting_coefficient(odds))

    @classmethod
    def betting_odds(cls, game: Game) -> float:
        """Return the best betting odds for a given game."""
        return float(max(game['data']['homeOdds'], game['data']['awayOdds']))

    @classmethod
    def favored_team_won(cls, game: Game) -> bool:
        """Return true if the favored team won this game."""
        hometeam_favored = (game['data']['homeOdds'] >= game['data']['awayOdds'])
        hometeam_won = (game['data']['homeScore'] > game['data']['awayScore'])
        return bool(hometeam_favored == hometeam_won)

    @classmethod
    def betting_result(cls, game: Game, bet: int, threshold: float = 0.50) -> int:
        """Return money won or lost using the max-bet strategy on this game."""
        odds = cls.betting_odds(game)

        # If below threshold, don't spend or win
        if odds < threshold:
            return 0

        winnings = 0
        if cls.favored_team_won(game):
            winnings = cls.betting_payout(odds, bet)
        return winnings - bet

    def statistics(self, bet: int = 1000, threshold: float = 0.50) -> None:
        good_bet_games = list(filter(
            lambda g: self.betting_odds(g) >= threshold, self.games
        ))
        won_bet_games = list(filter(self.favored_team_won, good_bet_games))
        net_profit = sum(self.betting_result(
            game, bet, threshold=threshold) for game in self.games)
        print(f"total games: {len(self.games)}")
        print(f"games with favored odds above threshold: {len(good_bet_games)}")
        print(f"games where the favored team above threshold won: {len(won_bet_games)}")
        print("bettable games: {:0.3f}%".format(len(good_bet_games) / len(self.games)))
        print("won games: {:0.3f}%".format(len(won_bet_games) / len(self.games)))
        print("won games (as % of bettable games): {:0.3f}%".format(len(won_bet_games) / len(good_bet_games)))
        print(f"net profit: {net_profit}")
        #
        game_days = len(self.games) / 12
        profit_per_day = net_profit / game_days
        #
        print(f"profit per blaseball-day: {profit_per_day}")

    def payout(self, bet: int = 1000, threshold: float = 0.50) -> int:
        """
        Given a particular bet size, simulate a betting strategy where a
        user always bets their maximum if the favored team has odds
        above a specified threshold.
        """
        return sum(
            self.betting_result(game, bet, threshold=threshold)
            for game in self.games
        )

    def calculate_threshold(self) -> float:
        scores = []
        for i in range(0, 51):
            threshold = (50 + i) / 100
            payout = self.payout(threshold=threshold)
            scores.append((payout, threshold))
        scores = sorted(scores, reverse=True)
        return scores[0][1]