-- =====================================================
-- 近14天商业化活跃用户日表 aws.business_active_user_last_14_day
-- =====================================================
--
-- 【表粒度】
--   一用户一天多行（team_ids、team_names、business_gmv_attribution是订单粒度的标签，一个用户一天可能有多条记录；分区字段：day；近 14 天窗口内商业/付费等标签）
--   补充：一行 = 一个 user_sk 在一个统计日 day 下、按一组营收归属/团队归属组合展开的一条用户日记录；
--         不是简单的"一个用户一天仅一行"（来源 biMetadata）
--
-- 【业务定位】
--   - 与 dws.topic_user_active_detail_day 按 u_user + day 关联；含 *_day 后缀分层字段（与活跃日表同名字段语义不完全等同，见 table-relations）；与 dw.dim_user 可按 u_user 对齐
--   - 用户只包括c端活跃用户，不包括b端活跃用户
--   补充：该表沉淀 C 端活跃用户在统计日的商业化分层、当日及首购/复购营收、月/年首次活跃属性、
--         团队归属以及新价格方案拆分指标，是 business_active_channel_day/month 等经营宽表的用户层主源（来源 biMetadata）
--
-- 【统计口径】
--   表内营收/订单汇总列见字段 COMMENT
--
--   补充（来源 biMetadata）：
--   - 虽然表名含 last_14_day，但单条记录仍是**统计日当天**的用户经营快照；主程序只是会对最近 14 天补跑刷新
--   - 月属性取用户当月首次活跃日口径；年属性取当年首次活跃口径
--   - 订单指标按统计日 paid_time_sk = day 的轻课营收订单聚合；首购/复购通过历史 dw.fact_order 排序识别
--
-- 【常用关联】
--   - u_user、day 对齐 dws.topic_user_active_detail_day
--
--   补充（来源 biMetadata）：
--   | 场景 | Join Key | 说明 |
--   |------|----------|------|
--   | 渠道经营表 | u_user / user_sk + day | 作为渠道日/月表的用户层来源 |
--   | 用户快照   | user_sk + day          | 可回连 dws.topic_user_info 查看更多画像 |
--   | 团队归属   | team_ids + team_names  | 同一用户同日可能按不同团队组合拆成多行 |
--
-- 【常用筛选条件】
--   场景条件：
--   - day、分层字段按归因/寒假等需求
--
--   ★必加条件（来源 biMetadata）：
--   - day = yyyymmdd                       -- 必须带分区
--   - 若按用户去重统计，请先确认是否需要忽略 business_gmv_attribution、team_ids、team_names 等拆行维度
--
-- 【注意事项】
--   - JOIN 字段与活跃日表差异见 `knowledge/table-relations.md`
--   - 更新频率 T+1
--   - 知识库约定：取数与分析仅使用 business_user_pay_status_*；
--
--   补充常见误用（来源 biMetadata）：
--   - 把表名理解成 14 日滚动指标表：行级仍是"单日用户经营记录"，只是作业会回刷近 14 天
--   - 把 pay_user_sk 当人数指标直接求和：该列本质是"付费则回填当前 user_sk"，
--     人数应 count(distinct pay_user_sk)
--   - 使用已废弃电销字段做新分析：is_tele_belong_day/month、is_tele_receive_month 在代码中已写 NULL
--
-- 【数据来源】（来源 biMetadata）
--   - 调度实现：com.onion.etl.aws.business.BusinessActiveUserLast14Day
--   - 活跃主链：dws.topic_user_active_detail_day/month/week、dw.middle_dim_user_year_last_14
--   - 订单主链：dws.topic_order_detail、dw.fact_order_detail、dw.fact_order、dw.fact_order_crm
--
-- 【周期属性口径】（来源 biMetadata）
--   - *_month 字段取用户当月首次活跃日口径
--   - *_year  字段取用户当年首次活跃口径
--   - *_day   字段取统计日当天口径


CREATE TABLE
  `aws`.`business_active_user_last_14_day` (
    `user_sk` int COMMENT '数仓用户主键 |上游：dws.topic_user_active_detail_day 当日活跃用户主链 |加工：无',
    `grade_name_month` string COMMENT '当月首次活跃时年级 |上游：dws.topic_user_active_detail_month 首次活跃口径 |加工：非月末快照',
    `stage_name_month` string COMMENT '当月首次活跃时学段 |上游：同上 |加工：非月末快照',
    `grade_stage_name_month` string COMMENT '当月首次活跃时年级段 |上游：同上 |加工：CASE 映射',
    `user_pay_status_statistics_month` string COMMENT '本月第一次活跃当天的统计维度：新增、老未、付费的标签 |上游：aws.business_active_user_last_14_day.user_pay_status_statistics_month；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `user_pay_status_business_month` string COMMENT '本月第一次活跃当天的策略维度：新用户、老用户、付费用户 |上游：aws.business_active_user_last_14_day.user_pay_status_business_month；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `business_user_pay_status_statistics_month` string COMMENT '当月首次活跃时商业化统计分层 |上游：月口径首活标签 |加工：无',
    `month_first_day` int COMMENT '月首标记 |上游：月口径首活明细中固定写 1 |加工：字段名保留历史写法',
    `month_days` int COMMENT '统计日所在月天数 |上游：UDF get_days_in_month(day) |加工：无',
    `business_gmv_attribution` string COMMENT '营收归属 |上游：订单明细聚合维度 |加工：同一用户同日可多值',
    `amount` double COMMENT '当日营收 |上游：统计日轻课营收订单按用户+归属+团队汇总 |加工：无',
    `pay_user_sk` int COMMENT '当日付费用户标记 |上游：amount > 0 时回填 user_sk |加工：人数请 count(distinct pay_user_sk)',
    `normal_price_amount` double COMMENT '当日正价营收 |上游：original_amount >= 39 的订单金额之和 |加工：无',
    `normal_price_user_sk` int COMMENT '当日正价付费用户标记 |上游：normal_price_amount > 0 时回填 user_sk |加工：同上',
    `normal_price_big_vip_amount` double COMMENT '正价营收-大会员 |上游：aws.business_active_user_last_14_day.normal_price_big_vip_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_big_vip_user_sk` int COMMENT '正价大会员付费用户 |上游：aws.business_active_user_last_14_day.normal_price_big_vip_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_big_vip_xugou_amount` double COMMENT '正价营收-大会员续购 |上游：aws.business_active_user_last_14_day.normal_price_big_vip_xugou_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_big_vip_xugou_user_sk` int COMMENT '正价大会员续购付费用户 |上游：aws.business_active_user_last_14_day.normal_price_big_vip_xugou_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_total_review_amount` double COMMENT '正价营收-总复习 |上游：aws.business_active_user_last_14_day.normal_price_total_review_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_total_review_user_sk` int COMMENT '正价总复习付费用户 |上游：aws.business_active_user_last_14_day.normal_price_total_review_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_vip_amount` double COMMENT '正价营收-同步课 |上游：aws.business_active_user_last_14_day.normal_price_vip_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_vip_user_sk` int COMMENT '正价同步课付费用户 |上游：aws.business_active_user_last_14_day.normal_price_vip_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_other_amount` double COMMENT '正价营收-其他商品 |上游：aws.business_active_user_last_14_day.normal_price_other_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_other_user_sk` int COMMENT '正价其他商品付费用户 |上游：aws.business_active_user_last_14_day.normal_price_other_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_order_cnt` int COMMENT '当日正价订单数 |上游：当日订单按 order_id 计数 |加工：无',
    `normal_price_big_vip_order_cnt` int COMMENT '正价大会员付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_big_vip_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_big_vip_xugou_order_cnt` int COMMENT '正价大会员续购付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_big_vip_xugou_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_vip_order_cnt` int COMMENT '正价同步课付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_vip_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_total_review_order_cnt` int COMMENT '正价总复习付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_total_review_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_other_order_cnt` int COMMENT '正价其他商品付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_other_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_first_purchase_amount` double COMMENT '当日正价首购营收 |上游：统计日订单与历史首购订单集合匹配 |加工：仅首购订单命中',
    `normal_price_first_purchase_user_sk` int COMMENT '正价首购付费用户 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_big_vip_amount` double COMMENT '正价首购营收-大会员 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_big_vip_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_big_vip_user_sk` int COMMENT '正价首购大会员付费用户 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_big_vip_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_big_vip_xugou_amount` double COMMENT '正价首购营收-大会员续购 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_big_vip_xugou_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_big_vip_xugou_user_sk` int COMMENT '正价首购大会员续购付费用户 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_big_vip_xugou_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_total_review_amount` double COMMENT '正价首购营收-总复习 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_total_review_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_total_review_user_sk` int COMMENT '正价首购总复习付费用户 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_total_review_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_vip_amount` double COMMENT '正价首购营收-同步课 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_vip_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_vip_user_sk` int COMMENT '正价首购同步课付费用户 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_vip_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_other_amount` double COMMENT '正价首购营收-其他商品 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_other_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_other_user_sk` int COMMENT '正价首购其他商品付费用户 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_other_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_order_cnt` int COMMENT '当日正价首购订单数 |上游：同上 |加工：无',
    `normal_price_first_purchase_big_vip_order_cnt` int COMMENT '正价首购大会员付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_big_vip_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_big_vip_xugou_order_cnt` int COMMENT '正价首购大会员续购付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_big_vip_xugou_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_vip_order_cnt` int COMMENT '正价首购同步课付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_vip_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_total_review_order_cnt` int COMMENT '正价首购总复习付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_total_review_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_other_order_cnt` int COMMENT '正价首购其他商品付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_other_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_repurchase_amount` double COMMENT '当日正价复购营收 |上游：统计日订单与历史复购订单集合匹配 |加工：仅复购订单命中',
    `normal_price_repurchase_user_sk` int COMMENT '正价复购付费用户 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_big_vip_amount` double COMMENT '正价复购营收-大会员 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_big_vip_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_big_vip_user_sk` int COMMENT '正价复购大会员付费用户 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_big_vip_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_big_vip_xugou_amount` double COMMENT '正价复购营收-大会员续购 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_big_vip_xugou_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_big_vip_xugou_user_sk` int COMMENT '正价复购大会员续购付费用户 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_big_vip_xugou_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_total_review_amount` double COMMENT '正价复购营收-总复习 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_total_review_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_total_review_user_sk` int COMMENT '正价复购总复习付费用户 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_total_review_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_vip_amount` double COMMENT '正价复购营收-同步课 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_vip_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_vip_user_sk` int COMMENT '正价复购同步课付费用户 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_vip_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_other_amount` double COMMENT '正价复购营收-其他商品 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_other_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_other_user_sk` int COMMENT '正价复购其他商品付费用户 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_other_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_order_cnt` int COMMENT '当日正价复购订单数 |上游：同上 |加工：无',
    `normal_price_repurchase_big_vip_order_cnt` int COMMENT '正价复购大会员付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_big_vip_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_big_vip_xugou_order_cnt` int COMMENT '正价复购大会员续购付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_big_vip_xugou_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_vip_order_cnt` int COMMENT '正价复购同步课付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_vip_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_total_review_order_cnt` int COMMENT '正价复购总复习付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_total_review_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_other_order_cnt` int COMMENT '正价复购其他商品付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_other_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `day_timestamp` timestamp COMMENT '统计日零点时间戳 |上游：from_unixtime(unix_timestamp(day,\'yyyyMMdd\')) |加工：固定到 00:00:00',
    `grade_name_year` string COMMENT '当年首次活跃时年级 |上游：dw.middle_dim_user_year_last_14 或当年首次月活记录 |加工：非年末快照',
    `stage_name_year` string COMMENT '当年首次活跃时学段 |上游：同上 |加工：无',
    `grade_stage_name_year` string COMMENT '本年第一次活跃年级段 |上游：aws.business_active_user_last_14_day.grade_stage_name_year；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `user_pay_status_statistics_year` string COMMENT '本年第一次活跃付费统计分层 |上游：aws.business_active_user_last_14_day.user_pay_status_statistics_year；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `user_pay_status_business_year` string COMMENT '本年第一次活跃付费业务分层 |上游：aws.business_active_user_last_14_day.user_pay_status_business_year；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `business_user_pay_status_statistics_year` string COMMENT '当年首次活跃时商业化统计分层 |上游：同上 |加工：无',
    `u_user` string COMMENT '业务用户 ID |上游：同上 |加工：无',
    `user_pay_status_statistics_day` string COMMENT '当天付费统计分层 |上游：当日活跃明细主链 |加工：无',
    `user_pay_status_business_day` string COMMENT '当天付费业务分层 |上游：当日活跃明细主链 |加工：无',
    `business_user_pay_status_statistics_day` string COMMENT '当天商业化付费分层 |上游：当日活跃明细主链 |加工：无',
    `business_user_pay_status_business_day` string COMMENT '当天商业化业务分层 |上游：当日活跃明细主链 |加工：无',
    `business_user_pay_status_business_month` string COMMENT '当月首次活跃时商业化业务分层 |上游：月口径首活标签 |加工：无',
    `business_user_pay_status_business_year` string COMMENT '本年第一次活跃时付费分层-业务维度-拆分付费 |上游：aws.business_active_user_last_14_day.business_user_pay_status_business_year；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `grade_name_day` string COMMENT '当天年级 |上游：当日活跃明细主链 |加工：无',
    `stage_name_day` string COMMENT '当天学段 |上游：当日活跃明细主链 |加工：无',
    `grade_stage_name_day` string COMMENT '当天年级段 |上游：基于当天年级 CASE 映射 |加工：一二=小初，三四=小中，五六=小高',
    `normal_price_routine_amount` double COMMENT '正价常规商品营收 |上游：aws.business_active_user_last_14_day.normal_price_routine_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_routine_user_sk` int COMMENT '正价常规商品付费用户 |上游：aws.business_active_user_last_14_day.normal_price_routine_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_routine_order_cnt` int COMMENT '正价常规商品付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_routine_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_first_purchase_routine_amount` double COMMENT '正价首购常规商品营收 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_routine_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_routine_user_sk` int COMMENT '正价首购常规商品付费用户 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_routine_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_first_purchase_routine_order_cnt` int COMMENT '正价首购常规商品付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_first_purchase_routine_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
    `normal_price_repurchase_routine_amount` double COMMENT '正价复购常规商品营收 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_routine_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_routine_user_sk` int COMMENT '正价复购常规商品付费用户 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_routine_user_sk；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `normal_price_repurchase_routine_order_cnt` int COMMENT '正价复购常规商品付费订单数 |上游：aws.business_active_user_last_14_day.normal_price_repurchase_routine_order_cnt；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `team_ids` array<string> COMMENT '全域团队归属 ID |上游：订单宽表聚合结果 |加工：会导致同一用户同日拆行',
    `team_names` array<string> COMMENT '全域团队归属名称 |上游：同上 |加工：会导致同一用户同日拆行',
    `user_allocation` array<string> COMMENT '用户全域服务期 |上游：当日活跃明细主链 |加工：无',
    `normal_price_scheme_amount` double COMMENT '正价方案型商品营收 |上游：当日订单中 good_kind_id_level_1 为方案型 |加工：无',
    `normal_price_non_scheme_amount` double COMMENT '正价非方案型商品营收 |上游：当日订单中非方案型部分 |加工：无',
    `fix_normal_price_amount` double COMMENT '修正后的正价营收 |上游：基于 business_gmv_attribution、sell_from、sync_type 重算 APP 实际成单口径 |加工：非原始订单金额',
    `fix_normal_price_scheme_amount` double COMMENT '修正的正价方案型商品营收 |上游：aws.business_active_user_last_14_day.fix_normal_price_scheme_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `fix_normal_price_non_scheme_amount` double COMMENT '修正的正价非方案型商品营收 |上游：aws.business_active_user_last_14_day.fix_normal_price_non_scheme_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `is_tele_belong_day` string COMMENT '已废弃字段 |上游：代码直接写 NULL |加工：已下线',
    `is_tele_belong_month` string COMMENT '已废弃字段 |上游：代码直接写 NULL |加工：已下线',
    `is_tele_receive_month` string COMMENT '已废弃字段 |上游：代码直接写 NULL |加工：已下线',
    `new_normal_price_scheme_amount` double COMMENT '新方案型商品营收 |上游：按 business_good_kind_name_level_1 in (\'组合品\',\'续购\') 聚合 |加工：新价格方案口径',
    `new_normal_price_scheme_zuhepin_amount` double COMMENT '新方案型-组合品营收 |上游：business_good_kind_name_level_1=\'组合品\' |加工：无',
    `new_normal_price_scheme_zuhepin_buchajia_amount` double COMMENT '新方案型-组合品-补差策略营收 |上游：aws.business_active_user_last_14_day.new_normal_price_scheme_zuhepin_buchajia_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `new_normal_price_scheme_zuhepin_mulchild_amount` double COMMENT '新方案型-组合品-多孩策略营收 |上游：aws.business_active_user_last_14_day.new_normal_price_scheme_zuhepin_mulchild_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `new_normal_price_scheme_zuhepin_highhoardcourse_amount` double COMMENT '新方案型-组合品-高中囤课策略营收 |上游：aws.business_active_user_last_14_day.new_normal_price_scheme_zuhepin_highhoardcourse_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `new_normal_price_scheme_zuhepin_padaddpur_amount` double COMMENT '新方案型-组合品-学习机加购策略营收 |上游：aws.business_active_user_last_14_day.new_normal_price_scheme_zuhepin_padaddpur_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `new_normal_price_scheme_zuhepin_hismem_amount` double COMMENT '新方案型-组合品-历史大会员续购策略营收 |上游：aws.business_active_user_last_14_day.new_normal_price_scheme_zuhepin_hismem_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `new_normal_price_scheme_zuhepin_non_singular_amount` double COMMENT '新方案型-组合品-无策略-单学段营收 |上游：aws.business_active_user_last_14_day.new_normal_price_scheme_zuhepin_non_singular_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `new_normal_price_scheme_zuhepin_non_plural_amount` double COMMENT '新方案型-组合品-无策略-多学段营收 |上游：aws.business_active_user_last_14_day.new_normal_price_scheme_zuhepin_non_plural_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `new_normal_price_scheme_xugou_common_amount` double COMMENT '新方案型-普通续购营收 |上游：business_good_kind_name_level_1=\'续购\' and business_good_kind_name_level_2=\'普通续购\' |加工：无',
    `new_normal_price_scheme_xugou_stageaddpeiyou_amount` double COMMENT '新方案型-续购-学段加购+培优课加购营收 |上游：aws.business_active_user_last_14_day.new_normal_price_scheme_xugou_stageaddpeiyou_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `new_normal_price_scheme_xugou_pad_amount` double COMMENT '新方案型-续购-学习机加购营收 |上游：aws.business_active_user_last_14_day.new_normal_price_scheme_xugou_pad_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `new_normal_price_non_scheme_amount` double COMMENT '新常规型商品营收 |上游：新价格方案中不属于 组合品/续购 的部分 |加工：无',
    `fix_new_normal_price_scheme_amount` double COMMENT '修正后的新方案型营收 |上游：基于 fix_normal_amount 再按新方案分类 |加工：APP 实际成单口径专用',
    `fix_new_normal_price_scheme_zuhepin_amount` double COMMENT '修正的新方案型-组合品营收 |上游：aws.business_active_user_last_14_day.fix_new_normal_price_scheme_zuhepin_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `fix_new_normal_price_scheme_zuhepin_buchajia_amount` double COMMENT '修正的新方案型-组合品-补差策略营收 |上游：aws.business_active_user_last_14_day.fix_new_normal_price_scheme_zuhepin_buchajia_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `fix_new_normal_price_scheme_zuhepin_mulchild_amount` double COMMENT '修正的新方案型-组合品-多孩策略营收 |上游：aws.business_active_user_last_14_day.fix_new_normal_price_scheme_zuhepin_mulchild_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `fix_new_normal_price_scheme_zuhepin_highhoardcourse_amount` double COMMENT '修正的新方案型-组合品-高中囤课策略营收 |上游：aws.business_active_user_last_14_day.fix_new_normal_price_scheme_zuhepin_highhoardcourse_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `fix_new_normal_price_scheme_zuhepin_padaddpur_amount` double COMMENT '修正的新方案型-组合品-学习机加购策略营收 |上游：aws.business_active_user_last_14_day.fix_new_normal_price_scheme_zuhepin_padaddpur_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `fix_new_normal_price_scheme_zuhepin_hismem_amount` double COMMENT '修正的新方案型-组合品-历史大会员续购策略营收 |上游：aws.business_active_user_last_14_day.fix_new_normal_price_scheme_zuhepin_hismem_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `fix_new_normal_price_scheme_zuhepin_non_singular_amount` double COMMENT '修正的新方案型-组合品-无策略-单学段营收 |上游：aws.business_active_user_last_14_day.fix_new_normal_price_scheme_zuhepin_non_singular_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `fix_new_normal_price_scheme_zuhepin_non_plural_amount` double COMMENT '修正的新方案型-组合品-无策略-多学段营收 |上游：aws.business_active_user_last_14_day.fix_new_normal_price_scheme_zuhepin_non_plural_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `fix_new_normal_price_scheme_xugou_common_amount` double COMMENT '修正的新方案型-续购-普通续购营收 |上游：aws.business_active_user_last_14_day.fix_new_normal_price_scheme_xugou_common_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `fix_new_normal_price_scheme_xugou_stageaddpeiyou_amount` double COMMENT '修正的新方案型-续购-学段加购+培优课加购营收 |上游：aws.business_active_user_last_14_day.fix_new_normal_price_scheme_xugou_stageaddpeiyou_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `fix_new_normal_price_scheme_xugou_pad_amount` double COMMENT '修正的新方案型-续购-学习机加购营收 |上游：aws.business_active_user_last_14_day.fix_new_normal_price_scheme_xugou_pad_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `fix_new_normal_price_non_scheme_amount` double COMMENT '修正的新常规型商品营收 |上游：aws.business_active_user_last_14_day.fix_new_normal_price_non_scheme_amount；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `big_vip_kind_day` string COMMENT '当日历史大会员标签 |上游：若日标签命中"历史大会员用户"则保留，否则记"非历史大会员用户" |加工：CASE 修正',
    `big_vip_kind_week` string COMMENT '周口径历史大会员标签 |上游：来自周活跃表 |加工：周首次活跃口径',
    `big_vip_kind_month` string COMMENT '月口径历史大会员标签 |上游：来自月活跃表 |加工：月首次活跃口径',
    `user_strategy_tag_day` string COMMENT '当日策略标签 |上游：当日活跃明细主链 |加工：无',
    `user_strategy_eligibility_day` string COMMENT '当日策略资格 |上游：当日活跃明细主链 |加工：无',
    `user_strategy_tag_month` string COMMENT '月口径策略标签 |上游：月首次活跃口径 |加工：无',
    `user_strategy_eligibility_month` string COMMENT '月口径策略资格 |上游：月首次活跃口径 |加工：无',
    `user_strategy_tag_year` string COMMENT '策略用户分层-年 |上游：aws.business_active_user_last_14_day.user_strategy_tag_year；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `user_strategy_eligibility_year` string COMMENT '用户策略资格-年 |上游：aws.business_active_user_last_14_day.user_strategy_eligibility_year；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `big_vip_kind_year` string COMMENT '历史大会员标签-年 |上游：aws.business_active_user_last_14_day.big_vip_kind_year；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
    `user_allocation_month` array<string> COMMENT '用户全域服务期-月 |上游：aws.business_active_user_last_14_day.user_allocation_month；当前表字段，详细来源与计算见对应 ETL/调度 |加工：无'
  ) COMMENT '近14天活跃用户日标（商业化）' PARTITIONED BY (`day` int COMMENT '分区业务日 |上游：写入 partition(day = 统计日) |加工：无') ROW FORMAT SERDE 'org.apache.hadoop.hive.ql.io.orc.OrcSerde' STORED AS INPUTFORMAT 'org.apache.hadoop.hive.ql.io.orc.OrcInputFormat' OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.orc.OrcOutputFormat' LOCATION 'tos://yc-data-platform/user/hive/warehouse/aws.db/business_active_user_last_14_day'

-- =====================================================
-- 关键枚举补充（来源 biMetadata）
-- =====================================================
--
-- ## 废弃字段
--
-- - is_tele_belong_day、is_tele_belong_month、is_tele_receive_month：当前代码写 NULL，请勿作为新口径依赖
--
-- ## 开放集合
--
-- - business_gmv_attribution、team_ids、team_names、user_allocation、*_status_*、big_vip_kind_*、user_strategy_*
--   为开放集合
-- - 所有金额、订单数与用户标记字段为数值/标记指标，非枚举分布表

-- =====================================================
-- 数据库校验（来源 biMetadata）
-- =====================================================
--
-- - 校验脚本：./scripts/hive-inspect.sh -d aws -t business_active_user_last_14_day -a
-- - 一次查库快照：最新分区 day=20260419；该分区行数 457,053

-- =====================================================
-- 现有枚举（保留：来源现有 DDL 注释）
-- =====================================================
--
-- 以下取值来自跳板机 Impala 实查 `aws.business_active_user_last_14_day`，条件 `WHERE day = 20260325`（int 分区，对应取数日「昨天」）；其它分区可能存在历史上未出现的取值。
-- 「含义」列暂空；数组字段 `team_ids` / `team_names` / `user_allocation` / `user_allocation_month` 为 `LATERAL VIEW explode` 后元素级 distinct。
--
-- ## grade_name_month（本月第一次活跃当天的年级）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | NULL | 未归类 |
-- | 一年级 | 一年级 |
-- | 七年级 | 七年级 |
-- | 三年级 | 三年级 |
-- | 九年级 | 九年级 |
-- | 二年级 | 二年级 |
-- | 五年级 | 五年级 |
-- | 八年级 | 八年级 |
-- | 六年级 | 六年级 |
-- | 四年级 | 四年级 |
-- | 学龄前 | 学龄前 |
-- | 职一 | 职一 |
-- | 职三 | 职三 |
-- | 职二 | 职二 |
-- | 高一 | 高一 |
-- | 高三 | 高三 |
-- | 高二 | 高二 |
--
-- ## stage_name_month（本月第一次活跃当天的学段）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | NULL | 未归类 |
-- | 中职 | 中职 |
-- | 初中 | 初中 |
-- | 启蒙 | 启蒙 |
-- | 小学 | 小学 |
-- | 高中 | 高中 |
--
-- ## grade_stage_name_month（本月第一次活跃当天的年级（其中把小学一二年级划分为小初，三四年级划分为小中，五六年级划分为小高））
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | NULL | 未归类 |
-- | 七年级 | 七年级 |
-- | 九年级 | 九年级 |
-- | 八年级 | 八年级 |
-- | 学龄前 | 学龄前 |
-- | 小中 | 小中 |
-- | 小初 | 小初 |
-- | 小高 | 小高 |
-- | 职一 | 职一 |
-- | 职三 | 职三 |
-- | 职二 | 职二 |
-- | 高一 | 高一 |
-- | 高三 | 高三 |
-- | 高二 | 高二 |
--
--
-- ## business_user_pay_status_statistics_month（本月第一次活跃当天的统计维度：新增、老未、大会员付费、非大会员付费）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 新增 |新增 |
-- | 续费用户 |续费用户 |
-- | 老未 |老未 |
-- | 高净值用户 |高净值用户 |
--
-- ## business_gmv_attribution（营收归属）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | NULL | 未归类 |
-- | 体验营 | 体验营 |
-- | 商业化 | 商业化，业务术语有时称"app",如果提到"app"需要确认是否"商业化" |
-- | 商业化-电商 | 商业化-电商 |
-- | 新媒体变现 | 新媒体变现 |
-- | 新媒体视频 | 新媒体视频 |
-- | 电销 | 电销 |
--
--
-- ## grade_name_year（本年第一次活跃年级）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | NULL | 未归类 |
-- | 一年级 | 一年级 |
-- | 七年级 | 七年级 |
-- | 三年级 | 三年级 |
-- | 九年级 | 九年级 |
-- | 二年级 | 二年级 |
-- | 五年级 | 五年级 |
-- | 八年级 | 八年级 |
-- | 六年级 | 六年级 |
-- | 四年级 | 四年级 |
-- | 学龄前 | 学龄前 |
-- | 职一 | 职一 |
-- | 职三 | 职三 |
-- | 职二 | 职二 |
-- | 高一 | 高一 |
-- | 高三 | 高三 |
-- | 高二 | 高二 |
--
-- ## stage_name_year（本年第一次活跃学段）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | NULL | 未归类 |
-- | 中职 | 中职 |
-- | 初中 | 初中 |
-- | 启蒙 | 启蒙 |
-- | 小学 | 小学 |
-- | 高中 | 高中 |
--
-- ## grade_stage_name_year（本年第一次活跃年级段）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | NULL | 未归类 |
-- | 七年级 | 七年级 |
-- | 九年级 | 九年级 |
-- | 八年级 | 八年级 |
-- | 学龄前 | 学龄前 |
-- | 小中 | 小中 |
-- | 小初 | 小初 |
-- | 小高 | 小高 |
-- | 职一 | 职一 |
-- | 职三 | 职三 |
-- | 职二 | 职二 |
-- | 高一 | 高一 |
-- | 高三 | 高三 |
-- | 高二 | 高二 |
--
--
-- ## business_user_pay_status_statistics_year（本年第一次活跃商业化付费分层）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 新增 |新增 |
-- | 续费用户 |续费用户 |
-- | 老未 |老未 |
-- | 高净值用户 |高净值用户 |
--
-- ## business_user_pay_status_statistics_day（商业化付费分层）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 新增 |新增 |
-- | 续费用户 |续费用户 |
-- | 老未 |老未 |
-- | 高净值用户 |高净值用户 |
--
-- ## business_user_pay_status_business_day（当天付费分层-业务维度）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 新用户 |新用户 |
-- | 续费用户 |续费用户 |
-- | 老用户 |老用户 |
-- | 高净值用户 |高净值用户 |
--
-- ## business_user_pay_status_business_month（本月第一次活跃时付费分层-业务维度-拆分付费）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 新用户 |新用户 |
-- | 续费用户 |续费用户 |
-- | 老用户 |老用户 |
-- | 高净值用户 |高净值用户 |
--
-- ## business_user_pay_status_business_year（本年第一次活跃时付费分层-业务维度-拆分付费）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 新用户 |新用户 |
-- | 续费用户 |续费用户 |
-- | 老用户 |老用户 |
-- | 高净值用户 |高净值用户 |
--
-- ## grade_name_day（当天用户年级）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | NULL | 未归类 |
-- | 一年级 | 一年级 |
-- | 七年级 | 七年级 |
-- | 三年级 | 三年级 |
-- | 九年级 | 九年级 |
-- | 二年级 | 二年级 |
-- | 五年级 | 五年级 |
-- | 八年级 | 八年级 |
-- | 六年级 | 六年级 |
-- | 四年级 | 四年级 |
-- | 学龄前 | 学龄前 |
-- | 职一 | 职一 |
-- | 职三 | 职三 |
-- | 职二 | 职二 |
-- | 高一 | 高一 |
-- | 高三 | 高三 |
-- | 高二 | 高二 |
--
-- ## stage_name_day（当天用户学段）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | NULL | 未归类 |
-- | 中职 | 中职 |
-- | 初中 | 初中 |
-- | 启蒙 | 启蒙 |
-- | 小学 | 小学 |
-- | 高中 | 高中 |
--
-- ## grade_stage_name_day（当天用户年级段）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | NULL | 未归类 |
-- | 七年级 | 七年级 |
-- | 九年级 | 九年级 |
-- | 八年级 | 八年级 |
-- | 学龄前 | 学龄前 |
-- | 小中 | 小中 |
-- | 小初 | 小初 |
-- | 小高 | 小高 |
-- | 职一 | 职一 |
-- | 职三 | 职三 |
-- | 职二 | 职二 |
-- | 高一 | 高一 |
-- | 高三 | 高三 |
-- | 高二 | 高二 |
--
-- ## team_ids（全域业绩归属，数组元素）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 11 |见team_names |
-- | 12 |见team_names |
-- | 2 |见team_names |
-- | 4 |见team_names |
-- | 5 |见team_names |
-- | 6 |见team_names |
-- | 8 |见team_names |
-- | 9 |见team_names |
--
-- ## team_names（全域业绩归属，数组元素）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 体验营 | |
-- | 商业化-APP | |
-- | 商业化-公域 | |
-- | 客服-仅用于标记订单 | |
-- | 新媒体视频 | |
-- | 智能硬件-仅用于标记订单 | |
-- | 电销/网销 | |
-- | 研学 | |
--
-- ## user_allocation（用户全域服务期，数组元素）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 体验营 | 体验营 |
-- | 新媒体视频 | 新媒体视频 |
-- | 电销/网销 | 电销/网销 |
--
--
-- ## big_vip_kind_day（历史大会员标签-日）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 历史大会员用户_不可续购 | 历史大会员用户_不可续购 |
-- | 历史大会员用户_可续购 | 历史大会员用户_可续购 |
-- | 非历史大会员用户 | 非历史大会员用户 |
--
-- ## big_vip_kind_week（历史大会员标签-周）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 历史大会员用户_不可续购 | 历史大会员用户_不可续购 |
-- | 历史大会员用户_可续购 | 历史大会员用户_可续购 |
-- | 非历史大会员用户 | 非历史大会员用户 |
--
-- ## big_vip_kind_month（历史大会员标签-月）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 历史大会员用户_不可续购 | 历史大会员用户_不可续购 |
-- | 历史大会员用户_可续购 | 历史大会员用户_可续购 |
-- | 非历史大会员用户 | 非历史大会员用户 |
--
-- ## user_strategy_tag_day（用户策略标签）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 付费加购品用户 | 付费加购品用户  |
-- | 付费组合品用户 | 付费组合品用户 |
-- | 付费零售品用户 | 付费零售品用户 |
-- | 历史大会员用户_不可续购 | 历史大会员用户_不可续购 |
-- | 历史大会员用户_可续购 | 历史大会员用户_可续购 |
-- | 新用户 | 新用户 |
-- | 老用户 | 老用户 |
--
-- ## user_strategy_eligibility_day（用户策略资格）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | (空字符串) | |
-- | 历史大会员续购策略资格;学习机加购策略资格 | 历史大会员续购策略资格;学习机加购策略资格 |
-- | 历史大会员续购策略资格;学习机加购策略资格;小学品升级补差至小初品资格 | 历史大会员续购策略资格;学习机加购策略资格;小学品升级补差至小初品资格 |
-- | 学习机加购策略资格;高中囤课策略资格 | 学习机加购策略资格;高中囤课策略资格 |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版 | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版 |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小初同步品升级补差至小初品资格 | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小初同步品升级补差至小初品资格 |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格 | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格 |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格;小初同步品升级补差至小初品资格 | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格;小初同步品升级补差至小初品资格 |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版 | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版 |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小初同步品升级补差至小初品资格 | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小初同步品升级补差至小初品资格 |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格 | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格 |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格;小初同步品升级补差至小初品资格 | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格;小初同步品升级补差至小初品资格 |
-- | 学习机加购策略资格;高中囤课策略资格;小学品升级补差至小初品资格 | 学习机加购策略资格;高中囤课策略资格;小学品升级补差至小初品资格 |
-- | 小初同步品升级补差至小初品资格 | 小初同步品升级补差至小初品资格 |
-- | 小学品升级补差至小初品资格 | 小学品升级补差至小初品资格 |
--
-- ## user_strategy_tag_month（策略用户分层-月）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 付费加购品用户 | 付费加购品用户 |
-- | 付费组合品用户 | 付费组合品用户 |
-- | 付费零售品用户 | 付费零售品用户 |
-- | 历史大会员用户_不可续购 | 历史大会员用户_不可续购 |
-- | 历史大会员用户_可续购 | 历史大会员用户_可续购 |
-- | 新用户 | 新用户 |
-- | 老用户 | 老用户 |
--
-- ## user_strategy_eligibility_month（用户策略资格-月）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | (空字符串) | 无策略资格 |
-- | 历史大会员续购策略资格;学习机加购策略资格 | 历史大会员续购策略资格;学习机加购策略资格 |
-- | 历史大会员续购策略资格;学习机加购策略资格;小学品升级补差至小初品资格 | 历史大会员续购策略资格;学习机加购策略资格;小学品升级补差至小初品资格 |
-- | 学习机加购策略资格;高中囤课策略资格 | 学习机加购策略资格;高中囤课策略资格 |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版 | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版 |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小初同步品升级补差至小初品资格 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格;小初同步品升级补差至小初品资格 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小初同步品升级补差至小初品资格 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格;小初同步品升级补差至小初品资格 | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格;小初同步品升级补差至小初品资格 |
-- | 学习机加购策略资格;高中囤课策略资格;小学品升级补差至小初品资格 | 学习机加购策略资格;高中囤课策略资格;小学品升级补差至小初品资格 |
-- | 小初同步品升级补差至小初品资格 | 小初同步品升级补差至小初品资格 |
-- | 小学品升级补差至小初品资格 | |
--
-- ## user_strategy_tag_year（策略用户分层-年）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 付费加购品用户 | |
-- | 付费组合品用户 | |
-- | 付费零售品用户 | |
-- | 历史大会员用户_不可续购 | |
-- | 历史大会员用户_可续购 | |
-- | 新用户 | |
-- | 老用户 | |
--
-- ## user_strategy_eligibility_year（用户策略资格-年）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | (空字符串) | 无策略资格 |
-- | 历史大会员续购策略资格;学习机加购策略资格 | |
-- | 历史大会员续购策略资格;学习机加购策略资格;小初同步品升级补差至小初品资格 | |
-- | 历史大会员续购策略资格;学习机加购策略资格;小学品升级补差至小初品资格 | |
-- | 学习机加购策略资格;高中囤课策略资格 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小初同步品升级补差至小初品资格 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格;小初同步品升级补差至小初品资格 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小初同步品升级补差至小初品资格 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格;小初同步品升级补差至小初品资格 | |
-- | 学习机加购策略资格;高中囤课策略资格;小学品升级补差至小初品资格 | |
-- | 小学品升级补差至小初品资格 | |
--
-- ## big_vip_kind_year（历史大会员标签-年）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 历史大会员用户_不可续购 | 历史大会员用户_不可续购 |
-- | 历史大会员用户_可续购 | 历史大会员用户_可续购 |
-- | 非历史大会员用户 | 非历史大会员用户 |
--
-- ## user_allocation_month（用户全域服务期-月，数组元素）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 体验营 | 体验营 |
-- | 入校 | 入校 |
-- | 新媒体视频 | 新媒体视频 |
-- | 电销/网销 | 电销/网销 |
