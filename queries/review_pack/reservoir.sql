WITH strategy_periods AS (
    SELECT '本期' AS period,
           {{RESERVOIR_SOURCE_START}} AS source_start, {{RESERVOIR_SOURCE_END}} AS source_end
    UNION ALL
    SELECT '去年同期',
           CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST({{RESERVOIR_SOURCE_START}} AS VARCHAR), '%Y%m%d'), INTERVAL 1 YEAR), '%Y%m%d') AS INT),
           CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST({{RESERVOIR_SOURCE_END}} AS VARCHAR), '%Y%m%d'), INTERVAL 1 YEAR), '%Y%m%d') AS INT)
),
channels AS (SELECT '私域整体' channel UNION ALL SELECT 'APP' UNION ALL SELECT '销售'),
user_layer_values AS (SELECT '新增' user_layer UNION ALL SELECT '老未' UNION ALL SELECT '续费' UNION ALL SELECT '高净值汇总' UNION ALL SELECT '高净值－当年毕业' UNION ALL SELECT '高净值－历史大会员可续购' UNION ALL SELECT '高净值－历史大会员不可续购' UNION ALL SELECT '高净值－其他组合品' UNION ALL SELECT '未映射'),
stage_values AS (SELECT '1–3 年级' stage UNION ALL SELECT '4–6 年级' UNION ALL SELECT '初中' UNION ALL SELECT '高中' UNION ALL SELECT '未知学段'),
products AS (SELECT '组合品' product UNION ALL SELECT '498' UNION ALL SELECT '其他商品'),
reservoir_source_rows AS (
    SELECT p.period,
           CASE WHEN o.business_gmv_attribution='商业化' THEN 'APP' ELSE '销售' END AS channel,
           CAST(o.u_user AS VARCHAR) AS user_id, o.order_id, MIN(o.paid_time) AS source_time,
           SUM(o.sub_amount) AS source_amount,
           CASE WHEN o.business_user_pay_status_statistics IN ('新增','新用户') THEN '新增'
                WHEN o.business_user_pay_status_statistics='老未' THEN '老未'
                WHEN o.business_user_pay_status_statistics IN ('续费用户','续费') THEN '续费'
                WHEN o.business_user_pay_status_statistics='高净值用户' THEN '高净值汇总'
                ELSE '未映射' END AS user_layer
    FROM strategy_periods p
    JOIN dws.topic_order_detail o ON o.paid_time_sk BETWEEN p.source_start AND p.source_end
    WHERE o.u_user IS NOT NULL AND o.is_test_user=0
      AND o.business_gmv_attribution IN ('商业化','电销')
      AND (
          (p.period='本期' AND o.good_kind_name_level_2='同步课加培优课' AND o.good_kind_name_level_3='同步课加培优课流量品')
          OR (p.period='去年同期' AND o.sku_group_good_id IN ('2ad36071-17ec-4eda-9a7a-27c005fd61fa','10138aa5-ea9c-4723-9ac7-4aab637e7218'))
      )
    GROUP BY p.period, CASE WHEN o.business_gmv_attribution='商业化' THEN 'APP' ELSE '销售' END,
             CAST(o.u_user AS VARCHAR), o.order_id,
             CASE WHEN o.business_user_pay_status_statistics IN ('新增','新用户') THEN '新增'
                  WHEN o.business_user_pay_status_statistics='老未' THEN '老未'
                  WHEN o.business_user_pay_status_statistics IN ('续费用户','续费') THEN '续费'
                  WHEN o.business_user_pay_status_statistics='高净值用户' THEN '高净值汇总' ELSE '未映射' END
),
reservoir_source_ranked AS (
    SELECT period,channel,user_id,order_id,source_time,source_amount,user_layer,COUNT(*) OVER(PARTITION BY period,user_id) source_orders,
           SUM(source_amount) OVER(PARTITION BY period,user_id) total_source_amount,
           ROW_NUMBER() OVER(PARTITION BY period, user_id ORDER BY source_time DESC, order_id DESC) source_rank
    FROM reservoir_source_rows s
),
reservoir_users AS (
    SELECT period,channel,user_id,source_time first_source_time,source_orders,total_source_amount source_amount,user_layer
    FROM reservoir_source_ranked WHERE source_rank = 1
),
active_audience AS (
    SELECT period,user_id,stage FROM (
      SELECT p.period,CAST(a.u_user AS VARCHAR) user_id,
       CASE WHEN a.grade_name_month IN ('一年级','二年级','三年级') THEN '1–3 年级' WHEN a.grade_name_month IN ('四年级','五年级','六年级') THEN '4–6 年级' WHEN a.grade_name_month IN ('七年级','八年级','九年级','初一','初二','初三') THEN '初中' WHEN a.grade_name_month IN ('高一','高二','高三','十年级') THEN '高中' ELSE '未知学段' END stage,
       ROW_NUMBER() OVER(PARTITION BY p.period,CAST(a.u_user AS VARCHAR) ORDER BY a.day DESC) fact_rank
      FROM strategy_periods p JOIN aws.business_active_user_last_14_day a ON a.day BETWEEN CASE WHEN p.period='本期' THEN {{CURRENT_START}} ELSE {{LAST_YEAR_START}} END AND CASE WHEN p.period='本期' THEN {{CURRENT_END}} ELSE {{LAST_YEAR_END}} END WHERE a.u_user IS NOT NULL
    ) x WHERE fact_rank = 1
),
conversion_order_rows AS (
    SELECT r.period,r.channel,r.user_id,o.order_id,
           CASE WHEN o.original_amount>=498 AND o.original_amount<499 THEN '498'
                WHEN o.business_good_kind_name_level_1='组合品' THEN '组合品'
                ELSE '其他商品' END flow_product,
           SUM(o.sub_amount) revenue
    FROM reservoir_users r JOIN strategy_periods p ON r.period=p.period
    JOIN dws.topic_order_detail o ON CAST(o.u_user AS VARCHAR)=r.user_id
      AND o.paid_time>r.first_source_time
      AND o.paid_time_sk BETWEEN CASE WHEN p.period='本期' THEN {{CURRENT_START}} ELSE {{LAST_YEAR_START}} END
                             AND CASE WHEN p.period='本期' THEN {{CURRENT_END}} ELSE {{LAST_YEAR_END}} END
    WHERE o.u_user IS NOT NULL AND o.is_test_user=0 AND o.original_amount>=39
      AND o.business_gmv_attribution IN ('商业化','电销')
    GROUP BY r.period,r.channel,r.user_id,o.order_id,
             CASE WHEN o.original_amount>=498 AND o.original_amount<499 THEN '498'
                  WHEN o.business_good_kind_name_level_1='组合品' THEN '组合品' ELSE '其他商品' END
),
conversion_orders AS (
    SELECT period,channel,user_id,order_id,flow_product,revenue FROM conversion_order_rows
),
channel_users AS (
    SELECT r.period,r.channel,r.user_id,r.source_orders,r.source_amount,r.user_layer,
           COALESCE(a.stage,'未知学段') stage,CASE WHEN a.user_id IS NULL THEN 0 ELSE 1 END is_active
    FROM reservoir_users r LEFT JOIN active_audience a ON r.period=a.period AND r.user_id=a.user_id
    UNION ALL
    SELECT r.period,'私域整体',r.user_id,r.source_orders,r.source_amount,r.user_layer,
           COALESCE(a.stage,'未知学段'),CASE WHEN a.user_id IS NULL THEN 0 ELSE 1 END
    FROM reservoir_users r LEFT JOIN active_audience a ON r.period=a.period AND r.user_id=a.user_id
),
channel_conversion AS (
    SELECT period,channel,user_id,order_id,flow_product,revenue FROM conversion_orders
    UNION ALL SELECT period,'私域整体',user_id,order_id,flow_product,MAX(revenue)
    FROM conversion_orders GROUP BY period,user_id,order_id,flow_product
),
layer_expanded AS (SELECT period,channel,user_id,source_orders,source_amount,is_active,user_layer,stage FROM channel_users),
dimension_grid AS (
    SELECT p.period,c.channel,u.user_layer,s.stage FROM strategy_periods p CROSS JOIN channels c CROSS JOIN user_layer_values u CROSS JOIN stage_values s
),
summary_actual AS (
    SELECT d.period,d.channel,d.user_layer,d.stage,COUNT(DISTINCT d.user_id) source_users,SUM(d.source_orders) source_orders,SUM(d.source_amount) source_amount,
           COUNT(DISTINCT CASE WHEN d.is_active=1 THEN d.user_id END) active_source_users,COUNT(DISTINCT CASE WHEN d.is_active=0 THEN d.user_id END) inactive_source_users,
           COUNT(DISTINCT c.user_id) converted_users,COUNT(DISTINCT c.order_id) converted_orders,SUM(COALESCE(c.revenue,0)) converted_revenue,
           COUNT(DISTINCT CASE WHEN d.is_active=1 AND c.user_id IS NOT NULL THEN d.user_id END) active_converted_users,
           COUNT(DISTINCT CASE WHEN d.is_active=0 AND c.user_id IS NOT NULL THEN d.user_id END) inactive_converted_users
    FROM layer_expanded d LEFT JOIN channel_conversion c
      ON d.period=c.period AND d.channel=c.channel AND d.user_id=c.user_id
    GROUP BY d.period,d.channel,d.user_layer,d.stage
),
summary AS (
    SELECT g.period,g.channel,'用户层级×学段' dimension_type,CONCAT(g.user_layer,'×',g.stage) dimension_value,
           COALESCE(a.source_users,0) source_users,COALESCE(a.source_orders,0) source_orders,COALESCE(a.source_amount,0) source_amount,
           COALESCE(a.active_source_users,0) active_source_users,COALESCE(a.inactive_source_users,0) inactive_source_users,
           COALESCE(a.converted_users,0) converted_users,COALESCE(a.converted_orders,0) converted_orders,COALESCE(a.converted_revenue,0) converted_revenue,
           COALESCE(a.active_converted_users,0) active_converted_users,COALESCE(a.inactive_converted_users,0) inactive_converted_users
    FROM dimension_grid g LEFT JOIN summary_actual a ON g.period=a.period AND g.channel=a.channel AND g.user_layer=a.user_layer AND g.stage=a.stage
),
flow_grid AS (
    SELECT p.period,c.channel,u.user_layer,s.stage,x.product FROM strategy_periods p CROSS JOIN channels c CROSS JOIN user_layer_values u CROSS JOIN stage_values s CROSS JOIN products x
),
flow_actual AS (
    SELECT d.period,d.channel,d.user_layer,d.stage,c.flow_product product,SUM(c.revenue) value
    FROM layer_expanded d JOIN channel_conversion c
      ON d.period=c.period AND d.channel=c.channel AND d.user_id=c.user_id
    GROUP BY d.period,d.channel,d.user_layer,d.stage,c.flow_product
),
flow_summary AS (
    SELECT g.period,g.channel,'用户层级×学段×商品' dimension_type,CONCAT(g.user_layer,'×',g.stage,'×',g.product) dimension_value,COALESCE(a.value,0) value
    FROM flow_grid g LEFT JOIN flow_actual a ON g.period=a.period AND g.channel=a.channel AND g.user_layer=a.user_layer AND g.stage=a.stage AND g.product=a.product
),
metrics AS (
    SELECT period,channel,dimension_type,dimension_value,'蓄水来源用户数' metric,CAST(source_users AS DOUBLE) value FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'蓄水订单量',CAST(source_orders AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'蓄水金额',source_amount FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转大人数',CAST(converted_users AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转大订单量',CAST(converted_orders AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转大营收',converted_revenue FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转大率',converted_users/NULLIF(source_users,0) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'活跃蓄水用户数',CAST(active_source_users AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'非活跃蓄水用户数',CAST(inactive_source_users AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'活跃蓄水用户转大率',active_converted_users/NULLIF(active_source_users,0) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'非活跃蓄水用户转大率',inactive_converted_users/NULLIF(inactive_source_users,0) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转化商品流向',value FROM flow_summary
)
SELECT period,channel,dimension_type,dimension_value,metric,value,
       'v1;source_rule=sync_course_traffic_products;activity_window=conversion' source_version,
       CURRENT_TIMESTAMP data_updated_at,'reservoir.source_conversion_flow.v1' definition_id
FROM metrics
LIMIT 10000
