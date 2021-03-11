import sqlite3


def initialize(db):
    with sqlite3.connect(db) as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS hitterstatstable (
                                                id INTEGER NOT NULL PRIMARY KEY, 
                                                player_id INTEGER NOT NULL,
                                                day INTEGER NOT NULL, 
                                                hits INTEGER NOT NULL, 
                                                home_runs INTEGER NOT NULL,
                                                stolen_bases INTEGER NOT NULL);""")
        c.execute("""CREATE TABLE IF NOT EXISTS rulesblogtable (
                                                id INTEGER NOT NULL PRIMARY KEY,
                                                pull_date DATETIME NOT NULL,
                                                page_text TEXT NOT NULL);""")
        c.execute("""CREATE TABLE IF NOT EXISTS usersnaxignoretable (
                                                id INTEGER NOT NULL PRIMARY KEY, 
                                                user_id INTEGER NOT NULL, 
                                               ignore_list TEXT NOT NULL);""")
        c.execute("""CREATE TABLE IF NOT EXISTS usersnaxtable (
                                                id    INTEGER NOT NULL,
                                                user_id   INTEGER NOT NULL UNIQUE,
                                                snake_oil INTEGER DEFAULT 0,
                                                fresh_popcorn INTEGER DEFAULT 0,
                                                stale_popcorn INTEGER DEFAULT 0,
                                                chips INTEGER DEFAULT 0,
                                                burger    INTEGER DEFAULT 0,
                                                hot_dog   INTEGER DEFAULT 0,
                                                seeds INTEGER DEFAULT 0,
                                                pickles   INTEGER DEFAULT 0,
                                                slushies  INTEGER DEFAULT 0,
                                                wet_pretzel   INTEGER DEFAULT 0,
                                                PRIMARY KEY(id)
                                            );""")
        c.close()


class SnaxInstance:
    def __init__(self, user_id, snake_oil, fresh_popcorn, stale_popcorn,
                 chips, burger, hot_dog, seeds, pickles, slushies, wet_pretzel):
        self.user_id = user_id
        self.snake_oil = snake_oil
        self.fresh_popcorn = fresh_popcorn
        self.stale_popcorn = stale_popcorn
        self.chips = chips
        self.burger = burger
        self.hot_dog = hot_dog
        self.seeds = seeds
        self.pickles = pickles
        self.slushies = slushies
        self.wet_pretzel = wet_pretzel

    def get_as_dict(self):
        return {'hot_dog': self.hot_dog, 'seeds': self.seeds, 'pickles': self.pickles,
                'slushies': self.slushies, 'wet_pretzel': self.wet_pretzel, 'snake_oil': self.snake_oil,
                'fresh': self.fresh_popcorn, "stale": self.stale_popcorn,
                "burgers": self.burger, "chips": self.chips}

