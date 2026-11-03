from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .util import parse_dt, parse_utc, strip_html, to_local


class Store:
    """只读访问 TrendRadar 的 SQLite 数据。"""

    def __init__(self, root: str = "output"):
        self.root = Path(root)

    def _connect(self, path: Path) -> sqlite3.Connection:
        return sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=10)

    def items_since(self, since: datetime, published_floor=None):
        items = []
        stamp = since.strftime("%Y-%m-%d %H:%M:%S")
        day = since.strftime("%Y-%m-%d")
        for kind, sub in (("hotlist", "news"), ("rss", "rss")):
            folder = self.root / sub
            if not folder.exists():
                continue
            for path in sorted(folder.glob("*.db")):
                if path.stem < day:
                    continue
                items.extend(self._read_db(path, kind, stamp, published_floor))
        items.sort(key=lambda item: item["crawl_at"])
        return items

    def _read_db(self, path: Path, kind: str, stamp: str, published_floor=None):
        out = []
        try:
            conn = self._connect(path)
        except Exception:
            return out
        try:
            names = {}
            try:
                table = "platforms" if kind == "hotlist" else "rss_feeds"
                for row in conn.execute(f"select id, name from {table}"):
                    names[row[0]] = row[1]
            except Exception:
                pass
            if kind == "hotlist":
                sql = (
                    "select id, title, platform_id, rank, url, created_at from news_items "
                    "where created_at >= ? order by created_at"
                )
                rows = conn.execute(sql, (stamp,))
                for row in rows:
                    out.append(
                        {
                            "uid": f"h{row[0]}",
                            "kind": "hotlist",
                            "title": (row[1] or "").strip(),
                            "source_id": row[2] or "",
                            "source_name": names.get(row[2], row[2] or "热榜"),
                            "rank": row[3] or 0,
                            "url": row[4] or "",
                            "summary": "",
                            "published_at": None,
                            "crawl_at": parse_dt(row[5]),
                        }
                    )
            else:
                sql = (
                    "select id, title, feed_id, url, published_at, summary, created_at "
                    "from rss_items where created_at >= ? order by created_at"
                )
                rows = conn.execute(sql, (stamp,))
                for row in rows:
                    published = parse_utc(row[4])
                    if published_floor and published and published < published_floor:
                        continue
                    out.append(
                        {
                            "uid": f"r{row[0]}",
                            "kind": "rss",
                            "title": (row[1] or "").strip(),
                            "source_id": row[2] or "",
                            "source_name": names.get(row[2], row[2] or "RSS"),
                            "rank": 0,
                            "url": row[3] or "",
                            "summary": strip_html(row[5] or "")[:600],
                            "published_at": published,
                            "crawl_at": parse_dt(row[6]),
                        }
                    )
        finally:
            conn.close()
        return out


class Ledger:
    """推送台账：防重复、缓存简报、记录日报发送状态。"""

    def __init__(self, path: str = "data/state.db"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=30)
        self.conn.executescript(
            """
            create table if not exists pushed (
                key text primary key, titles text, score real, mode text,
                date text, pushed_at text);
            create table if not exists pushed_urls (
                url text primary key, key text, at text);
            create table if not exists seen (
                key text primary key, title text, brief text, score real,
                first_seen text, last_seen text);
            create table if not exists digests (
                date text, kind text, sent_at text, primary key(date, kind));
            create table if not exists meta (k text primary key, v text);
            """
        )
        self.conn.commit()

    def is_pushed(self, key: str, urls) -> bool:
        cur = self.conn.execute("select 1 from pushed where key = ?", (key,))
        if cur.fetchone():
            return True
        for url in urls:
            cur = self.conn.execute("select 1 from pushed_urls where url = ?", (url,))
            if cur.fetchone():
                return True
        return False

    def mark_pushed(self, key: str, urls, titles, score: float, mode: str, day: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            "insert or replace into pushed(key, titles, score, mode, date, pushed_at) "
            "values (?,?,?,?,?,?)",
            (key, json.dumps(titles[:3], ensure_ascii=False), score, mode, day, now),
        )
        for url in urls:
            if url:
                self.conn.execute(
                    "insert or replace into pushed_urls(url, key, at) values (?,?,?)",
                    (url, key, now),
                )
        self.conn.commit()

    def cached_brief(self, key: str, max_age_hours: float = 20.0):
        row = self.conn.execute(
            "select brief, last_seen from seen where key = ?", (key,)
        ).fetchone()
        if not row:
            return None
        last = parse_dt(row[1])
        if last and (datetime.now() - last) > timedelta(hours=max_age_hours):
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None

    def put_brief(self, key: str, title: str, brief: dict, score: float):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            "insert into seen(key, title, brief, score, first_seen, last_seen) "
            "values (?,?,?,?,?,?) on conflict(key) do update set "
            "brief=excluded.brief, score=excluded.score, last_seen=excluded.last_seen",
            (key, title[:200], json.dumps(brief, ensure_ascii=False), score, now, now),
        )
        self.conn.commit()

    def digest_sent(self, day: str, kind: str) -> bool:
        cur = self.conn.execute(
            "select 1 from digests where date = ? and kind = ?", (day, kind)
        )
        return cur.fetchone() is not None

    def mark_digest(self, day: str, kind: str):
        self.conn.execute(
            "insert or replace into digests(date, kind, sent_at) values (?,?,?)",
            (day, kind, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        self.conn.commit()

    def meta_get(self, key: str, default=None):
        row = self.conn.execute("select v from meta where k = ?", (key,)).fetchone()
        return row[0] if row else default

    def meta_set(self, key: str, value: str):
        self.conn.execute(
            "insert or replace into meta(k, v) values (?,?)", (key, str(value))
        )
        self.conn.commit()