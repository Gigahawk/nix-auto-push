import sqlite3
import subprocess
import threading


class JobQueue:
    def __init__(self, path: str, max_attempts: int = 5):
        self._path = path
        self._local = threading.local()
        self.max_attempts: int = max_attempts

        self.init_db()

        self.recover_jobs()

    @property
    def conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self._path, isolation_level=None)
        return self._local.conn

    def init_db(self):
        print(f"Initializing database at {self._path}")

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

    def recover_jobs(self):
        _ = self.conn.execute("BEGIN IMMEDIATE")

        rows = self.conn.execute("""
            SELECT id, store_path, started_at, status, error
            FROM jobs
            WHERE status NOT IN ('queued', 'done')
        """)

        for job_id, store_path, started_at, status, exit_code, output, error in rows:
            print(
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

    def submit_job(self, store_path: str):
        _ = self.conn.execute(
            "INSERT INTO jobs (store_path, status) VALUES (?, 'queued')",
            (store_path,),
        )

    def job_available(self) -> bool:
        return bool(
            self.conn.execute("""
            SELECT store_path
            FROM jobs
            WHERE status = 'queued'
        """).fetchone()
        )

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
            if int(attempt) < self.max_attempts:
                print(f"Job ID {job_id} failed, requeuing")
                status = "queued"
            else:
                print(f"Job ID {job_id} failed {self.max_attempts} times.")
                status = "failed"

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
