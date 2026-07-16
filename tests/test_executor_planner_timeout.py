import sys
import types
import unittest
from unittest.mock import patch

from executor import SQLExecutor


class PlannerTimeoutTest(unittest.TestCase):
    def test_starrocks_sets_planner_timeout_before_review_query(self):
        statements = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def execute(self, sql):
                statements.append(sql)

            def fetchall(self):
                return []

        class Connection:
            def cursor(self, _kind):
                return Cursor()

            def close(self):
                pass

        fake = types.SimpleNamespace(
            connect=lambda **kwargs: Connection(),
            cursors=types.SimpleNamespace(DictCursor=object),
            err=types.SimpleNamespace(OperationalError=RuntimeError),
        )
        executor = SQLExecutor({
            "starrocks": {"host": "x", "user": "u", "password": "p"},
            "starrocks_planner_timeout_ms": 30000,
        })

        with patch.dict(sys.modules, {"pymysql": fake}):
            executor._execute_starrocks("SELECT 1")

        self.assertEqual(statements[0], "SET new_planner_optimize_timeout=30000")
        self.assertEqual(statements[1], "SELECT 1")


if __name__ == "__main__":
    unittest.main()
