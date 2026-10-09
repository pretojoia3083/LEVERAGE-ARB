"""Historico de operacoes.

- No PC: SQLite local (leverage_arb.db) — como sempre foi.
- Na nuvem (Render): Postgres gratis via DATABASE_URL — o historico
  sobrevive a deploys e reinicios (no plano gratis o disco apaga tudo).
"""
import json
import os
import threading

DB_PATH = 'leverage_arb.db'
db_lock = threading.Lock()

DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
USE_PG = bool(DATABASE_URL)

if USE_PG:
    try:
        import psycopg  # noqa: F401
    except ImportError:
        print("[DB] DATABASE_URL definido mas psycopg nao instalado — usando SQLite")
        USE_PG = False


def _conn():
    if USE_PG:
        import psycopg
        return psycopg.connect(DATABASE_URL)
    import sqlite3
    c = sqlite3.connect(DB_PATH, timeout=30)
    try:
        c.execute('PRAGMA busy_timeout=30000')
    except Exception:
        pass
    return c


def _exec(c, sql, params=()):
    if USE_PG:
        sql = sql.replace('?', '%s')
    return c.execute(sql, params)


def _init():
    c = _conn()
    if USE_PG:
        c.execute("""
        CREATE TABLE IF NOT EXISTS simulations (
            id SERIAL PRIMARY KEY,
            ts TIMESTAMPTZ DEFAULT NOW(),
            trigger TEXT DEFAULT 'auto',
            pair TEXT,
            buy_exchange TEXT,
            sell_exchange TEXT,
            buy_price REAL,
            sell_price REAL,
            gross_pct REAL,
            invest_usdt REAL,
            net_usdt REAL,
            net_pct REAL,
            network TEXT,
            est_seconds INTEGER
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS executions (
            id SERIAL PRIMARY KEY,
            ts TIMESTAMPTZ DEFAULT NOW(),
            pair TEXT,
            buy_exchange TEXT,
            sell_exchange TEXT,
            invest_usdt REAL,
            network TEXT,
            gross_pct REAL,
            net_usdt REAL,
            net_pct REAL,
            elapsed_ms INTEGER,
            mode TEXT,
            ok INTEGER DEFAULT 1,
            stages_json TEXT
        )
        """)
        c.execute("ALTER TABLE executions ADD COLUMN IF NOT EXISTS ok INTEGER DEFAULT 1")
    else:
        c.execute('PRAGMA journal_mode=WAL')
        c.execute("""
        CREATE TABLE IF NOT EXISTS simulations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT CURRENT_TIMESTAMP,
            trigger TEXT DEFAULT 'auto',
            pair TEXT,
            buy_exchange TEXT,
            sell_exchange TEXT,
            buy_price REAL,
            sell_price REAL,
            gross_pct REAL,
            invest_usdt REAL,
            net_usdt REAL,
            net_pct REAL,
            network TEXT,
            est_seconds INTEGER
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT CURRENT_TIMESTAMP,
            pair TEXT,
            buy_exchange TEXT,
            sell_exchange TEXT,
            invest_usdt REAL,
            network TEXT,
            gross_pct REAL,
            net_usdt REAL,
            net_pct REAL,
            elapsed_ms INTEGER,
            mode TEXT,
            ok INTEGER DEFAULT 1,
            stages_json TEXT
        )
        """)
        cols = [r[1] for r in c.execute("PRAGMA table_info(executions)").fetchall()]
        if 'ok' not in cols:
            c.execute("ALTER TABLE executions ADD COLUMN ok INTEGER DEFAULT 1")
    c.commit()
    c.close()


try:
    _init()
    print(f"[DB] usando {'Postgres' if USE_PG else 'SQLite local'}")
except Exception as e:
    print(f"[DB] falha ao iniciar banco: {e}")
    if USE_PG:
        print("[DB] caindo para SQLite local")
        USE_PG = False
        _init()


def _insert_id(c, sql, params):
    if USE_PG:
        cur = _exec(c, sql + " RETURNING id", params)
        return cur.fetchone()[0]
    _exec(c, sql, params)
    return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def _time_filter(hours):
    if USE_PG:
        return "ts >= NOW() + ?::INTERVAL", (f'-{hours} hours',)
    return "ts >= datetime('now', ?)", (f'-{hours} hours',)


def add_simulation(row):
    with db_lock:
        c = _conn()
        rid = _insert_id(c, """
        INSERT INTO simulations
        (trigger, pair, buy_exchange, sell_exchange, buy_price, sell_price,
         gross_pct, invest_usdt, net_usdt, net_pct, network, est_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row.get('trigger', 'auto'), row['pair'], row['buy_exchange'],
            row['sell_exchange'], row['buy_price'], row['sell_price'],
            row['gross_pct'], row['invest_usdt'], row['net_usdt'],
            row['net_pct'], row['network'], row['est_seconds'],
        ))
        c.commit()
        c.close()
        return rid


def recent_simulations(limit=200):
    c = _conn()
    rows = _exec(
        c, "SELECT * FROM simulations ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    c.close()
    cols = ['id', 'ts', 'trigger', 'pair', 'buy_exchange', 'sell_exchange',
            'buy_price', 'sell_price', 'gross_pct', 'invest_usdt',
            'net_usdt', 'net_pct', 'network', 'est_seconds']
    return [dict(zip(cols, r)) for r in rows]


def stats(hours=24):
    c = _conn()
    filt, params = _time_filter(hours)
    total, total_net, avg_net = _exec(c,
        f"""SELECT COUNT(*), COALESCE(SUM(net_usdt),0), COALESCE(AVG(net_pct),0)
           FROM simulations WHERE {filt}""",
        params,
    ).fetchone()
    best = _exec(c,
        f"""SELECT pair, buy_exchange, sell_exchange, network, net_usdt
           FROM simulations WHERE {filt}
           ORDER BY net_usdt DESC LIMIT 1""",
        params,
    ).fetchone()
    c.close()
    result = {
        'total_simulations': total,
        'total_net_usdt': round(total_net, 2),
        'avg_net_pct': round(avg_net, 4),
    }
    if best:
        result['best_route'] = {
            'pair': best[0], 'buy_exchange': best[1],
            'sell_exchange': best[2], 'network': best[3], 'net_usdt': round(best[4], 2),
        }
    return result


def clear():
    with db_lock:
        c = _conn()
        _exec(c, "DELETE FROM simulations")
        c.commit()
        c.close()


def add_execution(r):
    with db_lock:
        c = _conn()
        rid = _insert_id(c, """
        INSERT INTO executions
        (pair, buy_exchange, sell_exchange, invest_usdt, network,
         gross_pct, net_usdt, net_pct, elapsed_ms, mode, ok, stages_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r['pair'], r['buy_exchange'], r['sell_exchange'],
            r.get('invest_usdt', 0), r.get('network', ''),
            r.get('gross_pct', 0), r.get('net_usdt', 0), r.get('net_pct', 0),
            r.get('elapsed_ms', 0), r.get('mode', 'paper'),
            1 if r.get('ok') else 0,
            json.dumps(r.get('stages', [])),
        ))
        c.commit()
        c.close()
        return rid


def recent_executions(limit=100):
    c = _conn()
    rows = _exec(
        c, "SELECT * FROM executions ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    c.close()
    cols = ['id', 'ts', 'pair', 'buy_exchange', 'sell_exchange', 'invest_usdt',
            'network', 'gross_pct', 'net_usdt', 'net_pct', 'elapsed_ms',
            'mode', 'ok', 'stages_json']
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        d['elapsed_fmt'] = f"{(d['elapsed_ms'] or 0) / 1000:.2f}s"
        out.append(d)
    return out


def execution_stats():
    c = _conn()
    total, total_net, wins = _exec(c,
        "SELECT COUNT(*), COALESCE(SUM(net_usdt),0), COALESCE(SUM(ok),0) FROM executions"
    ).fetchone()
    c.close()
    return {
        'total_executions': total,
        'total_executed_net': round(total_net, 2),
        'successful_executions': wins,
    }
