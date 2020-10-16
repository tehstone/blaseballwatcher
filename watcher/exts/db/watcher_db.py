from playhouse.apsw_ext import *
from playhouse.migrate import *


class WatcherDB:
    _db = Proxy()
    _migrator = None
    @classmethod
    def start(cls, db_path):
        handle = APSWDatabase(db_path, pragmas={
            'journal_mode': 'wal',
            'cache_size': -1 * 64000,
            'foreign_keys': 1,
            'ignore_check_constraints': 0
        })
        cls._db.initialize(handle)
        # ensure db matches current schema
        cls._db.create_tables([RulesBlogTable])
        cls.init()
        cls._migrator = SqliteMigrator(cls._db)

    @classmethod
    def stop(cls):
        return cls._db.close()

    @classmethod
    def init(cls):
        pass


class BaseModel(Model):
    class Meta:
        database = WatcherDB._db


class RulesBlogTable(BaseModel):
    pull_date = DateTimeField()
    page_text = TextField(index=True)

