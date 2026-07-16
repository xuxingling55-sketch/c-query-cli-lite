WITH periods AS (SELECT '本期' period,{{CURRENT_START}} start_day,{{CURRENT_END}} end_day UNION ALL SELECT '去年同期',{{LAST_YEAR_START}},{{LAST_YEAR_END}}),
channels AS (SELECT '私域整体' channel UNION ALL SELECT 'APP' UNION ALL SELECT '销售'),
user_layer_values AS (SELECT '新增' user_layer UNION ALL SELECT '老未' UNION ALL SELECT '续费' UNION ALL SELECT '高净值汇总' UNION ALL SELECT '高净值－当年毕业' UNION ALL SELECT '高净值－历史大会员可续购' UNION ALL SELECT '高净值－历史大会员不可续购' UNION ALL SELECT '高净值－其他组合品' UNION ALL SELECT '未映射'),
stage_values AS (SELECT '1–3 年级' stage UNION ALL SELECT '4–6 年级' UNION ALL SELECT '初中' UNION ALL SELECT '高中' UNION ALL SELECT '未知学段'),
products AS (SELECT '全部' product UNION ALL SELECT '组合品' UNION ALL SELECT '零售品' UNION ALL SELECT '家庭包' UNION ALL SELECT '从小学系列' UNION ALL SELECT '198' UNION ALL SELECT '498' UNION ALL SELECT '千元及以上'),
source_ranked AS (
 SELECT p.period,CAST(m.u_user AS VARCHAR) user_id,CASE WHEN a.business_gmv_attribution='商业化' THEN 'APP' WHEN a.business_gmv_attribution='电销' THEN '销售' END channel,
 CASE WHEN a.grade_name_month IN ('一年级','二年级','三年级') THEN '1–3 年级' WHEN a.grade_name_month IN ('四年级','五年级','六年级') THEN '4–6 年级' WHEN a.grade_name_month IN ('七年级','八年级','九年级','初一','初二','初三') THEN '初中' WHEN a.grade_name_month IN ('高一','高二','高三','十年级') THEN '高中' ELSE '未知学段' END stage,
 CASE WHEN m.user_strategy_tag_month REGEXP CONCAT('付费组合品用户-',SUBSTR(CAST(p.start_day AS VARCHAR),1,4),'年初中毕业') THEN '高净值－当年毕业' WHEN m.user_strategy_tag_month REGEXP '历史大会员用户_可续购' THEN '高净值－历史大会员可续购' WHEN m.user_strategy_tag_month REGEXP '历史大会员用户_不可续购' THEN '高净值－历史大会员不可续购' ELSE '高净值－其他组合品' END detail_layer,
 ROW_NUMBER() OVER(PARTITION BY p.period,CAST(m.u_user AS VARCHAR),CASE WHEN a.business_gmv_attribution='商业化' THEN 'APP' WHEN a.business_gmv_attribution='电销' THEN '销售' END ORDER BY a.day DESC,CASE WHEN m.user_strategy_tag_month REGEXP '历史大会员用户_可续购' THEN 1 WHEN m.user_strategy_tag_month REGEXP '历史大会员用户_不可续购' THEN 2 ELSE 3 END,CAST(m.u_user AS VARCHAR)) fact_rank
 FROM periods p JOIN dws.topic_user_active_detail_month m ON m.`month`=CAST(SUBSTR(CAST(p.start_day AS VARCHAR),1,6) AS INT)
 LEFT JOIN aws.business_active_user_last_14_day a ON a.u_user=m.u_user AND a.day=p.start_day
 WHERE m.u_user IS NOT NULL AND m.user_strategy_tag_month REGEXP '历史大会员用户|付费组合品用户|付费加购品用户'
),
source_channel_users AS (SELECT period,channel,user_id,stage,detail_layer FROM source_ranked WHERE fact_rank=1 AND channel IS NOT NULL),
source_private_users AS (SELECT period,'私域整体' channel,user_id,stage,detail_layer FROM (SELECT period,user_id,stage,detail_layer,ROW_NUMBER() OVER(PARTITION BY period,user_id ORDER BY CASE WHEN stage<>'未知学段' THEN 1 ELSE 2 END,user_id) private_rank FROM source_ranked WHERE fact_rank=1) x WHERE private_rank=1),
source_users AS (
 SELECT period,channel,user_id,stage,'高净值汇总' user_layer FROM source_channel_users UNION ALL SELECT period,channel,user_id,stage,detail_layer FROM source_channel_users
 UNION ALL SELECT period,channel,user_id,stage,'高净值汇总' FROM source_private_users UNION ALL SELECT period,channel,user_id,stage,detail_layer FROM source_private_users
),
active_users AS (
 SELECT DISTINCT s.period,s.channel,s.user_id FROM source_users s JOIN periods p ON s.period=p.period
 JOIN aws.business_active_user_last_14_day a ON CAST(a.u_user AS VARCHAR)=s.user_id AND a.day BETWEEN p.start_day AND p.end_day
),
order_line_rows AS (
 SELECT p.period,CASE WHEN o.business_gmv_attribution='商业化' THEN 'APP' ELSE '销售' END channel,CAST(o.u_user AS VARCHAR) user_id,o.order_id,o.sku_group_good_id,
 o.business_good_kind_name_level_1,o.business_good_kind_name_level_3,o.good_name,o.good_kind_name_level_3,o.good_stage_subject_cnt,o.good_stage_subject,o.original_amount,o.sub_amount revenue
 FROM periods p JOIN dws.topic_order_detail o ON o.paid_time_sk BETWEEN p.start_day AND p.end_day
 WHERE o.u_user IS NOT NULL AND o.is_test_user=0 AND o.original_amount>=39 AND o.business_gmv_attribution IN ('商业化','电销')
),
product_order_rows AS (
 SELECT period,channel,user_id,order_id,sku_group_good_id,revenue,'全部' product FROM order_line_rows
 UNION ALL SELECT period,channel,user_id,order_id,sku_group_good_id,revenue,'组合品' FROM order_line_rows WHERE business_good_kind_name_level_1='组合品'
 UNION ALL SELECT period,channel,user_id,order_id,sku_group_good_id,revenue,'零售品' FROM order_line_rows WHERE business_good_kind_name_level_1='零售商品'
 UNION ALL SELECT period,channel,user_id,order_id,sku_group_good_id,revenue,'家庭包' FROM order_line_rows WHERE business_good_kind_name_level_3='小初高品'
 UNION ALL SELECT period,channel,user_id,order_id,sku_group_good_id,revenue,'从小学系列' FROM order_line_rows WHERE business_good_kind_name_level_3='小学品加拓展' OR (good_name LIKE '从小学%' AND good_name NOT LIKE '%系列%') OR (good_kind_name_level_3='拓展课' AND good_stage_subject_cnt=1 AND (good_stage_subject REGEXP '1-2-specialCourse' OR good_stage_subject REGEXP '1-6-specialCourse' OR good_stage_subject REGEXP '1-7-specialCourse'))
 UNION ALL SELECT period,channel,user_id,order_id,sku_group_good_id,revenue,'198' FROM order_line_rows WHERE original_amount>=198 AND original_amount<199
 UNION ALL SELECT period,channel,user_id,order_id,sku_group_good_id,revenue,'498' FROM order_line_rows WHERE original_amount>=498 AND original_amount<499
 UNION ALL SELECT period,channel,user_id,order_id,sku_group_good_id,revenue,'千元及以上' FROM order_line_rows WHERE original_amount>=1000
 UNION ALL SELECT period,'私域整体',user_id,order_id,sku_group_good_id,revenue,'全部' FROM order_line_rows
 UNION ALL SELECT period,'私域整体',user_id,order_id,sku_group_good_id,revenue,'组合品' FROM order_line_rows WHERE business_good_kind_name_level_1='组合品'
 UNION ALL SELECT period,'私域整体',user_id,order_id,sku_group_good_id,revenue,'零售品' FROM order_line_rows WHERE business_good_kind_name_level_1='零售商品'
 UNION ALL SELECT period,'私域整体',user_id,order_id,sku_group_good_id,revenue,'家庭包' FROM order_line_rows WHERE business_good_kind_name_level_3='小初高品'
 UNION ALL SELECT period,'私域整体',user_id,order_id,sku_group_good_id,revenue,'从小学系列' FROM order_line_rows WHERE business_good_kind_name_level_3='小学品加拓展' OR (good_name LIKE '从小学%' AND good_name NOT LIKE '%系列%')
 UNION ALL SELECT period,'私域整体',user_id,order_id,sku_group_good_id,revenue,'198' FROM order_line_rows WHERE original_amount>=198 AND original_amount<199
 UNION ALL SELECT period,'私域整体',user_id,order_id,sku_group_good_id,revenue,'498' FROM order_line_rows WHERE original_amount>=498 AND original_amount<499
 UNION ALL SELECT period,'私域整体',user_id,order_id,sku_group_good_id,revenue,'千元及以上' FROM order_line_rows WHERE original_amount>=1000
),
dimension_grid AS (SELECT p.period,c.channel,u.user_layer,s.stage,x.product FROM periods p CROSS JOIN channels c CROSS JOIN user_layer_values u CROSS JOIN stage_values s CROSS JOIN products x),
summary_actual AS (
 SELECT s.period,s.channel,s.user_layer,s.stage,p.product,COUNT(DISTINCT s.user_id) source_users,COUNT(DISTINCT a.user_id) active_users,COUNT(DISTINCT o.user_id) pay_users,COUNT(DISTINCT o.order_id) orders,SUM(COALESCE(o.revenue,0)) revenue
 FROM source_users s CROSS JOIN products p LEFT JOIN active_users a ON s.period=a.period AND s.channel=a.channel AND s.user_id=a.user_id
 LEFT JOIN product_order_rows o ON s.period=o.period AND s.channel=o.channel AND s.user_id=o.user_id AND p.product=o.product
 GROUP BY s.period,s.channel,s.user_layer,s.stage,p.product
),
summary AS (
 SELECT g.period,g.channel,g.user_layer,g.stage,g.product,COALESCE(a.source_users,0) source_users,COALESCE(a.active_users,0) active_users,COALESCE(a.pay_users,0) pay_users,COALESCE(a.orders,0) orders,COALESCE(a.revenue,0) revenue
 FROM dimension_grid g LEFT JOIN summary_actual a ON g.period=a.period AND g.channel=a.channel AND g.user_layer=a.user_layer AND g.stage=a.stage AND g.product=a.product
),
private_revenue AS (SELECT p.period,SUM(o.sub_amount) revenue FROM periods p JOIN dws.topic_order_detail o ON o.paid_time_sk BETWEEN p.start_day AND p.end_day WHERE o.u_user IS NOT NULL AND o.is_test_user=0 AND o.original_amount>=39 AND o.business_gmv_attribution IN ('商业化','电销') GROUP BY p.period),
base_metrics AS (
 SELECT period,channel,user_layer,stage,product,'来源用户数' metric,CAST(source_users AS DOUBLE) value FROM summary UNION ALL SELECT period,channel,user_layer,stage,product,'活跃人数',CAST(active_users AS DOUBLE) FROM summary UNION ALL SELECT period,channel,user_layer,stage,product,'付费人数',CAST(pay_users AS DOUBLE) FROM summary UNION ALL SELECT period,channel,user_layer,stage,product,'订单量',CAST(orders AS DOUBLE) FROM summary UNION ALL SELECT period,channel,user_layer,stage,product,'营收',revenue FROM summary UNION ALL SELECT period,channel,user_layer,stage,product,'付费转化率',pay_users/NULLIF(active_users,0) FROM summary UNION ALL SELECT period,channel,user_layer,stage,product,'客单价',revenue/NULLIF(pay_users,0) FROM summary UNION ALL SELECT period,channel,user_layer,stage,product,'ARPU',revenue/NULLIF(active_users,0) FROM summary
 UNION ALL SELECT s.period,s.channel,s.user_layer,s.stage,s.product,'高净值营收占私域营收比例',s.revenue/NULLIF(p.revenue,0) FROM summary s JOIN private_revenue p ON s.period=p.period
),
combo_rows AS (
 SELECT period,channel,user_layer,stage,product,'组合品付费人数' metric,CAST(pay_users AS DOUBLE) value FROM summary WHERE product='组合品'
 UNION ALL SELECT period,channel,user_layer,stage,product,'组合品订单量',CAST(orders AS DOUBLE) FROM summary WHERE product='组合品'
 UNION ALL SELECT period,channel,user_layer,stage,product,'组合品营收',revenue FROM summary WHERE product='组合品'
 UNION ALL SELECT period,channel,user_layer,stage,product,'组合品转化率',pay_users/NULLIF(active_users,0) FROM summary WHERE product='组合品'
),
metrics AS (SELECT period,channel,user_layer,stage,product,metric,value FROM base_metrics UNION ALL SELECT period,channel,user_layer,stage,product,metric,value FROM combo_rows)
SELECT period,channel,dimension_type,dimension_value,metric,value,'v3;monthly_source;independent_slices' source_version,CURRENT_TIMESTAMP data_updated_at,'high_value.monthly_pool_slices.v3' definition_id FROM (
 SELECT period,channel,'高净值层级' dimension_type,user_layer dimension_value,metric,SUM(value) value FROM metrics WHERE product='全部' GROUP BY period,channel,user_layer,metric
 UNION ALL
 SELECT period,channel,'学段' dimension_type,stage dimension_value,metric,SUM(value) value FROM metrics WHERE user_layer='高净值汇总' AND product='全部' GROUP BY period,channel,stage,metric
 UNION ALL
 SELECT period,channel,'商品' dimension_type,product dimension_value,metric,SUM(value) value FROM metrics WHERE user_layer='高净值汇总' GROUP BY period,channel,product,metric
) independent_slices LIMIT 10000
