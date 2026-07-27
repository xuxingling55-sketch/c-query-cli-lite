WITH deposit_channel_users AS (
    SELECT
        TRIM(CAST(u_user AS STRING)) AS u_user,
        CASE
            WHEN business_gmv_attribution = '商业化' THEN 'APP'
            WHEN business_gmv_attribution = '电销' THEN '电销'
            ELSE '其他'
        END AS channel
    FROM dws.topic_order_detail
    WHERE paid_time_sk BETWEEN 20260624 AND 20260630
      AND sku_group_good_id = '74ec057c-4a49-45aa-a0ee-0fd2a410989a'
      AND business_gmv_attribution IN ('商业化', '电销')
    AND u_user IS NOT NULL
    GROUP BY
        TRIM(CAST(u_user AS STRING)),
        CASE
            WHEN business_gmv_attribution = '商业化' THEN 'APP'
            WHEN business_gmv_attribution = '电销' THEN '电销'
            ELSE '其他'
        END
),
deposit_source AS (
    SELECT
        CAST(order_id AS STRING) AS order_id,
        TRIM(CAST(u_user AS STRING)) AS u_user,
        COALESCE(MAX(business_user_pay_status_business_month), '未知') AS user_layer,
        MIN(paid_time) AS source_paid_time,
        SUM(sub_amount) AS source_amount
    FROM dws.topic_order_detail
    WHERE paid_time_sk BETWEEN 20260624 AND 20260630
      AND u_user IS NOT NULL
      AND sku_group_good_id = '74ec057c-4a49-45aa-a0ee-0fd2a410989a'
      AND business_gmv_attribution IN ('商业化', '电销')
    GROUP BY CAST(order_id AS STRING), TRIM(CAST(u_user AS STRING))
),
deposit_user_flags AS (
    SELECT
        u_user,
        MAX(CASE WHEN channel = 'APP' THEN 1 ELSE 0 END) AS is_app_deposit,
        MAX(CASE WHEN channel = '电销' THEN 1 ELSE 0 END) AS is_tele_deposit
    FROM deposit_channel_users
    GROUP BY u_user
),
tele_zhike_double_users AS (
    SELECT DISTINCT
        TRIM(CAST(a.user_id AS STRING)) AS user_id
    FROM aws.crm_order_info a
    LEFT JOIN (
        SELECT
            TRIM(CAST(u_user AS STRING)) AS u_user,
            team_names
        FROM dws.topic_order_detail
        WHERE paid_time_sk BETWEEN 20260624 AND 20260630
          AND sku_group_good_id = '74ec057c-4a49-45aa-a0ee-0fd2a410989a'
          AND u_user IS NOT NULL
        GROUP BY 1, 2
    ) b
      ON TRIM(CAST(a.user_id AS STRING)) = b.u_user
    WHERE SUBSTR(a.pay_time, 1, 10) BETWEEN '2026-06-24' AND '2026-06-30'
      AND a.good_kind_name_level_3 = '活动定金'
      AND a.workplace_id IN (4, 400, 702)
      AND a.regiment_id NOT IN (303, 0, 546)
      AND a.worker_id <> 0
      AND a.is_test = false
      AND array_contains(b.team_names, '入校')
      AND array_contains(b.team_names, '电销/网销')
),
reservoir_source AS (
    SELECT
        CAST(order_id AS STRING) AS order_id,
        TRIM(CAST(u_user AS STRING)) AS u_user,
        COALESCE(MAX(business_user_pay_status_business_month), '未知') AS user_layer,
        MIN(paid_time) AS source_paid_time,
        SUM(sub_amount) AS source_amount
    FROM dws.topic_order_detail
    WHERE paid_time_sk BETWEEN 20260522 AND 20260630
      AND u_user IS NOT NULL
      AND good_kind_name_level_2 = '同步课加培优课'
AND good_kind_name_level_3 = '同步课加培优课流量品'
      AND business_gmv_attribution IN ('商业化', '电销')
    GROUP BY CAST(order_id AS STRING), TRIM(CAST(u_user AS STRING))
),
reservoir_users AS (
    SELECT
        u_user,
        MIN(source_paid_time) AS first_source_paid_time
    FROM reservoir_source
    GROUP BY u_user
),
reservoir_users_total AS (
    SELECT COUNT(DISTINCT u_user) AS total_reservoir_users
    FROM reservoir_users
),
high_value_active_users AS (
    SELECT DISTINCT
        CAST(day AS INT) AS day,
        TRIM(CAST(u_user AS STRING)) AS u_user
    FROM aws.business_active_user_last_14_day
    WHERE day BETWEEN 20260701 AND 20260726
      AND business_user_pay_status_business_day = '高净值用户'
      AND u_user IS NOT NULL
),
high_value_active_total AS (
    SELECT COUNT(DISTINCT u_user) AS total_high_value_users
    FROM high_value_active_users
),
deposit_channel_totals AS (
    SELECT
        COUNT(DISTINCT CASE WHEN channel = 'APP' THEN u_user END) AS app_deposit_users,
        COUNT(DISTINCT CASE WHEN channel = '电销' THEN u_user END) AS tele_deposit_users
    FROM deposit_channel_users
),
deposit_double_total AS (
    SELECT COUNT(DISTINCT user_id) AS double_deposit_users
    FROM tele_zhike_double_users
),
deposit_users_total AS (
    SELECT
        dct.app_deposit_users + dct.tele_deposit_users + ddt.double_deposit_users AS total_deposit_users,
        dct.app_deposit_users AS app_deposit_users,
        dct.tele_deposit_users + ddt.double_deposit_users AS tele_deposit_users,
        ddt.double_deposit_users AS tele_zhike_double_deposit_users
    FROM deposit_channel_totals dct
    CROSS JOIN deposit_double_total ddt
),
org_team_dim AS (
    SELECT
        team_id,
        MAX(department_name) AS department_name
    FROM dw.dim_crm_organization
    GROUP BY team_id
),
orders_window AS (
    SELECT
        paid_time_sk,
        paid_time,
        TRIM(CAST(u_user AS STRING)) AS u_user,
        order_id,
        sub_amount,
        original_amount,
        order_amount,
        is_normal_price,
        is_test_user,
        sku_group_good_id,
        good_kind_name_level_1,
        business_good_kind_name_level_1,
        good_kind_name_level_2,
        good_kind_name_level_3,
        business_good_kind_name_level_3,
        good_stage_subject_cnt,
        good_stage_subject,
        business_user_pay_status_business,
        business_gmv_attribution,
        team_id
    FROM dws.topic_order_detail
    WHERE paid_time_sk BETWEEN 20260701 AND 20260726
      AND business_gmv_attribution IN ('商业化', '电销')
),
big_order AS (
    SELECT
        TRIM(CAST(u_user AS STRING)) AS u_user,
        MIN(paid_time) AS first_big_paid_time,
        COUNT(DISTINCT order_id) AS big_order_cnt,
        SUM(sub_amount) AS big_amount
    FROM dws.topic_order_detail
    WHERE paid_time_sk BETWEEN 20260701 AND 20260726
      AND u_user IS NOT NULL
      AND is_normal_price = 1
      AND original_amount >= 39
      AND business_good_kind_name_level_1 = '组合品'
      AND business_gmv_attribution IN ('商业化', '电销')
    GROUP BY TRIM(CAST(u_user AS STRING))
),
reservoir_big_order AS (
    SELECT
        TRIM(CAST(u_user AS STRING)) AS u_user,
        paid_time_sk,
        MIN(paid_time) AS paid_time,
        CAST(order_id AS STRING) AS order_id,
        SUM(sub_amount) AS big_amount
    FROM dws.topic_order_detail
    WHERE paid_time_sk BETWEEN 20260522 AND 20260726
      AND u_user IS NOT NULL
      AND is_normal_price = 1
      AND original_amount >= 39
      AND business_good_kind_name_level_1 = '组合品'
      AND business_gmv_attribution IN ('商业化', '电销')
    GROUP BY TRIM(CAST(u_user AS STRING)), paid_time_sk, CAST(order_id AS STRING)
),
reservoir_conversion_order AS (
    SELECT
        TRIM(CAST(o.u_user AS STRING)) AS u_user,
        o.paid_time_sk,
        MIN(o.paid_time) AS paid_time,
        CAST(o.order_id AS STRING) AS order_id,
        SUM(o.sub_amount) AS conversion_amount
    FROM dws.topic_order_detail o
    LEFT JOIN reservoir_source rs
      ON TRIM(CAST(o.u_user AS STRING)) = rs.u_user
     AND CAST(o.order_id AS STRING) = rs.order_id
    WHERE o.paid_time_sk BETWEEN 20260522 AND 20260726
      AND o.u_user IS NOT NULL
      AND o.business_gmv_attribution IN ('商业化', '电销')
      AND rs.order_id IS NULL
    GROUP BY TRIM(CAST(o.u_user AS STRING)), o.paid_time_sk, CAST(o.order_id AS STRING)
),
deposit_tail_total AS (
    SELECT
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN d.u_user END) AS total_deposit_tail_users,
        SUM(CASE WHEN b.u_user IS NOT NULL THEN b.big_amount ELSE 0 END) AS total_deposit_tail_revenue
    FROM deposit_source d
    LEFT JOIN big_order b
      ON d.u_user = b.u_user
     AND b.first_big_paid_time >= d.source_paid_time
),
reservoir_tail_total AS (
    SELECT
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN r.u_user END) AS total_reservoir_tail_users,
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN b.order_id END) AS total_reservoir_tail_orders,
        SUM(CASE WHEN b.u_user IS NOT NULL THEN b.big_amount ELSE 0 END) AS total_reservoir_tail_revenue
    FROM reservoir_users r
    LEFT JOIN reservoir_big_order b
      ON r.u_user = b.u_user
     AND b.paid_time_sk BETWEEN 20260701 AND 20260726
     AND b.paid_time >= r.first_source_paid_time
),
reservoir_june_tail_total AS (
    SELECT
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN r.u_user END) AS total_reservoir_june_tail_users,
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN b.order_id END) AS total_reservoir_june_tail_orders,
        SUM(CASE WHEN b.u_user IS NOT NULL THEN b.big_amount ELSE 0 END) AS total_reservoir_june_tail_revenue
    FROM reservoir_users r
    LEFT JOIN reservoir_big_order b
      ON r.u_user = b.u_user
     AND b.paid_time_sk BETWEEN 20260601 AND 20260630
     AND b.paid_time >= r.first_source_paid_time
),
reservoir_may_tail_total AS (
    SELECT
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN r.u_user END) AS total_reservoir_may_tail_users,
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN b.order_id END) AS total_reservoir_may_tail_orders,
        SUM(CASE WHEN b.u_user IS NOT NULL THEN b.big_amount ELSE 0 END) AS total_reservoir_may_tail_revenue
    FROM reservoir_users r
    LEFT JOIN reservoir_big_order b
      ON r.u_user = b.u_user
     AND b.paid_time_sk BETWEEN 20260522 AND 20260531
     AND b.paid_time >= r.first_source_paid_time
),
reservoir_total_tail_total AS (
    SELECT
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN r.u_user END) AS total_reservoir_total_tail_users,
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN b.order_id END) AS total_reservoir_total_tail_orders,
        SUM(CASE WHEN b.u_user IS NOT NULL THEN b.big_amount ELSE 0 END) AS total_reservoir_total_tail_revenue
    FROM reservoir_users r
    LEFT JOIN reservoir_big_order b
     ON r.u_user = b.u_user
     AND b.paid_time_sk BETWEEN 20260522 AND 20260726
     AND b.paid_time >= r.first_source_paid_time
),
reservoir_conversion_total AS (
    SELECT
        COUNT(DISTINCT CASE WHEN c.u_user IS NOT NULL THEN r.u_user END) AS total_reservoir_conversion_users,
        COUNT(DISTINCT CASE WHEN c.u_user IS NOT NULL THEN c.order_id END) AS total_reservoir_conversion_orders,
        SUM(CASE WHEN c.u_user IS NOT NULL THEN c.conversion_amount ELSE 0 END) AS total_reservoir_conversion_revenue
    FROM reservoir_users r
    LEFT JOIN reservoir_conversion_order c
      ON r.u_user = c.u_user
     AND c.paid_time_sk BETWEEN 20260522 AND 20260726
     AND c.paid_time >= r.first_source_paid_time
),
reservoir_july_conversion_total AS (
    SELECT
        COUNT(DISTINCT CASE WHEN c.u_user IS NOT NULL THEN r.u_user END) AS total_reservoir_july_conversion_users,
        COUNT(DISTINCT CASE WHEN c.u_user IS NOT NULL THEN c.order_id END) AS total_reservoir_july_conversion_orders,
        SUM(CASE WHEN c.u_user IS NOT NULL THEN c.conversion_amount ELSE 0 END) AS total_reservoir_july_conversion_revenue
    FROM reservoir_users r
    LEFT JOIN reservoir_conversion_order c
      ON r.u_user = c.u_user
     AND c.paid_time_sk BETWEEN 20260701 AND 20260726
     AND c.paid_time >= r.first_source_paid_time
),
high_value_renew_total AS (
    SELECT
        COUNT(DISTINCT CASE WHEN o.u_user IS NOT NULL THEN hv.u_user END) AS total_high_value_renew_users,
        SUM(CASE WHEN o.u_user IS NOT NULL THEN o.sub_amount ELSE 0 END) AS total_high_value_renew_revenue
    FROM high_value_active_users hv
    LEFT JOIN orders_window o
      ON hv.u_user = o.u_user
     AND hv.day = o.paid_time_sk
     AND o.business_good_kind_name_level_1 = '组合品'
),
crm_tele_daily AS (
    SELECT
        CAST(REGEXP_REPLACE(SUBSTR(a.pay_time, 1, 10), '-', '') AS INT) AS day,
        SUM(a.amount) AS crm_tele_revenue
    FROM aws.crm_order_info a
    LEFT JOIN dw.dim_crm_organization b
        ON a.workplace_id = b.id
    LEFT JOIN dw.dim_crm_organization c
        ON a.department_id = c.id
    LEFT JOIN dw.dim_crm_organization d
        ON a.regiment_id = d.id
    LEFT JOIN dw.dim_crm_organization e
        ON a.heads_id = e.id
    LEFT JOIN dw.dim_crm_organization f
        ON a.team_id = f.id
    WHERE SUBSTR(a.pay_time, 1, 10) BETWEEN '2026-07-01' AND '2026-07-26'
      AND a.workplace_id IN (4, 400, 702)
      AND a.regiment_id NOT IN (303, 0, 546)
      AND a.worker_id <> 0
      AND a.is_test = false
    GROUP BY CAST(REGEXP_REPLACE(SUBSTR(a.pay_time, 1, 10), '-', '') AS INT)
),
day_base AS (
    SELECT paid_time_sk AS day FROM orders_window
    UNION
    SELECT day FROM crm_tele_daily
    UNION
    SELECT day FROM high_value_active_users
),
deposit_tail_cumulative_by_day AS (
    SELECT
        db.day,
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN d.u_user END) AS cumulative_deposit_tail_users,
        SUM(CASE WHEN b.u_user IS NOT NULL THEN b.big_amount ELSE 0 END) AS cumulative_deposit_tail_revenue
    FROM day_base db
    LEFT JOIN deposit_source d
      ON 1 = 1
    LEFT JOIN big_order b
      ON d.u_user = b.u_user
     AND b.first_big_paid_time >= d.source_paid_time
     AND CAST(REGEXP_REPLACE(SUBSTR(b.first_big_paid_time, 1, 10), '-', '') AS INT) <= db.day
    GROUP BY db.day
),
reservoir_tail_cumulative_by_day AS (
    SELECT
        db.day,
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN r.u_user END) AS cumulative_reservoir_tail_users,
        COUNT(DISTINCT CASE WHEN b.u_user IS NOT NULL THEN b.order_id END) AS cumulative_reservoir_tail_orders,
        SUM(CASE WHEN b.u_user IS NOT NULL THEN b.big_amount ELSE 0 END) AS cumulative_reservoir_tail_revenue
    FROM day_base db
    LEFT JOIN reservoir_users r
      ON 1 = 1
    LEFT JOIN reservoir_big_order b
      ON r.u_user = b.u_user
     AND b.paid_time_sk BETWEEN 20260701 AND db.day
     AND b.paid_time >= r.first_source_paid_time
    GROUP BY db.day
),
reservoir_conversion_cumulative_by_day AS (
    SELECT
        db.day,
        COUNT(DISTINCT CASE WHEN c.u_user IS NOT NULL THEN r.u_user END) AS cumulative_reservoir_conversion_users,
        COUNT(DISTINCT CASE WHEN c.u_user IS NOT NULL THEN c.order_id END) AS cumulative_reservoir_conversion_orders,
        SUM(CASE WHEN c.u_user IS NOT NULL THEN c.conversion_amount ELSE 0 END) AS cumulative_reservoir_conversion_revenue,
        COUNT(DISTINCT CASE WHEN c.u_user IS NOT NULL AND c.paid_time_sk >= 20260701 THEN r.u_user END) AS cumulative_reservoir_july_conversion_users,
        COUNT(DISTINCT CASE WHEN c.u_user IS NOT NULL AND c.paid_time_sk >= 20260701 THEN c.order_id END) AS cumulative_reservoir_july_conversion_orders,
        SUM(CASE WHEN c.u_user IS NOT NULL AND c.paid_time_sk >= 20260701 THEN c.conversion_amount ELSE 0 END) AS cumulative_reservoir_july_conversion_revenue
    FROM day_base db
    LEFT JOIN reservoir_users r
      ON 1 = 1
    LEFT JOIN reservoir_conversion_order c
      ON r.u_user = c.u_user
     AND c.paid_time_sk BETWEEN 20260522 AND db.day
     AND c.paid_time >= r.first_source_paid_time
    GROUP BY db.day
),
daily AS (
    SELECT
        db.day AS day,
        SUM(CASE WHEN business_gmv_attribution = '商业化' THEN o.sub_amount ELSE 0 END) + MAX(COALESCE(ctd.crm_tele_revenue, 0)) AS revenue_amount,
        MAX(COALESCE(ctd.crm_tele_revenue, 0)) AS revenue_telesale_amount,
        SUM(CASE WHEN business_gmv_attribution = '商业化' THEN sub_amount ELSE 0 END) AS revenue_app_amount,
        COUNT(DISTINCT o.order_id) AS total_orders,
        SUM(o.sub_amount) AS total_revenue_amount,
        MAX(dut.total_deposit_users) AS deposit_users,
        MAX(dtc.cumulative_deposit_tail_users) AS deposit_tail_users,
        MAX(dtc.cumulative_deposit_tail_revenue) AS deposit_tail_revenue,
        MAX(dtt.total_deposit_tail_users) AS deposit_tail_total_users,
        MAX(dtt.total_deposit_tail_revenue) AS deposit_tail_total_revenue,
        MAX(dtc.cumulative_deposit_tail_users) AS deposit_tail_cumulative_users,
        MAX(dtc.cumulative_deposit_tail_revenue) AS deposit_tail_cumulative_revenue,
        MAX(rut.total_reservoir_users) AS reservoir_users,
        MAX(rtc.cumulative_reservoir_tail_users) AS reservoir_tail_users,
        MAX(rtc.cumulative_reservoir_tail_orders) AS reservoir_tail_orders,
        MAX(rtc.cumulative_reservoir_tail_revenue) AS reservoir_tail_revenue,
        MAX(rtt.total_reservoir_tail_users) AS reservoir_tail_total_users,
        MAX(rtt.total_reservoir_tail_orders) AS reservoir_tail_total_orders,
        MAX(rtt.total_reservoir_tail_revenue) AS reservoir_tail_total_revenue,
        MAX(rjt.total_reservoir_june_tail_users) AS reservoir_june_tail_users,
        MAX(rjt.total_reservoir_june_tail_orders) AS reservoir_june_tail_orders,
        MAX(rjt.total_reservoir_june_tail_revenue) AS reservoir_june_tail_revenue,
        MAX(rmt.total_reservoir_may_tail_users) AS reservoir_may_tail_users,
        MAX(rmt.total_reservoir_may_tail_orders) AS reservoir_may_tail_orders,
        MAX(rmt.total_reservoir_may_tail_revenue) AS reservoir_may_tail_revenue,
        MAX(ratt.total_reservoir_total_tail_users) AS reservoir_total_tail_users,
        MAX(ratt.total_reservoir_total_tail_orders) AS reservoir_total_tail_orders,
        MAX(ratt.total_reservoir_total_tail_revenue) AS reservoir_total_tail_revenue,
        MAX(rct.total_reservoir_conversion_users) AS reservoir_conversion_users,
        MAX(rct.total_reservoir_conversion_orders) AS reservoir_conversion_orders,
        MAX(rct.total_reservoir_conversion_revenue) AS reservoir_conversion_revenue,
        MAX(rjct.total_reservoir_july_conversion_users) AS reservoir_july_conversion_users,
        MAX(rjct.total_reservoir_july_conversion_orders) AS reservoir_july_conversion_orders,
        MAX(rjct.total_reservoir_july_conversion_revenue) AS reservoir_july_conversion_revenue,
        MAX(rtc.cumulative_reservoir_tail_users) AS reservoir_tail_cumulative_users,
        MAX(rtc.cumulative_reservoir_tail_orders) AS reservoir_tail_cumulative_orders,
        MAX(rtc.cumulative_reservoir_tail_revenue) AS reservoir_tail_cumulative_revenue,
        MAX(rcc.cumulative_reservoir_conversion_users) AS reservoir_conversion_cumulative_users,
        MAX(rcc.cumulative_reservoir_conversion_orders) AS reservoir_conversion_cumulative_orders,
        MAX(rcc.cumulative_reservoir_conversion_revenue) AS reservoir_conversion_cumulative_revenue,
        MAX(rcc.cumulative_reservoir_july_conversion_users) AS reservoir_july_conversion_cumulative_users,
        MAX(rcc.cumulative_reservoir_july_conversion_orders) AS reservoir_july_conversion_cumulative_orders,
        MAX(rcc.cumulative_reservoir_july_conversion_revenue) AS reservoir_july_conversion_cumulative_revenue,
       COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 = '小初高品' THEN o.order_id END) AS family_orders,
       COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_1 = '组合品' THEN o.order_id END) AS family_base_orders,
       SUM(CASE WHEN o.business_good_kind_name_level_3 = '小初高品' AND o.u_user IS NOT NULL AND o.is_test_user = 0 AND o.original_amount >= 39 THEN o.sub_amount ELSE 0 END) AS family_revenue,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 = '小初高品' AND org.department_name LIKE '%小学%' THEN o.order_id END) AS family_primary_orders,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_1 = '组合品' AND org.department_name LIKE '%小学%' THEN o.order_id END) AS family_primary_base_orders,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 = '小初高品' AND org.department_name LIKE '%初中%' THEN o.order_id END) AS family_middle_orders,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_1 = '组合品' AND org.department_name LIKE '%初中%' THEN o.order_id END) AS family_middle_base_orders,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 = '小初高品' AND org.department_name LIKE '%高中%' THEN o.order_id END) AS family_high_orders,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_1 = '组合品' AND org.department_name LIKE '%高中%' THEN o.order_id END) AS family_high_base_orders,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 = '小学品加拓展' THEN o.order_id END) AS from_primary_orders,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 IN ('小学品', '小学品加拓展') THEN o.order_id END) AS from_primary_base_orders,
        SUM(CASE WHEN o.u_user IS NOT NULL AND o.is_test_user = 0 AND o.original_amount >= 39 AND (
              (o.good_kind_name_level_3 = '拓展课' AND o.good_stage_subject_cnt = 1 AND o.good_stage_subject REGEXP '1-2-specialCourse')
           OR (o.good_kind_name_level_3 = '拓展课' AND o.good_stage_subject_cnt = 1 AND o.good_stage_subject REGEXP '1-6-specialCourse')
           OR (o.good_kind_name_level_3 = '拓展课' AND o.good_stage_subject_cnt = 1 AND o.good_stage_subject REGEXP '1-7-specialCourse')
           OR (o.good_kind_name_level_3 = '拓展课' AND o.good_stage_subject_cnt = 3 AND o.good_stage_subject REGEXP '1-2-specialCourse' AND o.good_stage_subject REGEXP '1-6-specialCourse' AND o.good_stage_subject REGEXP '1-7-specialCourse')
           OR o.business_good_kind_name_level_3 IN ('小学品加拓展')
        ) THEN o.sub_amount ELSE 0 END) AS from_primary_revenue,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 = '小学品加拓展' AND org.department_name LIKE '%小学%' THEN o.order_id END) AS from_primary_primary_orders
        ,COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_3 IN ('小学品', '小学品加拓展') AND org.department_name LIKE '%小学%' THEN o.order_id END) AS from_primary_primary_base_orders,
        MAX(hvbt.total_high_value_users) AS high_value_users,
        MAX(hvrt.total_high_value_renew_users) AS high_value_renew_users,
        MAX(hvrt.total_high_value_renew_revenue) AS high_value_renew_revenue
    FROM day_base db
    LEFT JOIN orders_window o
      ON db.day = o.paid_time_sk
    LEFT JOIN crm_tele_daily ctd
      ON db.day = ctd.day
    CROSS JOIN deposit_users_total dut
    CROSS JOIN deposit_tail_total dtt
    CROSS JOIN reservoir_users_total rut
    CROSS JOIN reservoir_tail_total rtt
    CROSS JOIN reservoir_june_tail_total rjt
    CROSS JOIN reservoir_may_tail_total rmt
    CROSS JOIN reservoir_total_tail_total ratt
    CROSS JOIN reservoir_conversion_total rct
    CROSS JOIN reservoir_july_conversion_total rjct
    CROSS JOIN high_value_active_total hvbt
    CROSS JOIN high_value_renew_total hvrt
    LEFT JOIN deposit_tail_cumulative_by_day dtc
      ON db.day = dtc.day
    LEFT JOIN reservoir_tail_cumulative_by_day rtc
      ON db.day = rtc.day
    LEFT JOIN reservoir_conversion_cumulative_by_day rcc
      ON db.day = rcc.day
    LEFT JOIN high_value_active_users hv
      ON o.u_user = hv.u_user
     AND hv.day = o.paid_time_sk
    LEFT JOIN org_team_dim org
      ON o.team_id = org.team_id
    GROUP BY db.day
)
SELECT *
FROM daily
ORDER BY day;
