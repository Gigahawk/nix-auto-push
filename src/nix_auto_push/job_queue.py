import sqlite3
import subprocess
import threading
import functools

from loguru import logger


def with_db_lock(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        if self.require_lock:
            with self._lock:
                return fn(self, *args, **kwargs)
        else:
            return fn(self, *args, **kwargs)

    return wrapper


class JobQueue:
    def __init__(self, path: str, max_attempts: int = 5, delete_attempts: int = 10):
        self._path = path
        self.max_attempts: int = max_attempts
        self.delete_attempts: int = delete_attempts
        assert self.max_attempts <= self.delete_attempts
        self.conn = sqlite3.connect(
            self._path,
            isolation_level=None,
            check_same_thread=False,
        )
        self._lock = threading.Lock()

        # See below for details
        # https://ricardoanderegg.com/posts/python-sqlite-thread-safety/
        if sqlite3.threadsafety == 3:
            logger.debug(
                "SQLite thread safety supported, queue access will not be serialized"
            )
            self.require_lock = False
        else:
            logger.warning(
                "SQLite thread safety NOT supported, queue access be serialized"
            )
            self.require_lock = True

        self.init_db()

        self.recover_jobs()

    @with_db_lock
    def init_db(self):
        logger.info(f"Initializing database at {self._path}")

        _ = self.conn.execute("PRAGMA journal_mode=WAL;")
        _ = self.conn.execute("PRAGMA synchronous=NORMAL")

        _ = self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                attempt INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                started_at DATETIME,
                finished_at DATETIME,
                exit_code INT,
                output TEXT,
                error TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_status_id ON jobs(status, id)
            """
        )

    @with_db_lock
    def recover_jobs(self):
        _ = self.conn.execute("BEGIN IMMEDIATE")

        rows = self.conn.execute("""
            SELECT id, store_path, started_at, status, exit_code, output, error
            FROM jobs
            WHERE status NOT IN ('queued', 'done')
        """)

        for job_id, store_path, started_at, status, exit_code, output, error in rows:
            if status != "cancelled":
                logger.warning(
                    (
                        f"Resetting failed job {job_id} for {store_path}, "
                        f"previously started at {started_at} and left with status {status}.\n"
                        f"Return code: {exit_code}\n"
                        f"Job output: {output}\n"
                        f"Error: {error}"
                    )
                )
                _ = self.conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'queued',
                        started_at = NULL
                    WHERE id = ?
                """,
                    (job_id,),
                )
        _ = self.conn.execute("COMMIT")

    @with_db_lock
    def submit_job(self, store_path: str):
        _ = self.conn.execute(
            "INSERT INTO jobs (store_path, status) VALUES (?, 'queued')",
            (store_path,),
        )

    @with_db_lock
    def job_available(self) -> bool:
        return bool(
            self.conn.execute("""
            SELECT store_path
            FROM jobs
            WHERE status = 'queued'
        """).fetchone()
        )

    @with_db_lock
    def start_job(self) -> tuple[int, str] | None:
        _ = self.conn.execute("BEGIN IMMEDIATE")

        row = self.conn.execute("""
            UPDATE jobs
            SET status='running',
                started_at=CURRENT_TIMESTAMP,
                attempt = attempt + 1
            WHERE id = (
                SELECT id FROM jobs
                WHERE status='queued'
                ORDER BY id
                LIMIT 1
            )
            RETURNING id, store_path
        """).fetchone()

        self.conn.commit()

        return row

    @with_db_lock
    def finish_job(
        self,
        job_id: int,
        proc: subprocess.CompletedProcess | subprocess.CalledProcessError,
        success: bool = True,
    ):
        _ = self.conn.execute("BEGIN IMMEDIATE")
        if success:
            status = "done"
        else:
            (attempt,) = self.conn.execute(
                """
                SELECT attempt
                FROM jobs
                WHERE id = ?
            """,
                (job_id,),
            ).fetchone()

            # Return to queue
            attempt = int(attempt)
            if attempt < self.max_attempts:
                logger.error(f"Job ID {job_id} failed, requeuing")
                status = "queued"
            elif attempt < self.delete_attempts:
                logger.error(
                    f"Job ID {job_id} failed {attempt} >= {self.max_attempts} times, setting status to failed"
                )
                status = "failed"
            else:
                logger.critical(
                    f"Job ID {job_id} failed {attempt} >= {self.delete_attempts} times, setting status to cancelled"
                )
                status = "cancelled"

        _ = self.conn.execute(
            """
        UPDATE jobs
        SET status = ?,
            finished_at = CURRENT_TIMESTAMP,
            exit_code = ?,
            output = ?,
            error = ?
        WHERE id = ?
        """,
            (
                status,
                proc.returncode,
                proc.stdout,
                proc.stderr,
                job_id,
            ),
        )

        self.conn.commit()
