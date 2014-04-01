import os
import functools
import sqlite3


db = None


@functools.total_ordering
class Table(object):
    _columns = ()
    _table = None

    def __init__(self, *args, **kwargs):
        if len(args) > len(self._columns):
            raise TypeError('Got %i arguments. Only %i expected'
                            % (len(args), len(self._columns)))
        for k, v in zip(self._columns, args):
            if k in kwargs:
                raise TypeError("Got multiple values for keyword argument '%s'"
                                % k)
            setattr(self, k, v)
        for k, v in kwargs.iteritems():
            if k not in self._columns:
                raise TypeError("Unexpected keyword argument '%s'" % k)
            setattr(self, k, v)

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            raise NotImplemented
        for key in self._columns:
            if getattr(self, key) != getattr(other, key):
                return False
        return True

    def __lt__(self, other):
        if not isinstance(other, self.__class__):
            raise NotImplemented
        for key in self._columns:
            if getattr(self, key) < getattr(other, key):
                return True
        return False

    def save(self):
        db = get_db()
        query = 'REPLACE INTO "%s" (%s) VALUES (%s);' % (
            self._table,
            ', '.join('"%s"' % column for column in self._columns),
            ', '.join('?' for column in self._columns))
        c = db.cursor()
        c.execute(query, [getattr(self, column) for column in self._columns])
        db.commit()

    @classmethod
    def get_all_where(cls, where_clause, parameters=()):
        db = get_db()
        c = db.cursor()
        c.execute(
            'SELECT %s FROM "%s" WHERE %s;' % (
                ', '.join('"%s"' % column for column in cls._columns),
                cls._table,
                where_clause
            ), parameters)
        for row in c:
            yield cls(*row)

    @classmethod
    def get_where(cls, where_clause, parameters=()):
        try:
            return next(cls.get_all_where(where_clause, parameters))
        except StopIteration:
            return None


class Job(Table):
    _columns = ('id', 'order_id', 'lang', 'source', 'translation', 'status')
    _table = 'job'

    @classmethod
    def create_table(cls, cursor):
        cursor.execute(
            """CREATE TABLE job (
                    id INTEGER PRIMARY KEY,
                    order_id INTEGER REFERENCES "order" (id),
                    lang TEXT,
                    source TEXT,
                    translation TEXT,
                    status TEXT
                );""")
        cursor.execute(
            'CREATE INDEX job_lang_string ON job (lang, source);')
        cursor.execute('CREATE INDEX job_status ON job (status);')

    @classmethod
    def find(cls, lang, source):
        return cls.get_where('lang = ? AND source = ?', (lang, source))

    @classmethod
    def get_in_progress(cls):
        return cls.get_all_where("status NOT IN ('approved', 'canceled')")

    @classmethod
    def get_reviewable(cls):
        return cls.get_all_where("status = 'reviewable'")


class Order(Table):
    _columns = ('id', 'created')
    _table = 'order'

    @classmethod
    def create_table(cls, cursor):
        cursor.execute(
            """CREATE TABLE "order"
               (id INTEGER PRIMARY KEY, created INTEGER);""")

    @classmethod
    def get_latest(cls):
        return cls.get_where('created = (SELECT MAX(created) FROM "order")')


def get_db():
    global db
    if not db:
        create_tables = not os.path.exists('jobs.db')
        db = sqlite3.connect('jobs.db')
        if create_tables:
            c = db.cursor()
            Order.create_table(c)
            Job.create_table(c)
            db.commit()
    return db
