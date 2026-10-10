"""Historico de operacoes.

- No PC: SQLite local (leverage_arb.db) — como sempre foi.
- Na nuvem (Render): Postgres gratis via DATABASE_URL — o historico
  sobrevive a deploys e reinicios (no plano gratis o disco apaga tudo).
"""
import json
import os
import threading
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))

DB_PATH = 'leverage_arb.db'
db_lock = threading.Lock()

# garante o .env antes de ler as variaveis (independe da ordem de import)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

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
            stages_json TEXT,
            est_real_seconds INTEGER DEFAULT 0,
            transfer_id INTEGER,
            done INTEGER DEFAULT 1
        )
        """)
        c.execute("ALTER TABLE executions ADD COLUMN IF NOT EXISTS ok INTEGER DEFAULT 1")
        c.execute("ALTER TABLE executions ADD COLUMN IF NOT EXISTS est_real_seconds INTEGER DEFAULT 0")
        c.execute("ALTER TABLE executions ADD COLUMN IF NOT EXISTS transfer_id INTEGER")
        c.execute("ALTER TABLE executions ADD COLUMN IF NOT EXISTS done INTEGER DEFAULT 1")
        c.execute("ALTER TABLE executions ADD COLUMN IF NOT EXISTS saldo_apos REAL DEFAULT 0")
        c.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
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
            stages_json TEXT,
            est_real_seconds INTEGER DEFAULT 0,
            transfer_id INTEGER,
            done INTEGER DEFAULT 1
        )
        """)
        cols = [r[1] for r in c.execute("PRAGMA table_info(executions)").fetchall()]
        if 'ok' not in cols:
            c.execute("ALTER TABLE executions ADD COLUMN ok INTEGER DEFAULT 1")
        if 'est_real_seconds' not in cols:
            c.execute("ALTER TABLE executions ADD COLUMN est_real_seconds INTEGER DEFAULT 0")
        if 'transfer_id' not in cols:
            c.execute("ALTER TABLE executions ADD COLUMN transfer_id INTEGER")
        if 'done' not in cols:
            c.execute("ALTER TABLE executions ADD COLUMN done INTEGER DEFAULT 1")
        if 'saldo_apos' not in cols:
            c.execute("ALTER TABLE executions ADD COLUMN saldo_apos REAL DEFAULT 0")
        c.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
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
         gross_pct, net_usdt, net_pct, elapsed_ms, mode, ok, stages_json,
         est_real_seconds, transfer_id, done, saldo_apos)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r['pair'], r['buy_exchange'], r['sell_exchange'],
            r.get('invest_usdt', 0), r.get('network', ''),
            r.get('gross_pct', 0), r.get('net_usdt', 0), r.get('net_pct', 0),
            r.get('elapsed_ms', 0), r.get('mode', 'paper'),
            1 if r.get('ok') else 0,
            json.dumps(r.get('stages', [])),
            r.get('est_real_seconds', 0) or 0,
            r.get('transfer_id'),
            1 if r.get('done', True) else 0,
            r.get('saldo_apos', 0) or 0,
        ))
        c.commit()
        c.close()
        return rid


def cancel_open_executions():
    """Ao reiniciar o servidor, ordens que ficaram abertas nao podem ficar
    'para sempre' no historico. Encerra com lucro 0 (nada foi ganho)."""
    with db_lock:
        c = _conn()
        _exec(c, "UPDATE executions SET done = 1, net_usdt = 0, net_pct = 0 "
                 "WHERE done = 0")
        n = c.rowcount
        c.commit()
        c.close()
    if n:
        print(f"[DB] {n} ordem(ns) aberta(s) encerrada(s) no reinicio")
    return n


def finish_execution(transfer_id, r):
    """Atualiza a ordem ja aberta com o resultado real (nao cria linha nova).
    Sem isso a ordem aberta (lucro simulado) e a concluida (lucro real)
    seriam somadas duas vezes no resultado."""
    if not transfer_id:
        return None
    sql = """
        UPDATE executions SET
            gross_pct = ?, net_usdt = ?, net_pct = ?,
            elapsed_ms = ?, ok = ?, stages_json = ?, done = 1, saldo_apos = ?
        WHERE transfer_id = ? AND done = 0
    """
    params = (r.get('gross_pct', 0), r.get('net_usdt', 0), r.get('net_pct', 0),
              r.get('elapsed_ms', 0), 1 if r.get('ok') else 0,
              json.dumps(r.get('stages', [])), r.get('saldo_apos', 0) or 0,
              transfer_id)
    with db_lock:
        c = _conn()
        _exec(c, sql, params)
        c.commit()
        c.close()
    return True


def recent_executions(limit=100):
    c = _conn()
    rows = _exec(
        c, "SELECT * FROM executions ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    c.close()
    cols = ['id', 'ts', 'pair', 'buy_exchange', 'sell_exchange', 'invest_usdt',
            'network', 'gross_pct', 'net_usdt', 'net_pct', 'elapsed_ms',
            'mode', 'ok', 'stages_json', 'est_real_seconds', 'transfer_id',
            'done', 'saldo_apos']
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        d['elapsed_fmt'] = f"{(d['elapsed_ms'] or 0) / 1000:.2f}s"
        out.append(d)
    return out


def _brt_day(v):
    """Data (BRT) de um timestamp do banco — SQLite devolve string UTC, PG devolve datetime."""
    if isinstance(v, datetime):
        d = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        return d.astimezone(BRT).date().isoformat()
    s = str(v)
    try:
        d = datetime.fromisoformat(s.replace('Z', '+00:00').replace(' ', 'T'))
    except ValueError:
        return s[:10]
    if not d.tzinfo:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(BRT).date().isoformat()


def daily_stats(mode=None):
    """Separa o resultado de HOJE (zera à meia-noite) do ACUMULADO de sempre.
    mode='demo'/'real'/'paper' filtra só um tipo de operação."""
    hoje = datetime.now(BRT).date().isoformat()
    c = _conn()
    ex_sql = ("SELECT ts, net_usdt, mode, buy_exchange, sell_exchange, network "
              "FROM executions WHERE done = 1")
    ex_params = ()
    if mode:
        ex_sql += " AND mode = ?"
        ex_params = (mode,)
    ex_rows = _exec(c, ex_sql, ex_params).fetchall()
    sim_rows = _exec(c, "SELECT ts, net_usdt, buy_exchange, sell_exchange, network "
                        "FROM simulations").fetchall()
    c.close()

    dia = {'ops': 0, 'net': 0.0, 'sims': 0, 'sim_net': 0.0}
    acum = {'ops': 0, 'net': 0.0, 'sims': 0, 'sim_net': 0.0}
    best = None

    for r in ex_rows:
        _, net, mode, buy, sell, net_id = r
        net = float(net or 0)
        acum['ops'] += 1
        acum['net'] += net
        if _brt_day(r[0]) == hoje:
            dia['ops'] += 1
            dia['net'] += net
            if best is None or net > best[0]:
                best = (net, buy, sell, net_id)

    for r in sim_rows:
        _, net, buy, sell, net_id = r
        net = float(net or 0)
        acum['sims'] += 1
        acum['sim_net'] += net
        if _brt_day(r[0]) == hoje:
            dia['sims'] += 1
            dia['sim_net'] += net

    return {
        'date': hoje,
        'dia': {k: (round(v, 2) if k.endswith('net') else v) for k, v in dia.items()},
        'acumulado': {k: (round(v, 2) if k.endswith('net') else v) for k, v in acum.items()},
        'melhor_hoje': None if not best else {
            'net_usdt': round(best[0], 2),
            'buy_exchange': best[1], 'sell_exchange': best[2], 'network': best[3],
        },
    }


def execution_stats():
    c = _conn()
    total, total_net, wins = _exec(c,
        "SELECT COUNT(*), COALESCE(SUM(net_usdt),0), COALESCE(SUM(ok),0) FROM executions"
    ).fetchone()
    # quebra por modo (paper / demo / real)
    por_modo = {}
    for r in _exec(c, "SELECT mode, COUNT(*), COALESCE(SUM(net_usdt),0) "
                      "FROM executions GROUP BY mode").fetchall():
        por_modo[r[0] or 'paper'] = {'ops': r[1], 'net': round(r[2], 2)}
    c.close()
    return {
        'total_executions': total,
        'total_executed_net': round(total_net, 2),
        'successful_executions': wins,
        'by_mode': por_modo,
    }


def get_setting(key, default=None):
    try:
        c = _conn()
        row = _exec(c, "SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        c.close()
        return row[0] if row else default
    except Exception:
        return default


def set_setting(key, value):
    with db_lock:
        c = _conn()
        if USE_PG:
            _exec(c, "INSERT INTO app_settings(key, value) VALUES (?, ?) "
                     "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                  (key, str(value)))
        else:
            _exec(c, "INSERT OR REPLACE INTO app_settings(key, value) VALUES (?, ?)",
                  (key, str(value)))
        c.commit()
        c.close()
