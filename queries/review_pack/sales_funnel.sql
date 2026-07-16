WITH periods AS (
 SELECT '本期' period,{{CURRENT_START}} start_day,{{CURRENT_END}} end_day
 UNION ALL SELECT '去年同期',{{LAST_YEAR_START}},{{LAST_YEAR_END}}
),
channels AS (SELECT '私域整体' channel UNION ALL SELECT 'APP' UNION ALL SELECT '销售'),
user_layer_values AS (SELECT '新增' user_layer UNION ALL SELECT '老未' UNION ALL SELECT '续费' UNION ALL SELECT '高净值汇总' UNION ALL SELECT '高净值－当年毕业' UNION ALL SELECT '高净值－历史大会员可续购' UNION ALL SELECT '高净值－历史大会员不可续购' UNION ALL SELECT '高净值－其他组合品' UNION ALL SELECT '未映射'),
stage_values AS (SELECT '1–3 年级' stage UNION ALL SELECT '4–6 年级' UNION ALL SELECT '初中' UNION ALL SELECT '高中' UNION ALL SELECT '未知学段'),
active_ranked AS (
 SELECT p.period,CAST(a.u_user AS VARCHAR) user_id,CASE WHEN a.business_gmv_attribution='商业化' THEN 'APP' WHEN a.business_gmv_attribution='电销' THEN '销售' END channel,
  CASE WHEN a.business_user_pay_status_statistics_month IN ('新增','新用户') THEN '新增' WHEN a.business_user_pay_status_statistics_month='老未' THEN '老未' WHEN a.business_user_pay_status_statistics_month IN ('续费用户','续费') THEN '续费' WHEN a.business_user_pay_status_statistics_month='高净值用户' THEN '高净值汇总' ELSE '未映射' END user_layer,
  CASE WHEN a.grade_name_month IN ('一年级','二年级','三年级') THEN '1–3 年级' WHEN a.grade_name_month IN ('四年级','五年级','六年级') THEN '4–6 年级' WHEN a.grade_name_month IN ('七年级','八年级','九年级','初一','初二','初三') THEN '初中' WHEN a.grade_name_month IN ('高一','高二','高三','十年级') THEN '高中' ELSE '未知学段' END stage,
  ROW_NUMBER() OVER(PARTITION BY p.period,CAST(a.u_user AS VARCHAR),CASE WHEN a.business_gmv_attribution='商业化' THEN 'APP' WHEN a.business_gmv_attribution='电销' THEN '销售' END ORDER BY a.day DESC) fact_rank
 FROM periods p JOIN aws.business_active_user_last_14_day a ON a.day BETWEEN p.start_day AND p.end_day WHERE a.u_user IS NOT NULL
),
active_users AS (
 SELECT period,channel,user_id,user_layer,stage FROM active_ranked WHERE fact_rank=1 AND channel IS NOT NULL
 UNION ALL SELECT period,'私域整体',user_id,user_layer,stage FROM (SELECT period,channel,user_id,user_layer,stage,ROW_NUMBER() OVER(PARTITION BY period,user_id ORDER BY CASE WHEN channel IS NULL THEN 1 ELSE 2 END,user_id) private_rank FROM active_ranked WHERE fact_rank=1) private_active_users WHERE private_rank=1
),
pool_users AS (
 SELECT p.period,CAST(d.active_u_user AS VARCHAR) user_id,
  MIN(IF(d.recieve_u_user IS NOT NULL, d.day, NULL)) AS first_receive_day
 FROM periods p JOIN aws.crm_active_data_pool_day d ON d.day BETWEEN p.start_day AND p.end_day
 WHERE d.active_u_user IS NOT NULL GROUP BY p.period,CAST(d.active_u_user AS VARCHAR)
 HAVING first_receive_day IS NOT NULL
),
phone_events AS (
 SELECT r.period,r.user_id,c.call_created_at,c.is_valid_connect
 FROM pool_users r JOIN periods p ON r.period=p.period JOIN tmp.niyiqiao_crm_clue_call_record c ON CAST(c.user_id AS VARCHAR)=r.user_id
 WHERE CAST(CONCAT(SUBSTR(c.call_created_at,1,4),SUBSTR(c.call_created_at,6,2),SUBSTR(c.call_created_at,9,2)) AS INT) BETWEEN r.first_receive_day AND p.end_day
),
phone_users AS (
 SELECT period,user_id,MIN(call_created_at) first_call_time,MIN(CASE WHEN is_valid_connect=1 THEN call_created_at END) first_connected_time,
  COUNT(*) call_count,SUM(CASE WHEN is_valid_connect=1 THEN 1 ELSE 0 END) connected_count
 FROM phone_events GROUP BY period,user_id
),
conversion_after_receive AS (
 SELECT r.period,r.user_id,COUNT(DISTINCT o.order_id) orders,SUM(o.sub_amount) revenue
 FROM pool_users r JOIN dws.topic_order_detail o ON CAST(o.u_user AS VARCHAR)=r.user_id AND o.paid_time_sk >= r.first_receive_day
 JOIN periods p ON r.period=p.period AND o.paid_time_sk<=p.end_day
 WHERE o.is_test_user=0 AND o.original_amount>=39 AND o.business_gmv_attribution IN ('商业化','电销') GROUP BY r.period,r.user_id
),
conversion_after_connected AS (
 SELECT p.period,p.user_id,COUNT(DISTINCT o.order_id) orders,SUM(o.sub_amount) revenue
 FROM phone_users p JOIN dws.topic_order_detail o ON CAST(o.u_user AS VARCHAR)=p.user_id AND o.paid_time > p.first_connected_time
 JOIN periods x ON p.period=x.period AND o.paid_time_sk<=x.end_day WHERE p.first_connected_time IS NOT NULL AND o.is_test_user=0 AND o.original_amount>=39 AND o.business_gmv_attribution IN ('商业化','电销') GROUP BY p.period,p.user_id
),
conversion_after_unconnected AS (
 SELECT p.period,p.user_id,COUNT(DISTINCT o.order_id) orders,SUM(o.sub_amount) revenue
 FROM phone_users p JOIN dws.topic_order_detail o ON CAST(o.u_user AS VARCHAR)=p.user_id AND o.paid_time > p.first_call_time
 JOIN periods x ON p.period=x.period AND o.paid_time_sk<=x.end_day WHERE p.first_connected_time IS NULL AND o.is_test_user=0 AND o.original_amount>=39 AND o.business_gmv_attribution IN ('商业化','电销') GROUP BY p.period,p.user_id
),
funnel_users AS (
 SELECT a.period,a.channel,a.user_id,a.user_layer,a.stage,r.first_receive_day,p.first_call_time,p.first_connected_time,
  c.user_id converted_user,c.revenue,cc.user_id connected_converted_user,cc.revenue connected_revenue,cu.user_id unconnected_converted_user,cu.revenue unconnected_revenue
 FROM active_users a LEFT JOIN pool_users r ON a.period=r.period AND a.user_id=r.user_id
 LEFT JOIN phone_users p ON r.period=p.period AND r.user_id=p.user_id
 LEFT JOIN conversion_after_receive c ON r.period=c.period AND r.user_id=c.user_id
 LEFT JOIN conversion_after_connected cc ON p.period=cc.period AND p.user_id=cc.user_id
 LEFT JOIN conversion_after_unconnected cu ON p.period=cu.period AND p.user_id=cu.user_id
),
dimension_grid AS (
 SELECT p.period,c.channel,u.user_layer,s.stage FROM periods p CROSS JOIN channels c CROSS JOIN user_layer_values u CROSS JOIN stage_values s
),
summary_actual AS (
 SELECT period,channel,user_layer,stage,COUNT(DISTINCT user_id) active_users,COUNT(DISTINCT CASE WHEN first_receive_day IS NOT NULL THEN user_id END) received_users,
 COUNT(DISTINCT CASE WHEN first_call_time IS NOT NULL THEN user_id END) called_users,COUNT(DISTINCT CASE WHEN first_connected_time IS NOT NULL THEN user_id END) connected_users,
 COUNT(DISTINCT CASE WHEN first_call_time IS NOT NULL AND first_connected_time IS NULL THEN user_id END) unconnected_users,
 COUNT(DISTINCT converted_user) converted_users,SUM(COALESCE(revenue,0)) revenue,COUNT(DISTINCT connected_converted_user) connected_converted_users,SUM(COALESCE(connected_revenue,0)) connected_revenue,
 COUNT(DISTINCT unconnected_converted_user) unconnected_converted_users,SUM(COALESCE(unconnected_revenue,0)) unconnected_revenue
 FROM funnel_users GROUP BY period,channel,user_layer,stage
),
summary AS (
 SELECT g.period,g.channel,'用户层级×学段' dimension_type,CONCAT(g.user_layer,'×',g.stage) dimension_value,
 COALESCE(a.active_users,0) active_users,COALESCE(a.received_users,0) received_users,COALESCE(a.called_users,0) called_users,COALESCE(a.connected_users,0) connected_users,COALESCE(a.unconnected_users,0) unconnected_users,
 COALESCE(a.converted_users,0) converted_users,COALESCE(a.revenue,0) revenue,COALESCE(a.connected_converted_users,0) connected_converted_users,COALESCE(a.connected_revenue,0) connected_revenue,COALESCE(a.unconnected_converted_users,0) unconnected_converted_users,COALESCE(a.unconnected_revenue,0) unconnected_revenue
 FROM dimension_grid g LEFT JOIN summary_actual a ON g.period=a.period AND g.channel=a.channel AND g.user_layer=a.user_layer AND g.stage=a.stage
),
numeric_metrics AS (
 SELECT period,channel,dimension_type,dimension_value,'线索领取人数' metric,CAST(received_users AS DOUBLE) value FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'线索领取率',received_users/NULLIF(active_users,0) FROM summary
 UNION ALL SELECT period,channel,dimension_type,dimension_value,'电话拨打人数',CAST(called_users AS DOUBLE) FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'有效接通人数',CAST(connected_users AS DOUBLE) FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'有效接通率',connected_users/NULLIF(called_users,0) FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'未有效接通人数',CAST(unconnected_users AS DOUBLE) FROM summary
 UNION ALL SELECT period,channel,dimension_type,dimension_value,'转化人数',CAST(converted_users AS DOUBLE) FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'转化率',converted_users/NULLIF(received_users,0) FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'转化营收',revenue FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'客单价',revenue/NULLIF(converted_users,0) FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'ARPU',revenue/NULLIF(received_users,0) FROM summary
 UNION ALL SELECT period,channel,dimension_type,dimension_value,'有效接通后转化人数',CAST(connected_converted_users AS DOUBLE) FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'有效接通后转化率',connected_converted_users/NULLIF(connected_users,0) FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'有效接通后营收',connected_revenue FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'有效接通后客单价',connected_revenue/NULLIF(connected_converted_users,0) FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'有效接通后ARPU',connected_revenue/NULLIF(connected_users,0) FROM summary
 UNION ALL SELECT period,channel,dimension_type,dimension_value,'未有效接通后转化人数',CAST(unconnected_converted_users AS DOUBLE) FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'未有效接通后转化率',unconnected_converted_users/NULLIF(unconnected_users,0) FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'未有效接通后营收',unconnected_revenue FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'未有效接通后客单价',unconnected_revenue/NULLIF(unconnected_converted_users,0) FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'未有效接通后ARPU',unconnected_revenue/NULLIF(unconnected_users,0) FROM summary
),
wechat_metrics AS (SELECT period,channel,dimension_type,dimension_value,'企微添加人数' metric,'数据源未接入' value,'data_source_missing' source_version FROM summary UNION ALL SELECT period,channel,dimension_type,dimension_value,'企微添加率','数据源未接入','data_source_missing' FROM summary),
metrics AS (SELECT period,channel,dimension_type,dimension_value,metric,CAST(value AS VARCHAR) value,'v2;event_ordered_nested_funnel' source_version FROM numeric_metrics UNION ALL SELECT period,channel,dimension_type,dimension_value,metric,value,source_version FROM wechat_metrics)
SELECT period,channel,dimension_type,dimension_value,metric,value,source_version,CURRENT_TIMESTAMP data_updated_at,CASE WHEN source_version='data_source_missing' THEN 'sales_funnel.wechat.data_source_missing.v1' ELSE 'sales_funnel.nested_event_ordered.v2' END definition_id FROM metrics LIMIT 10000
