from typing import Any, Dict, List, Tuple

from blaseball_mike import chronicler

Game = Dict[str, Any]  # Chronicler game data object


class Bets:
    def __init__(self, bot, season: int, interactive: bool = True):
        self.bot = bot
        self.season = season
        self.current_day = 0
        self.interactive = interactive
        self.games: List[Game] = []
        self.payout_cache: Dict[Tuple[int, float, float], int] = {}
        self.refresh()

    def refresh(self) -> None:
        if self.interactive:
            self.bot.logger.info("Getting bet data ...")
        self.games = chronicler.get_games(
            season=self.season, finished=True, order='asc')
        self.payout_cache = {}
        if self.interactive:
            self.bot.logger.info(" OK ({:0.2f} days retrieved.)".format(self.current_day))

    def set_current_day(self, day):
        self.current_day = day

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
        print("won games (as % of bettable games): {:0.3f}%".format(
            len(won_bet_games) / len(good_bet_games)))

        profit_per_day = net_profit / self.current_day
        print(f"profit per blaseball-day: {profit_per_day}")

    def payout(self, bet: int = 1000,
               threshold: float = 0.50,
               efficiency: float = 1.00) -> int:
        """
        Scale the resulting answer against the reported betting effiency!
        e.g. an efficiency of 14/24 (14 days per reality-day) is 0.58%.
        Efficiency is clamped to [0.00, 1.00] and rounded to two figures.
        """
        efficiency = round(max(0.0, min(efficiency, 1.0)), 2)
        key = (bet, threshold, efficiency)
        if key not in self.payout_cache:
            value = sum(
                self.betting_result(game, bet, threshold=threshold)
                for game in self.games
            )
            self.payout_cache[key] = round(efficiency * value)
        return self.payout_cache[key]

    def calculate_threshold(self) -> float:
        scores = []
        for i in range(0, 51):
            threshold = (50 + i) / 100
            payout = self.payout(threshold=threshold)
            scores.append((payout, threshold))
        scores = sorted(scores, reverse=True)
        return scores[0][1]
