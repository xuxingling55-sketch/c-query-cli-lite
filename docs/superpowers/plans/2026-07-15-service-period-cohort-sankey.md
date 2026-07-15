# Service Period Cohort Sankey Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a validated 2025 interactive Sankey that separately tracks monthly new-registration cohorts and the January month-end old-unpaid service-period base across explicit C-end service teams, no-service, and paid-exit states.

**Architecture:** StarRocks performs the large user-level month-end joins and returns a bounded link table. A small Python module validates conservation and allowed states, derives display payloads, and renders one interactive Sankey fragment with two views. Saved SQL, Excel results, a reproducible notebook, and the final visualization provide the audit trail.

**Tech Stack:** StarRocks SQL, existing `src/cli.py`, Python 3, pandas, unittest, D3.js 7, d3-sankey 0.12.3, Codex inline visualization fragment.

## Global Constraints

- Analysis window is January through December 2025; December 2024 is used only when a prior-month baseline is required.
- Every user attribute and service-period state is evaluated at the calendar month end.
- `user_allocation.user_allocation` is the source of truth for C-end service-period membership.
- The visible states are exactly: `电销/网销`, `体验营`, `新媒体视频`, `奥德赛`, `商业化-公域`, `研学`, `无服务期`, and `已付费`.
- Never create an `其他`, `其他服务期`, or unmapped fallback node; unexpected teams fail validation.
- New-registration cohorts retain their registration-month color through the final observed month.
- The January old-unpaid base includes only January month-end old-unpaid users who are in a C-end service period.
- The first paid month is an absorbing exit; later months for that user are excluded even if a refund occurs.
- B-end `入校` is out of scope for this version. A future B-end extension must source it from a user snapshot containing `入校`, not from `user_allocation.user_allocation`.
- Month-internal changes are out of scope; only adjacent month-end states are linked.
- Do not modify or stage unrelated files in the existing dirty worktree.

---

### Task 1: Confirm the month-end user-attribute source

**Files:**
- Create: `queries/service_period_sankey/01_profile_user_attributes.sql`
- Create: `queries/service_period_sankey/02_profile_service_teams.sql`
- Create: `outputs/service_period_sankey_2025/source_profile.md`

**Interfaces:**
- Consumes: `dws.topic_user_info`, `user_allocation.user_allocation`, `user_allocation.team`
- Produces: reviewed registration-time field, month-end paid-status values, user join key, and the exact 2025 C-end team set used by Task 3

- [ ] **Step 1: Write the user-attribute profiling query**

Create `queries/service_period_sankey/01_profile_user_attributes.sql` with:

```sql
SELECT
    day,
    business_user_pay_status_statistics,
    COUNT(*) AS row_count,
    COUNT(DISTINCT u_user) AS user_count,
    SUM(CASE WHEN u_user IS NULL OR u_user = '' THEN 1 ELSE 0 END) AS missing_user_rows,
    SUM(CASE WHEN regist_time IS NULL THEN 1 ELSE 0 END) AS missing_registration_rows,
    MIN(regist_time) AS earliest_registration_time,
    MAX(regist_time) AS latest_registration_time
FROM dws.topic_user_info
WHERE day IN (
    20250131, 20250228, 20250331, 20250430,
    20250531, 20250630, 20250731, 20250831,
    20250930, 20251031, 20251130, 20251231
)
GROUP BY day, business_user_pay_status_statistics
ORDER BY day, row_count DESC
LIMIT 1000;
```

- [ ] **Step 2: Run the user-attribute profile**

Run:

```bash
python3 src/cli.py run queries/service_period_sankey/01_profile_user_attributes.sql -o 服务期桑基图用户属性核验 --engine starrocks
```

Expected:

- 12 month-end dates are returned.
- `u_user` is populated for all usable rows.
- Paid-status values can be partitioned into `新增`, `老未`, and explicit paid values.
- `regist_time` is populated sufficiently to assign registration month; any missing rate is recorded in `source_profile.md` before continuing.

- [ ] **Step 3: Write the service-team profiling query**

Create `queries/service_period_sankey/02_profile_service_teams.sql` with:

```sql
WITH scoped AS (
    SELECT
        user_id,
        team_id,
        start_time AS day,
        end_time,
        deleted_at
    FROM user_allocation.user_allocation
)
SELECT
    ua.team_id,
    t.name AS team_name,
    COUNT(*) AS record_count,
    COUNT(DISTINCT ua.user_id) AS user_count,
    MIN(ua.day) AS earliest_start,
    MAX(ua.day) AS latest_start
FROM scoped ua
LEFT JOIN user_allocation.team t
  ON ua.team_id = t.id
WHERE ua.day < '2026-01-01'
  AND ua.end_time > '2025-01-01'
  AND ua.deleted_at IS NULL
GROUP BY ua.team_id, t.name
ORDER BY record_count DESC
LIMIT 100;
```

- [ ] **Step 4: Run the service-team profile**

Run:

```bash
python3 src/cli.py run queries/service_period_sankey/02_profile_service_teams.sql -o 服务期桑基图团队核验 --engine starrocks
```

Expected team names are exactly:

```text
电销/网销
体验营
新媒体视频
奥德赛-废弃
商业化-公域
研学
```

The display normalization is `奥德赛-废弃` → `奥德赛`. Any additional team blocks execution until it is added as its own explicit display node.

- [ ] **Step 5: Save source decisions**

Create `outputs/service_period_sankey_2025/source_profile.md` containing:

```markdown
# Source profile

- User join key: `dws.topic_user_info.u_user` = `user_allocation.user_allocation.user_id`
- Registration cohort: calendar month of `dws.topic_user_info.regist_time`
- Month-end paid status: `dws.topic_user_info.business_user_pay_status_statistics`
- Unpaid values: `新增`, `老未`
- Paid values: the explicit reviewed values `高净值用户`, `续费用户`; any new value blocks execution until reviewed
- Service state: interval membership in `user_allocation.user_allocation`
- Team display normalization: `奥德赛-废弃` → `奥德赛`
- Scope: C-end only; no `入校`
```

- [ ] **Step 6: Commit the source profile assets**

```bash
git add queries/service_period_sankey/01_profile_user_attributes.sql queries/service_period_sankey/02_profile_service_teams.sql outputs/service_period_sankey_2025/source_profile.md
git commit -m "chore: profile service period cohort sources"
```

---

### Task 2: Add pure validation and payload functions

**Files:**
- Create: `src/service_period_sankey.py`
- Create: `tests/test_service_period_sankey.py`

**Interfaces:**
- Consumes: aggregate link rows with `view_type`, `registration_cohort`, `source_month`, `source_state`, `target_month`, `target_state`, `user_count`, `cohort_size`
- Produces: `validate_links(frame) -> None`, `add_cohort_share(frame) -> pandas.DataFrame`, `build_payload(frame) -> dict`

- [ ] **Step 1: Write failing tests for allowed states and unmapped teams**

Create `tests/test_service_period_sankey.py` with:

```python
from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from service_period_sankey import add_cohort_share, build_payload, validate_links


def sample_links() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "view_type": "new_registration",
                "registration_cohort": "2025-01",
                "source_month": "入口",
                "source_state": "1月新增",
                "target_month": "2025-01",
                "target_state": "电销/网销",
                "user_count": 60,
                "cohort_size": 100,
            },
            {
                "view_type": "new_registration",
                "registration_cohort": "2025-01",
                "source_month": "入口",
                "source_state": "1月新增",
                "target_month": "2025-01",
                "target_state": "无服务期",
                "user_count": 40,
                "cohort_size": 100,
            },
            {
                "view_type": "new_registration",
                "registration_cohort": "2025-01",
                "source_month": "2025-01",
                "source_state": "电销/网销",
                "target_month": "2025-02",
                "target_state": "已付费",
                "user_count": 10,
                "cohort_size": 100,
            },
            {
                "view_type": "new_registration",
                "registration_cohort": "2025-01",
                "source_month": "2025-01",
                "source_state": "电销/网销",
                "target_month": "2025-02",
                "target_state": "电销/网销",
                "user_count": 50,
                "cohort_size": 100,
            },
            {
                "view_type": "new_registration",
                "registration_cohort": "2025-01",
                "source_month": "2025-01",
                "source_state": "无服务期",
                "target_month": "2025-02",
                "target_state": "无服务期",
                "user_count": 40,
                "cohort_size": 100,
            },
        ]
    )


class ServicePeriodSankeyTest(unittest.TestCase):
    def test_valid_links_pass(self) -> None:
        validate_links(sample_links())

    def test_unmapped_team_fails(self) -> None:
        frame = sample_links()
        frame.loc[0, "target_state"] = "其他服务期"
        with self.assertRaisesRegex(ValueError, "未映射服务期"):
            validate_links(frame)

    def test_negative_count_fails(self) -> None:
        frame = sample_links()
        frame.loc[0, "user_count"] = -1
        with self.assertRaisesRegex(ValueError, "负数"):
            validate_links(frame)

    def test_cohort_share_uses_fixed_cohort_size(self) -> None:
        result = add_cohort_share(sample_links())
        self.assertEqual(result.loc[0, "cohort_share"], 0.6)

    def test_payload_has_two_views_and_all_cohorts(self) -> None:
        payload = build_payload(add_cohort_share(sample_links()))
        self.assertIn("new_registration", payload["views"])
        self.assertIn("old_unpaid", payload["views"])
        self.assertIn("all", payload["views"]["new_registration"]["cohorts"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_service_period_sankey -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'service_period_sankey'`.

- [ ] **Step 3: Implement the minimal validation module**

Create `src/service_period_sankey.py` with:

```python
from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd


SERVICE_STATES = (
    "电销/网销",
    "体验营",
    "新媒体视频",
    "奥德赛",
    "商业化-公域",
    "研学",
    "无服务期",
    "已付费",
)
LINK_COLUMNS = (
    "view_type",
    "registration_cohort",
    "source_month",
    "source_state",
    "target_month",
    "target_state",
    "user_count",
    "cohort_size",
)


def validate_links(frame: pd.DataFrame) -> None:
    missing = [column for column in LINK_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"缺少字段: {', '.join(missing)}")
    if frame["user_count"].isna().any() or (frame["user_count"] < 0).any():
        raise ValueError("用户数存在空值或负数")
    if frame["cohort_size"].isna().any() or (frame["cohort_size"] <= 0).any():
        raise ValueError("批次人数必须为正数")
    allowed = set(SERVICE_STATES)
    observed = set(frame.loc[frame["source_month"] != "入口", "source_state"])
    observed |= set(frame["target_state"])
    unexpected = sorted(observed - allowed)
    if unexpected:
        raise ValueError(f"未映射服务期: {', '.join(unexpected)}")
    if not set(frame["view_type"]).issubset({"new_registration", "old_unpaid"}):
        raise ValueError("view_type 只能是 new_registration 或 old_unpaid")


def add_cohort_share(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["cohort_share"] = result["user_count"] / result["cohort_size"]
    return result


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return frame.sort_values(
        ["registration_cohort", "source_month", "source_state", "target_state"]
    ).to_dict(orient="records")


def build_payload(frame: pd.DataFrame) -> dict[str, Any]:
    validate_links(frame)
    views: dict[str, Any] = {
        "new_registration": {"cohorts": defaultdict(list)},
        "old_unpaid": {"cohorts": defaultdict(list)},
    }
    for view_type, view_frame in frame.groupby("view_type", sort=True):
        for cohort, cohort_frame in view_frame.groupby("registration_cohort", sort=True):
            views[view_type]["cohorts"][cohort] = _records(cohort_frame)
        views[view_type]["cohorts"]["all"] = _records(view_frame)
        views[view_type]["cohorts"] = dict(views[view_type]["cohorts"])
    views["new_registration"]["cohorts"].setdefault("all", [])
    views["old_unpaid"]["cohorts"].setdefault("all", [])
    return {
        "states": list(SERVICE_STATES),
        "default_view": "new_registration",
        "default_cohort": "2025-01",
        "views": views,
    }
```

- [ ] **Step 4: Run tests and verify pass**

```bash
python3 -m unittest tests.test_service_period_sankey -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit the validation module**

```bash
git add src/service_period_sankey.py tests/test_service_period_sankey.py
git commit -m "feat: validate service period sankey links"
```

---

### Task 3: Build the bounded cohort-link query

**Files:**
- Create: `queries/service_period_sankey/03_build_cohort_links.sql`
- Create: `queries/service_period_sankey/04_validate_cohort_links.sql`

**Interfaces:**
- Consumes: Task 1 source decisions and the exact paid-status values recorded in `source_profile.md`
- Produces: bounded link rows matching `LINK_COLUMNS` from Task 2

- [ ] **Step 1: Write the cohort-link SQL using the reviewed paid values**

Create `queries/service_period_sankey/03_build_cohort_links.sql` with these complete CTE responsibilities:

```sql
WITH month_ends AS (
    SELECT 1 AS month_num, '2025-01' AS month_name, 20250131 AS day, CAST('2025-01-31 23:59:59' AS DATETIME) AS snapshot_time
    UNION ALL SELECT 2, '2025-02', 20250228, CAST('2025-02-28 23:59:59' AS DATETIME)
    UNION ALL SELECT 3, '2025-03', 20250331, CAST('2025-03-31 23:59:59' AS DATETIME)
    UNION ALL SELECT 4, '2025-04', 20250430, CAST('2025-04-30 23:59:59' AS DATETIME)
    UNION ALL SELECT 5, '2025-05', 20250531, CAST('2025-05-31 23:59:59' AS DATETIME)
    UNION ALL SELECT 6, '2025-06', 20250630, CAST('2025-06-30 23:59:59' AS DATETIME)
    UNION ALL SELECT 7, '2025-07', 20250731, CAST('2025-07-31 23:59:59' AS DATETIME)
    UNION ALL SELECT 8, '2025-08', 20250831, CAST('2025-08-31 23:59:59' AS DATETIME)
    UNION ALL SELECT 9, '2025-09', 20250930, CAST('2025-09-30 23:59:59' AS DATETIME)
    UNION ALL SELECT 10, '2025-10', 20251031, CAST('2025-10-31 23:59:59' AS DATETIME)
    UNION ALL SELECT 11, '2025-11', 20251130, CAST('2025-11-30 23:59:59' AS DATETIME)
    UNION ALL SELECT 12, '2025-12', 20251231, CAST('2025-12-31 23:59:59' AS DATETIME)
),
month_end_users AS (
    SELECT
        m.month_num,
        m.month_name,
        m.day,
        m.snapshot_time,
        u.u_user AS user_id,
        u.regist_time,
        DATE_FORMAT(u.regist_time, '%Y-%m') AS registration_cohort,
        u.business_user_pay_status_statistics,
        CASE
            WHEN u.business_user_pay_status_statistics IN ('新增', '老未') THEN 0
            WHEN u.business_user_pay_status_statistics IN ('高净值用户', '续费用户') THEN 1
            ELSE NULL
        END AS is_paid
    FROM month_ends m
    JOIN dws.topic_user_info u
      ON u.day = m.day
    WHERE u.u_user IS NOT NULL
      AND u.u_user <> ''
      AND u.business_user_pay_status_statistics IN (
          '新增', '老未', '高净值用户', '续费用户'
      )
),
service_states AS (
    SELECT
        meu.month_num,
        meu.month_name,
        meu.day,
        meu.user_id,
        meu.regist_time,
        meu.registration_cohort,
        meu.is_paid,
        COALESCE(
            MAX(
                CASE t.name
                    WHEN '奥德赛-废弃' THEN '奥德赛'
                    ELSE t.name
                END
            ),
            '无服务期'
        ) AS service_state,
        COUNT(DISTINCT ua.team_id) AS concurrent_team_count
    FROM month_end_users meu
    LEFT JOIN user_allocation.user_allocation ua
      ON ua.user_id = meu.user_id
     AND ua.start_time <= meu.snapshot_time
     AND ua.end_time > meu.snapshot_time
     AND ua.deleted_at IS NULL
    LEFT JOIN user_allocation.team t
      ON ua.team_id = t.id
    GROUP BY
        meu.month_num,
        meu.month_name,
        meu.day,
        meu.user_id,
        meu.regist_time,
        meu.registration_cohort,
        meu.is_paid
),
new_cohort_users AS (
    SELECT DISTINCT
        'new_registration' AS view_type,
        registration_cohort,
        user_id,
        CAST(SUBSTRING(registration_cohort, 6, 2) AS INT) AS start_month_num
    FROM service_states
    WHERE registration_cohort BETWEEN '2025-01' AND '2025-12'
),
old_unpaid_users AS (
    SELECT DISTINCT
        'old_unpaid' AS view_type,
        '2025年初老未' AS registration_cohort,
        user_id,
        1 AS start_month_num
    FROM service_states
    WHERE month_num = 1
      AND registration_cohort < '2025-01'
      AND is_paid = 0
      AND service_state <> '无服务期'
),
cohort_users AS (
    SELECT view_type, registration_cohort, user_id, start_month_num FROM new_cohort_users
    UNION ALL
    SELECT view_type, registration_cohort, user_id, start_month_num FROM old_unpaid_users
),
cohort_sizes AS (
    SELECT view_type, registration_cohort, COUNT(DISTINCT user_id) AS cohort_size
    FROM cohort_users
    GROUP BY view_type, registration_cohort
),
cohort_month_states AS (
    SELECT
        cu.view_type,
        cu.registration_cohort,
        cu.user_id,
        ss.month_num,
        ss.month_name,
        ss.is_paid,
        ss.service_state,
        ss.concurrent_team_count,
        MIN(CASE WHEN ss.is_paid = 1 THEN ss.month_num END)
            OVER (PARTITION BY cu.view_type, cu.registration_cohort, cu.user_id) AS first_paid_month_num
    FROM cohort_users cu
    JOIN service_states ss
      ON ss.user_id = cu.user_id
     AND ss.month_num >= cu.start_month_num
),
visible_states AS (
    SELECT
        view_type,
        registration_cohort,
        user_id,
        month_num,
        month_name,
        concurrent_team_count,
        CASE
            WHEN month_num = first_paid_month_num THEN '已付费'
            ELSE service_state
        END AS visible_state
    FROM cohort_month_states
    WHERE first_paid_month_num IS NULL
       OR month_num <= first_paid_month_num
),
entry_links AS (
    SELECT
        vs.view_type,
        vs.registration_cohort,
        '入口' AS source_month,
        CASE
            WHEN vs.view_type = 'old_unpaid' THEN '年初老未'
            ELSE CONCAT(CAST(vs.month_num AS STRING), '月新增')
        END AS source_state,
        vs.month_name AS target_month,
        vs.visible_state AS target_state,
        COUNT(DISTINCT vs.user_id) AS user_count
    FROM visible_states vs
    JOIN cohort_users cu
      ON cu.view_type = vs.view_type
     AND cu.registration_cohort = vs.registration_cohort
     AND cu.user_id = vs.user_id
     AND cu.start_month_num = vs.month_num
    GROUP BY
        vs.view_type,
        vs.registration_cohort,
        CASE
            WHEN vs.view_type = 'old_unpaid' THEN '年初老未'
            ELSE CONCAT(CAST(vs.month_num AS STRING), '月新增')
        END,
        vs.month_name,
        vs.visible_state
),
month_links AS (
    SELECT
        a.view_type,
        a.registration_cohort,
        a.month_name AS source_month,
        a.visible_state AS source_state,
        b.month_name AS target_month,
        b.visible_state AS target_state,
        COUNT(DISTINCT a.user_id) AS user_count
    FROM visible_states a
    JOIN visible_states b
      ON b.view_type = a.view_type
     AND b.registration_cohort = a.registration_cohort
     AND b.user_id = a.user_id
     AND b.month_num = a.month_num + 1
    WHERE a.visible_state <> '已付费'
    GROUP BY
        a.view_type,
        a.registration_cohort,
        a.month_name,
        a.visible_state,
        b.month_name,
        b.visible_state
),
all_links AS (
    SELECT view_type, registration_cohort, source_month, source_state, target_month, target_state, user_count
    FROM entry_links
    UNION ALL
    SELECT view_type, registration_cohort, source_month, source_state, target_month, target_state, user_count
    FROM month_links
)
SELECT
    l.view_type,
    l.registration_cohort,
    l.source_month,
    l.source_state,
    l.target_month,
    l.target_state,
    l.user_count,
    cs.cohort_size
FROM all_links l
JOIN cohort_sizes cs
  ON cs.view_type = l.view_type
 AND cs.registration_cohort = l.registration_cohort
WHERE l.user_count > 0
ORDER BY l.view_type, l.registration_cohort, l.source_month, l.source_state, l.target_state
LIMIT 10000;
```

Before execution, reconcile the four explicit status values with Task 1's profile. Any null, blank, or new status blocks execution until it is classified explicitly; never use a generic fallback.

- [ ] **Step 2: Run the cohort-link query**

```bash
python3 src/cli.py run queries/service_period_sankey/03_build_cohort_links.sql -o 2025服务期分群桑基图流向 --engine starrocks
```

Expected: fewer than 10,000 aggregate rows with both `new_registration` and `old_unpaid` views.

- [ ] **Step 3: Write the live validation query**

Create `queries/service_period_sankey/04_validate_cohort_links.sql` by reusing the CTEs through `visible_states`, then return:

```sql
SELECT
    view_type,
    registration_cohort,
    month_name,
    COUNT(DISTINCT user_id) AS visible_users,
    COUNT(DISTINCT CASE WHEN visible_state = '已付费' THEN user_id END) AS first_paid_users,
    MAX(concurrent_team_count) AS max_concurrent_team_count,
    COUNT(DISTINCT CASE
        WHEN visible_state NOT IN (
            '电销/网销', '体验营', '新媒体视频', '奥德赛',
            '商业化-公域', '研学', '无服务期', '已付费'
        ) THEN visible_state
    END) AS unmapped_state_count
FROM visible_states
WHERE month_name BETWEEN '2025-01' AND '2025-12'
GROUP BY view_type, registration_cohort, month_name
ORDER BY view_type, registration_cohort, month_name
LIMIT 1000;
```

Expected: `max_concurrent_team_count <= 1` and `unmapped_state_count = 0` for every row.

- [ ] **Step 4: Run the live validation query**

```bash
python3 src/cli.py run queries/service_period_sankey/04_validate_cohort_links.sql -o 2025服务期分群桑基图校验 --engine starrocks
```

Expected: all validation rows satisfy the limits above.

- [ ] **Step 5: Commit the analytical SQL**

```bash
git add queries/service_period_sankey/03_build_cohort_links.sql queries/service_period_sankey/04_validate_cohort_links.sql
git commit -m "feat: aggregate service period cohort flows"
```

---

### Task 4: Validate the exported link frame and generate the visual payload

**Files:**
- Modify: `src/service_period_sankey.py`
- Modify: `tests/test_service_period_sankey.py`
- Create: `queries/service_period_sankey/build_payload.py`
- Create: `outputs/service_period_sankey_2025/sankey_payload.json`
- Create: `outputs/service_period_sankey_2025/sankey_links.xlsx`

**Interfaces:**
- Consumes: Task 3 `result.xlsx`
- Produces: validated `sankey_payload.json` consumed by Task 5

- [ ] **Step 1: Add failing conservation tests**

Append to `ServicePeriodSankeyTest`:

```python
    def test_broken_conservation_fails(self) -> None:
        frame = sample_links()
        frame.loc[3, "user_count"] = 49
        with self.assertRaisesRegex(ValueError, "人数不守恒"):
            validate_links(frame)

    def test_paid_state_has_no_outgoing_link(self) -> None:
        frame = sample_links()
        extra = frame.iloc[[0]].copy()
        extra["source_month"] = "2025-02"
        extra["source_state"] = "已付费"
        extra["target_month"] = "2025-03"
        extra["target_state"] = "无服务期"
        frame = pd.concat([frame, extra], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "已付费不能继续流出"):
            validate_links(frame)
```

- [ ] **Step 2: Run tests and verify failure**

```bash
python3 -m unittest tests.test_service_period_sankey -v
```

Expected: the two new tests fail because conservation and paid-outflow checks are not implemented.

- [ ] **Step 3: Add conservation checks**

Add to `src/service_period_sankey.py`:

```python
def _validate_conservation(frame: pd.DataFrame) -> None:
    paid_sources = frame.loc[frame["source_state"] == "已付费"]
    if not paid_sources.empty:
        raise ValueError("已付费不能继续流出")

    internal = frame.loc[frame["source_month"] != "入口"]
    for keys, outgoing in internal.groupby(
        ["view_type", "registration_cohort", "source_month", "source_state"],
        sort=False,
    ):
        view_type, cohort, source_month, source_state = keys
        incoming = frame.loc[
            (frame["view_type"] == view_type)
            & (frame["registration_cohort"] == cohort)
            & (frame["target_month"] == source_month)
            & (frame["target_state"] == source_state),
            "user_count",
        ].sum()
        outgoing_count = outgoing["user_count"].sum()
        if int(incoming) != int(outgoing_count):
            raise ValueError(
                f"人数不守恒: {view_type}/{cohort}/{source_month}/{source_state} "
                f"incoming={incoming}, outgoing={outgoing_count}"
            )
```

Call `_validate_conservation(frame)` at the end of `validate_links`.

- [ ] **Step 4: Run tests and verify pass**

```bash
python3 -m unittest tests.test_service_period_sankey -v
```

Expected: 7 tests pass.

- [ ] **Step 5: Add the payload builder command**

Create `queries/service_period_sankey/build_payload.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from service_period_sankey import add_cohort_share, build_payload, validate_links


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_xlsx")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "outputs" / "service_period_sankey_2025"),
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.read_excel(args.result_xlsx)
    validate_links(frame)
    frame = add_cohort_share(frame)
    frame.to_excel(output_dir / "sankey_links.xlsx", index=False)
    payload = build_payload(frame)
    (output_dir / "sankey_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"rows={len(frame)} cohorts={frame['registration_cohort'].nunique()}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Generate the validated payload**

Resolve the actual Task 3 result path and run the builder:

```bash
RESULT_XLSX="$(find queries -maxdepth 2 -type f -path '*2025服务期分群桑基图流向*/result.xlsx' -print | sort | tail -1)"
test -n "$RESULT_XLSX"
python3 queries/service_period_sankey/build_payload.py "$RESULT_XLSX"
```

Expected: prints the row count and 13 cohorts: 12 registration months plus `2025年初老未`.

- [ ] **Step 7: Commit the payload pipeline**

```bash
git add src/service_period_sankey.py tests/test_service_period_sankey.py queries/service_period_sankey/build_payload.py
git commit -m "feat: prepare validated sankey payload"
```

Do not commit generated output data unless the user explicitly asks to version it.

---

### Task 5: Render the interactive Sankey fragment

**Files:**
- Modify: `src/service_period_sankey.py`
- Modify: `tests/test_service_period_sankey.py`
- Create: `/Users/hilda/.codex/visualizations/2026/07/15/019f64ab-f36b-70e1-8254-6d1fab37e02c/service-period-cohort-sankey.html`

**Interfaces:**
- Consumes: Task 4 `sankey_payload.json`
- Produces: `render_fragment(payload) -> str` and the final inline visualization fragment

- [ ] **Step 1: Write failing renderer contract tests**

Append imports and tests:

```python
from service_period_sankey import render_fragment


class ServicePeriodSankeyRenderTest(unittest.TestCase):
    def test_fragment_has_required_controls_and_no_document_wrapper(self) -> None:
        payload = build_payload(add_cohort_share(sample_links()))
        html = render_fragment(payload)
        self.assertIn('id="service-period-sankey"', html)
        self.assertIn('data-control="view"', html)
        self.assertIn('data-control="cohort"', html)
        self.assertIn('d3-sankey@0.12.3', html)
        self.assertNotIn("<!doctype", html.lower())
        self.assertNotIn("<html", html.lower())

    def test_fragment_never_contains_other_state(self) -> None:
        payload = build_payload(add_cohort_share(sample_links()))
        html = render_fragment(payload)
        self.assertNotIn("其他服务期", html)
```

- [ ] **Step 2: Run tests and verify failure**

```bash
python3 -m unittest tests.test_service_period_sankey -v
```

Expected: FAIL because `render_fragment` does not exist.

- [ ] **Step 3: Implement the fragment renderer**

Add `render_fragment(payload: dict[str, Any]) -> str` to `src/service_period_sankey.py`. It must return a literal HTML fragment with:

```html
<div id="service-period-sankey">
  <div class="viz-controls">
    <label class="form-label">视角
      <select class="form-select" data-control="view">
        <option value="new_registration">新注册批次</option>
        <option value="old_unpaid">年初老未</option>
      </select>
    </label>
    <label class="form-label">注册批次
      <select class="form-select" data-control="cohort"></select>
    </label>
  </div>
  <svg role="img" aria-labelledby="service-period-sankey-title service-period-sankey-desc"></svg>
  <p class="sr-only" id="service-period-sankey-title">2025年服务期用户流转</p>
  <p class="sr-only" id="service-period-sankey-desc">按月展示新注册批次或年初老未用户在明确服务期、无服务期和已付费之间的流转。</p>
</div>
<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/d3-sankey@0.12.3/dist/d3-sankey.min.js"></script>
```

The renderer must embed `json.dumps(payload, ensure_ascii=False)` in one script, use `document.getElementById('service-period-sankey')`, keep node ordering equal to `SERVICE_STATES`, and rebuild the SVG when either selector changes. Link color is selected-cohort color; the old-unpaid view is gray. The `all` cohort option uses each link's registration cohort color. Tooltip text must include source month/state, target month/state, user count, and fixed cohort share.

- [ ] **Step 4: Run tests and verify pass**

```bash
python3 -m unittest tests.test_service_period_sankey -v
```

Expected: 9 tests pass.

- [ ] **Step 5: Generate the fragment**

Run:

```bash
python3 - <<'PY'
import json
from pathlib import Path
import sys

root = Path('/Users/hilda/Documents/GitHub/c-query-cli-lite')
sys.path.insert(0, str(root / 'src'))
from service_period_sankey import render_fragment

payload = json.loads((root / 'outputs/service_period_sankey_2025/sankey_payload.json').read_text(encoding='utf-8'))
target = Path('/Users/hilda/.codex/visualizations/2026/07/15/019f64ab-f36b-70e1-8254-6d1fab37e02c/service-period-cohort-sankey.html')
target.write_text(render_fragment(payload), encoding='utf-8')
print(target)
PY
```

Expected: the fragment path is printed and the file is under 2 MB.

- [ ] **Step 6: Render and visually inspect**

Run:

```bash
python3 /Users/hilda/.codex/plugins/cache/openai-bundled/visualize/1.0.11/skills/visualize/scripts/render.py \
  /Users/hilda/.codex/visualizations/2026/07/15/019f64ab-f36b-70e1-8254-6d1fab37e02c/service-period-cohort-sankey.html \
  /tmp/service-period-cohort-sankey-preview.html
```

Inspect at approximately 736 px and 320 px widths. Expected:

- all visible states are explicit and readable;
- no `其他` node appears;
- the default view is January registration cohort;
- switching cohorts changes links without breaking node order;
- the old-unpaid view uses gray links;
- tooltips remain inside the plot;
- no horizontal overflow, clipped labels, browser errors, or external requests outside the approved CDNs.

- [ ] **Step 7: Commit the renderer code**

```bash
git add src/service_period_sankey.py tests/test_service_period_sankey.py
git commit -m "feat: render interactive service period sankey"
```

Do not commit the thread-scoped visualization fragment.

---

### Task 6: Build the reproducible analysis and final readout

**Files:**
- Create: `queries/service_period_sankey/2025_service_period_cohort_analysis.ipynb`
- Create: `outputs/service_period_sankey_2025/summary.xlsx`
- Create: `outputs/service_period_sankey_2025/README.md`

**Interfaces:**
- Consumes: validated Task 4 link table and Task 3 validation result
- Produces: executed notebook, compact summary workbook, plain-language findings, and final inline handoff

- [ ] **Step 1: Create the analysis notebook**

Use `nbformat` to create a notebook with sections in this exact order:

```markdown
## tl;dr
## Context & Methods
### Key Assumptions
## Data
### Validate Inputs
## Results
### New-registration cohorts
### January old-unpaid base
### No-service accumulation and paid exits
## Takeaways
```

The notebook must load `sankey_links.xlsx`, call `validate_links`, and calculate for each cohort:

```python
cohort_summary = (
    links.groupby(["view_type", "registration_cohort", "target_month", "target_state"], as_index=False)
    ["user_count"].sum()
)
paid_exits = links.loc[links["target_state"] == "已付费"]
no_service = links.loc[links["target_state"] == "无服务期"]
```

It must avoid summing repeated monthly states into a unique-user total; label all cross-month sums as monthly flow person-times.

- [ ] **Step 2: Execute the notebook top to bottom**

Run with the available notebook environment:

```bash
python3 -m jupyter nbconvert --execute --to notebook --inplace \
  queries/service_period_sankey/2025_service_period_cohort_analysis.ipynb
```

If the default environment lacks Jupyter, use a temporary virtual environment outside the repository and execute with `nbclient`. Expected: every code cell has an execution count and no error output.

- [ ] **Step 3: Create the summary workbook**

Write `outputs/service_period_sankey_2025/summary.xlsx` with sheets:

```text
cohort_overview
monthly_state_distribution
largest_transitions
paid_exits
no_service
validation
```

Every sheet must contain explicit `view_type` and `registration_cohort` columns.

- [ ] **Step 4: Write the output README**

Create `outputs/service_period_sankey_2025/README.md` containing:

```markdown
# 2025 服务期分群桑基图

## Scope

- C端服务期，仅含明确团队节点。
- 新注册批次按注册月份追踪；年初老未单独追踪。
- 月末状态；已付费为吸收出口。

## Files

- `sankey_links.xlsx`: 桑基图聚合流向
- `sankey_payload.json`: 交互图数据
- `summary.xlsx`: 汇总和校验结果
- `queries/service_period_sankey/2025_service_period_cohort_analysis.ipynb`: 可复查分析

## Limitations

- 不含B端入校。
- 不展示月内多次进出。
- 全年流量相加是月度人次，不是全年去重用户数。
```

- [ ] **Step 5: Run final verification**

Run:

```bash
python3 -m unittest tests.test_service_period_sankey -v
python3 - <<'PY'
from pathlib import Path
import json
import pandas as pd
import sys

root = Path('/Users/hilda/Documents/GitHub/c-query-cli-lite')
sys.path.insert(0, str(root / 'src'))
from service_period_sankey import validate_links

links = pd.read_excel(root / 'outputs/service_period_sankey_2025/sankey_links.xlsx')
validate_links(links)
payload = json.loads((root / 'outputs/service_period_sankey_2025/sankey_payload.json').read_text(encoding='utf-8'))
assert payload['default_view'] == 'new_registration'
assert payload['default_cohort'] == '2025-01'
assert 'old_unpaid' in payload['views']
assert '其他' not in json.dumps(payload, ensure_ascii=False)
print('final verification passed')
PY
```

Expected: all tests pass and the final line is `final verification passed`.

- [ ] **Step 6: Commit reproducibility assets**

```bash
git add queries/service_period_sankey/2025_service_period_cohort_analysis.ipynb outputs/service_period_sankey_2025/README.md
git commit -m "docs: add service period cohort analysis"
```

- [ ] **Step 7: Hand off the final result**

Return:

- the inline visualization directive for `service-period-cohort-sankey.html`;
- links to `sankey_links.xlsx`, `summary.xlsx`, the executed notebook, and `README.md`;
- three to five plain-language findings;
- the explicit caveat that B-end `入校` is not present in this C-end version.
