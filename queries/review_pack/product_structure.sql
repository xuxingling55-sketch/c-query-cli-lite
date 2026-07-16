WITH periods AS (
    SELECT '本期' AS period, {{CURRENT_START}} AS start_day, {{CURRENT_END}} AS end_day
    UNION ALL
    SELECT '去年同期', {{LAST_YEAR_START}}, {{LAST_YEAR_END}}
),
order_rows AS (
    SELECT
        p.period,
        o.order_id,
        CAST(o.u_user AS VARCHAR) AS user_id,
        o.business_good_kind_name_level_1,
        o.business_good_kind_name_level_3,
        o.good_name,
        o.good_kind_name_level_3,
        o.good_stage_subject_cnt,
        o.good_stage_subject,
        o.original_amount,
        o.sub_amount
    FROM periods p
    JOIN dws.topic_order_detail o
      ON o.paid_time_sk BETWEEN p.start_day AND p.end_day
    WHERE o.u_user IS NOT NULL
      AND o.is_test_user = 0
      AND o.original_amount >= 39
      AND o.business_gmv_attribution IN ('商业化', '电销')
),
order_level AS (
    SELECT
        period,
        order_id,
        MIN(user_id) AS user_id,
        MAX(CASE WHEN business_good_kind_name_level_1 = '组合品' THEN 1 ELSE 0 END) AS is_combo,
        MAX(CASE WHEN business_good_kind_name_level_1 = '零售商品' THEN 1 ELSE 0 END) AS is_retail,
        MAX(CASE WHEN business_good_kind_name_level_3 = '小初高品' THEN 1 ELSE 0 END) AS is_family,
        MAX(CASE
            WHEN business_good_kind_name_level_3 = '小学品加拓展' THEN 1
            WHEN good_name LIKE '从小学%' AND good_name NOT LIKE '%系列%' THEN 1
            WHEN good_kind_name_level_3 = '拓展课'
             AND good_stage_subject_cnt = 1
             AND (
                 good_stage_subject REGEXP '1-2-specialCourse'
                 OR good_stage_subject REGEXP '1-6-specialCourse'
                 OR good_stage_subject REGEXP '1-7-specialCourse'
             ) THEN 1
            ELSE 0
        END) AS is_from_primary,
        MAX(CASE WHEN original_amount >= 198 AND original_amount < 199 THEN 1 ELSE 0 END) AS is_198,
        MAX(CASE WHEN original_amount >= 498 AND original_amount < 499 THEN 1 ELSE 0 END) AS is_498,
        MAX(CASE WHEN original_amount >= 1000 THEN 1 ELSE 0 END) AS is_1000_plus,
        SUM(sub_amount) AS revenue
    FROM order_rows
    GROUP BY period, order_id
),
product_orders AS (
    SELECT period, order_id, user_id, revenue, '组合品' AS product FROM order_level WHERE is_combo = 1
    UNION ALL SELECT period, order_id, user_id, revenue, '零售品' FROM order_level WHERE is_retail = 1
    UNION ALL SELECT period, order_id, user_id, revenue, '家庭包' FROM order_level WHERE is_family = 1
    UNION ALL SELECT period, order_id, user_id, revenue, '从小学系列' FROM order_level WHERE is_from_primary = 1
    UNION ALL SELECT period, order_id, user_id, revenue, '198' FROM order_level WHERE is_198 = 1
    UNION ALL SELECT period, order_id, user_id, revenue, '498' FROM order_level WHERE is_498 = 1
    UNION ALL SELECT period, order_id, user_id, revenue, '千元及以上' FROM order_level WHERE is_1000_plus = 1
),
summary AS (
    SELECT
        period,
        product,
        COUNT(DISTINCT order_id) AS orders,
        COUNT(DISTINCT user_id) AS pay_users,
        SUM(revenue) AS revenue
    FROM product_orders
    GROUP BY period, product
),
private_totals AS (
    SELECT
        period,
        COUNT(DISTINCT order_id) AS orders,
        COUNT(DISTINCT user_id) AS pay_users,
        SUM(revenue) AS revenue
    FROM order_level
    GROUP BY period
),
active_totals AS (
    SELECT p.period, COUNT(DISTINCT CAST(a.u_user AS VARCHAR)) AS active_users
    FROM periods p
    JOIN aws.business_active_user_last_14_day a
      ON a.day BETWEEN p.start_day AND p.end_day
    WHERE a.u_user IS NOT NULL
      AND a.business_gmv_attribution IN ('商业化', '电销')
    GROUP BY p.period
),
metrics AS (
    SELECT period, product, '订单量' AS metric, CAST(orders AS DOUBLE) AS value FROM summary
    UNION ALL SELECT period, product, '付费人数', CAST(pay_users AS DOUBLE) FROM summary
    UNION ALL SELECT period, product, '营收', revenue FROM summary
    UNION ALL SELECT s.period, s.product, '订单占比', s.orders / NULLIF(t.orders, 0) FROM summary s JOIN private_totals t ON s.period=t.period
    UNION ALL SELECT s.period, s.product, '付费人数占比', s.pay_users / NULLIF(t.pay_users, 0) FROM summary s JOIN private_totals t ON s.period=t.period
    UNION ALL SELECT s.period, s.product, '营收占比', s.revenue / NULLIF(t.revenue, 0) FROM summary s JOIN private_totals t ON s.period=t.period
    UNION ALL SELECT s.period, s.product, '转化率', s.pay_users / NULLIF(a.active_users, 0) FROM summary s JOIN active_totals a ON s.period=a.period
    UNION ALL SELECT period, product, '客单价', revenue / NULLIF(pay_users, 0) FROM summary
    UNION ALL SELECT s.period, s.product, 'ARPU', s.revenue / NULLIF(a.active_users, 0) FROM summary s JOIN active_totals a ON s.period=a.period
)
SELECT
    period,
    '私域整体' AS channel,
    '商品主题' AS dimension_type,
    product AS dimension_value,
    metric,
    value,
    'v1' AS source_version,
    CURRENT_TIMESTAMP AS data_updated_at,
    'price_basis=original_amount' AS definition_id
FROM metrics
LIMIT 10000
