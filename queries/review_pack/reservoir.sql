WITH strategy_periods AS (
    SELECT '本期' AS period,
           {{RESERVOIR_SOURCE_START}} AS source_start, {{RESERVOIR_SOURCE_END}} AS source_end
    UNION ALL
    SELECT '去年同期',
           CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST({{RESERVOIR_SOURCE_START}} AS VARCHAR), '%Y%m%d'), INTERVAL 1 YEAR), '%Y%m%d') AS INT),
           CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST({{RESERVOIR_SOURCE_END}} AS VARCHAR), '%Y%m%d'), INTERVAL 1 YEAR), '%Y%m%d') AS INT)
),
reservoir_source_rows AS (
    SELECT p.period,
           CASE WHEN o.business_gmv_attribution='商业化' THEN 'APP' ELSE '销售' END AS channel,
           CAST(o.u_user AS VARCHAR) AS user_id, o.order_id, MIN(o.paid_time) AS first_source_time,
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
reservoir_users AS (
    SELECT period,channel,user_id,MIN(first_source_time) first_source_time,
           COUNT(DISTINCT order_id) source_orders,SUM(source_amount) source_amount,MAX(user_layer) user_layer
    FROM reservoir_source_rows GROUP BY period,channel,user_id
),
active_audience AS (
    SELECT p.period,CAST(a.u_user AS VARCHAR) user_id,
           CASE WHEN MAX(CASE WHEN a.grade_name_month IN ('一年级','二年级','三年级') THEN 1 ELSE 0 END)=1 THEN '1–3 年级'
                WHEN MAX(CASE WHEN a.grade_name_month IN ('四年级','五年级','六年级') THEN 1 ELSE 0 END)=1 THEN '4–6 年级'
                WHEN MAX(CASE WHEN a.grade_name_month IN ('七年级','八年级','九年级','初一','初二','初三') THEN 1 ELSE 0 END)=1 THEN '初中'
                WHEN MAX(CASE WHEN a.grade_name_month IN ('高一','高二','高三','十年级') THEN 1 ELSE 0 END)=1 THEN '高中'
                ELSE '未知学段' END stage
    FROM strategy_periods p JOIN aws.business_active_user_last_14_day a
      ON a.day BETWEEN CASE WHEN p.period='本期' THEN {{CURRENT_START}} ELSE {{LAST_YEAR_START}} END
                   AND CASE WHEN p.period='本期' THEN {{CURRENT_END}} ELSE {{LAST_YEAR_END}} END
    WHERE a.u_user IS NOT NULL GROUP BY p.period,CAST(a.u_user AS VARCHAR)
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
    SELECT r.period,'私域整体',r.user_id,SUM(r.source_orders),SUM(r.source_amount),MAX(r.user_layer),
           COALESCE(MAX(a.stage),'未知学段'),MAX(CASE WHEN a.user_id IS NULL THEN 0 ELSE 1 END)
    FROM reservoir_users r LEFT JOIN active_audience a ON r.period=a.period AND r.user_id=a.user_id
    GROUP BY r.period,r.user_id
),
channel_conversion AS (
    SELECT period,channel,user_id,order_id,flow_product,revenue FROM conversion_orders
    UNION ALL SELECT period,'私域整体',user_id,order_id,flow_product,MAX(revenue)
    FROM conversion_orders GROUP BY period,user_id,order_id,flow_product
),
dimension_users AS (
    SELECT period,channel,user_id,source_orders,source_amount,is_active,'整体' dimension_type,'全部' dimension_value FROM channel_users
    UNION ALL SELECT period,channel,user_id,source_orders,source_amount,is_active,'用户层级',user_layer FROM channel_users
    UNION ALL SELECT period,channel,user_id,source_orders,source_amount,is_active,'学段',stage FROM channel_users
),
source_summary AS (
    SELECT period,channel,dimension_type,dimension_value,COUNT(DISTINCT user_id) source_users,
           SUM(source_orders) source_orders,SUM(source_amount) source_amount,
           COUNT(DISTINCT CASE WHEN is_active=1 THEN user_id END) active_source_users,
           COUNT(DISTINCT CASE WHEN is_active=0 THEN user_id END) inactive_source_users
    FROM dimension_users GROUP BY period,channel,dimension_type,dimension_value
),
conversion_summary AS (
    SELECT d.period,d.channel,d.dimension_type,d.dimension_value,
           COUNT(DISTINCT c.user_id) converted_users,COUNT(DISTINCT c.order_id) converted_orders,SUM(COALESCE(c.revenue,0)) converted_revenue,
           COUNT(DISTINCT CASE WHEN d.is_active=1 AND c.user_id IS NOT NULL THEN d.user_id END) active_converted_users,
           COUNT(DISTINCT CASE WHEN d.is_active=0 AND c.user_id IS NOT NULL THEN d.user_id END) inactive_converted_users
    FROM dimension_users d LEFT JOIN channel_conversion c
      ON d.period=c.period AND d.channel=c.channel AND d.user_id=c.user_id
    GROUP BY d.period,d.channel,d.dimension_type,d.dimension_value
),
summary AS (
    SELECT s.period,s.channel,s.dimension_type,s.dimension_value,s.source_users,s.source_orders,s.source_amount,
           s.active_source_users,s.inactive_source_users,
           COALESCE(c.converted_users,0) converted_users,COALESCE(c.converted_orders,0) converted_orders,
           COALESCE(c.converted_revenue,0) converted_revenue,COALESCE(c.active_converted_users,0) active_converted_users,
           COALESCE(c.inactive_converted_users,0) inactive_converted_users
    FROM source_summary s LEFT JOIN conversion_summary c
      ON s.period=c.period AND s.channel=c.channel AND s.dimension_type=c.dimension_type AND s.dimension_value=c.dimension_value
),
flow_summary AS (
    SELECT d.period,d.channel,d.dimension_type,CONCAT(d.dimension_value,'×',c.flow_product) dimension_value,
           SUM(c.revenue) value
    FROM dimension_users d JOIN channel_conversion c
      ON d.period=c.period AND d.channel=c.channel AND d.user_id=c.user_id
    GROUP BY d.period,d.channel,d.dimension_type,CONCAT(d.dimension_value,'×',c.flow_product)
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
