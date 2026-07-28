WITH periods AS (
    SELECT '本期' AS period, {{CURRENT_START}} AS start_day, {{CURRENT_END}} AS end_day
    UNION ALL
    SELECT '去年同期', {{LAST_YEAR_START}}, {{LAST_YEAR_END}}
),
business_order_rows AS (
    SELECT
        p.period,
        CASE
            WHEN o.business_gmv_attribution = '商业化' THEN 'APP'
            WHEN o.business_gmv_attribution = '电销' THEN '销售'
        END AS channel,
        o.order_id,
        CAST(o.u_user AS VARCHAR) AS user_id,
        o.sub_amount
    FROM periods p
    JOIN dws.topic_order_detail o
      ON o.paid_time_sk BETWEEN p.start_day AND p.end_day
    WHERE o.business_gmv_attribution IN ('商业化', '电销')
      AND o.u_user IS NOT NULL
      AND o.is_test_user = 0
      AND o.original_amount >= 39
),
business_channels AS (
    SELECT period, channel,
           COUNT(DISTINCT order_id) AS orders,
           COUNT(DISTINCT user_id) AS users,
           SUM(sub_amount) AS revenue
    FROM business_order_rows
    GROUP BY period, channel
    UNION ALL
    SELECT period, '私域整体',
           COUNT(DISTINCT order_id), COUNT(DISTINCT user_id), SUM(sub_amount)
    FROM business_order_rows
    GROUP BY period
),
service_order_rows AS (
    SELECT
        p.period,
        CASE
            WHEN o.business_gmv_attribution = '商业化' THEN 'APP'
            WHEN o.business_gmv_attribution = '电销' THEN '销售'
        END AS channel,
        o.order_id,
        SUM(o.sub_amount) AS revenue
    FROM periods p
    JOIN dws.topic_order_detail o
      ON o.paid_time_sk BETWEEN p.start_day AND p.end_day
    WHERE o.u_user IS NOT NULL
      AND o.is_test_user = 0
      AND o.original_amount >= 39
      AND o.business_gmv_attribution IN ('商业化', '电销')
      AND (
          array_contains(o.correct_team_names, '商业化-APP')
          OR array_contains(o.correct_team_names, '电销/网销')
      )
    GROUP BY p.period, channel, o.order_id
),
service_summary AS (
    SELECT period, channel, SUM(revenue) AS service_revenue
    FROM service_order_rows
    GROUP BY period, channel
    UNION ALL
    SELECT period, '私域整体', SUM(revenue)
    FROM service_order_rows
    GROUP BY period
),
base_metrics AS (
    SELECT period, channel, '营收' AS metric, revenue AS value FROM business_channels
    UNION ALL SELECT period, channel, '订单量', CAST(orders AS DOUBLE) FROM business_channels
    UNION ALL SELECT period, channel, '付费人数', CAST(users AS DOUBLE) FROM business_channels
    UNION ALL
    SELECT b.period, b.channel, '服务期营收', s.service_revenue
    FROM business_channels b JOIN service_summary s
      ON b.period = s.period AND b.channel = s.channel
    UNION ALL
    SELECT b.period, b.channel, '业务营收与服务期营收差额', b.revenue - s.service_revenue
    FROM business_channels b JOIN service_summary s
      ON b.period = s.period AND b.channel = s.channel
),
target_metrics AS (
    SELECT '本期' AS period, '私域整体' AS channel, '活动目标' AS metric,
           CAST({{TARGET}} AS DOUBLE) AS value
    UNION ALL
    SELECT period, channel, '目标完成额', revenue
    FROM business_channels WHERE period = '本期' AND channel = '私域整体'
    UNION ALL
    SELECT period, channel, '目标完成率', revenue / NULLIF(CAST({{TARGET}} AS DOUBLE), 0)
    FROM business_channels WHERE period = '本期' AND channel = '私域整体'
    UNION ALL
    SELECT period, channel, '目标差额', CAST({{TARGET}} AS DOUBLE) - revenue
    FROM business_channels WHERE period = '本期' AND channel = '私域整体'
    UNION ALL SELECT '本期', '私域整体', '时间进度',
        LEAST(
            CAST(1 AS DOUBLE),
            GREATEST(
                CAST(0 AS DOUBLE),
                CAST(DATEDIFF(CURRENT_DATE(), STR_TO_DATE(CAST({{CURRENT_START}} AS VARCHAR), '%Y%m%d')) + 1 AS DOUBLE)
                / CAST(DATEDIFF(STR_TO_DATE(CAST({{CURRENT_END}} AS VARCHAR), '%Y%m%d'), STR_TO_DATE(CAST({{CURRENT_START}} AS VARCHAR), '%Y%m%d')) + 1 AS DOUBLE)
            )
        )
    UNION ALL
    SELECT period, channel, '营收进度与时间进度差',
           revenue / NULLIF(CAST({{TARGET}} AS DOUBLE), 0) - LEAST(
               CAST(1 AS DOUBLE),
               GREATEST(
                   CAST(0 AS DOUBLE),
                   CAST(DATEDIFF(CURRENT_DATE(), STR_TO_DATE(CAST({{CURRENT_START}} AS VARCHAR), '%Y%m%d')) + 1 AS DOUBLE)
                   / CAST(DATEDIFF(STR_TO_DATE(CAST({{CURRENT_END}} AS VARCHAR), '%Y%m%d'), STR_TO_DATE(CAST({{CURRENT_START}} AS VARCHAR), '%Y%m%d')) + 1 AS DOUBLE)
               )
           )
    FROM business_channels WHERE period = '本期' AND channel = '私域整体'
),
metrics AS (
    SELECT period, channel, metric, value FROM base_metrics
    UNION ALL
    SELECT period, channel, metric, value FROM target_metrics
)
SELECT
    period,
    channel,
    '经营总览' AS dimension_type,
    channel AS dimension_value,
    metric,
    value,
    'v1' AS source_version,
    CURRENT_TIMESTAMP AS data_updated_at,
    'overview.private_business_and_service.v1' AS definition_id
FROM metrics
LIMIT 10000
