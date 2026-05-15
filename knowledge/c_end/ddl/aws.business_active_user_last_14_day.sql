-- =====================================================
-- 公用- C端活跃日表 aws.business_active_user_last_14_day
-- =====================================================
--
-- 【表粒度】
--   一用户一天多行（team_ids、team_names、business_gmv_attribution是订单粒度的标签，一个用户一天可能有多条记录；分区字段：day；近 14 天窗口内商业/付费等标签）
--
-- 【业务定位】
--   - 【归属】公用 / C端活跃日表。
-- - 与 dws.topic_user_active_detail_day 按 u_user + day 关联；含 *_day 后缀分层字段（与活跃日表同名字段语义不完全等同，见 table-relations）；与 dw.dim_user 可按 u_user 对齐
--   - 用户只包括c端活跃用户，不包括b端活跃用户

-- 【统计口径】
--   表内营收/订单汇总列见字段 COMMENT
--
-- 【常用关联】
--   - u_user、day 对齐 dws.topic_user_active_detail_day
--
-- 【常用筛选条件】
--   场景条件：
--   - day、分层字段按归因/寒假等需求
--
-- 【注意事项】
--   - JOIN 字段与活跃日表差异见 `knowledge/table-relations.md`
--   - 更新频率 T+1
--   - 知识库约定：取数与分析仅使用 business_user_pay_status_*；user_pay_status_*（无 business_ 前缀）列不在知识库维护口径

CREATE TABLE
  `aws`.`business_active_user_last_14_day` (`user_sk` int COMMENT '用户id',
    `grade_name_month` string COMMENT '本月第一次活跃当天的年级',
    `stage_name_month` string COMMENT '本月第一次活跃当天的学段',
    `grade_stage_name_month` string COMMENT '本月第一次活跃当天的年级（其中把小学一二年级划分为小初，三四年级划分为小中，五六年级划分为小高）',
    `user_pay_status_statistics_month` string COMMENT '【知识库不引用】取数用 business_user_pay_status_statistics_month。原：本月第一次活跃当天的统计维度：新增、老未、付费的标签',
    `user_pay_status_business_month` string COMMENT '【知识库不引用】取数用 business_user_pay_status_business_month。原：本月第一次活跃当天的策略维度：新用户、老用户、付费用户',
    `business_user_pay_status_statistics_month` string COMMENT '本月第一次活跃当天的统计维度：新增、老未、大会员付费、非大会员付费',
    `month_first_day` int COMMENT '当月第一天',
    `month_days` int COMMENT '当月天数',
    `business_gmv_attribution` string COMMENT '营收归属',
    `amount` double COMMENT '营收',
    `pay_user_sk` int COMMENT '付费用户数',
    `normal_price_amount` double COMMENT '正价营收',
    `normal_price_user_sk` int COMMENT '正价付费用户',
    `normal_price_big_vip_amount` double COMMENT '正价营收-大会员',
    `normal_price_big_vip_user_sk` int COMMENT '正价大会员付费用户',
    `normal_price_big_vip_xugou_amount` double COMMENT '正价营收-大会员续购',
    `normal_price_big_vip_xugou_user_sk` int COMMENT '正价大会员续购付费用户',
    `normal_price_total_review_amount` double COMMENT '正价营收-总复习',
    `normal_price_total_review_user_sk` int COMMENT '正价总复习付费用户',
    `normal_price_vip_amount` double COMMENT '正价营收-同步课',
    `normal_price_vip_user_sk` int COMMENT '正价同步课付费用户',
    `normal_price_other_amount` double COMMENT '正价营收-其他商品',
    `normal_price_other_user_sk` int COMMENT '正价其他商品付费用户',
    `normal_price_order_cnt` int COMMENT '正价付费订单数',
    `normal_price_big_vip_order_cnt` int COMMENT '正价大会员付费订单数',
    `normal_price_big_vip_xugou_order_cnt` int COMMENT '正价大会员续购付费订单数',
    `normal_price_vip_order_cnt` int COMMENT '正价同步课付费订单数',
    `normal_price_total_review_order_cnt` int COMMENT '正价总复习付费订单数',
    `normal_price_other_order_cnt` int COMMENT '正价其他商品付费订单数',
    `normal_price_first_purchase_amount` double COMMENT '正价首购营收',
    `normal_price_first_purchase_user_sk` int COMMENT '正价首购付费用户',
    `normal_price_first_purchase_big_vip_amount` double COMMENT '正价首购营收-大会员',
    `normal_price_first_purchase_big_vip_user_sk` int COMMENT '正价首购大会员付费用户',
    `normal_price_first_purchase_big_vip_xugou_amount` double COMMENT '正价首购营收-大会员续购',
    `normal_price_first_purchase_big_vip_xugou_user_sk` int COMMENT '正价首购大会员续购付费用户',
    `normal_price_first_purchase_total_review_amount` double COMMENT '正价首购营收-总复习',
    `normal_price_first_purchase_total_review_user_sk` int COMMENT '正价首购总复习付费用户',
    `normal_price_first_purchase_vip_amount` double COMMENT '正价首购营收-同步课',
    `normal_price_first_purchase_vip_user_sk` int COMMENT '正价首购同步课付费用户',
    `normal_price_first_purchase_other_amount` double COMMENT '正价首购营收-其他商品',
    `normal_price_first_purchase_other_user_sk` int COMMENT '正价首购其他商品付费用户',
    `normal_price_first_purchase_order_cnt` int COMMENT '正价首购付费订单数',
    `normal_price_first_purchase_big_vip_order_cnt` int COMMENT '正价首购大会员付费订单数',
    `normal_price_first_purchase_big_vip_xugou_order_cnt` int COMMENT '正价首购大会员续购付费订单数',
    `normal_price_first_purchase_vip_order_cnt` int COMMENT '正价首购同步课付费订单数',
    `normal_price_first_purchase_total_review_order_cnt` int COMMENT '正价首购总复习付费订单数',
    `normal_price_first_purchase_other_order_cnt` int COMMENT '正价首购其他商品付费订单数',
    `normal_price_repurchase_amount` double COMMENT '正价复购营收',
    `normal_price_repurchase_user_sk` int COMMENT '正价复购付费用户',
    `normal_price_repurchase_big_vip_amount` double COMMENT '正价复购营收-大会员',
    `normal_price_repurchase_big_vip_user_sk` int COMMENT '正价复购大会员付费用户',
    `normal_price_repurchase_big_vip_xugou_amount` double COMMENT '正价复购营收-大会员续购',
    `normal_price_repurchase_big_vip_xugou_user_sk` int COMMENT '正价复购大会员续购付费用户',
    `normal_price_repurchase_total_review_amount` double COMMENT '正价复购营收-总复习',
    `normal_price_repurchase_total_review_user_sk` int COMMENT '正价复购总复习付费用户',
    `normal_price_repurchase_vip_amount` double COMMENT '正价复购营收-同步课',
    `normal_price_repurchase_vip_user_sk` int COMMENT '正价复购同步课付费用户',
    `normal_price_repurchase_other_amount` double COMMENT '正价复购营收-其他商品',
    `normal_price_repurchase_other_user_sk` int COMMENT '正价复购其他商品付费用户',
    `normal_price_repurchase_order_cnt` int COMMENT '正价复购付费订单数',
    `normal_price_repurchase_big_vip_order_cnt` int COMMENT '正价复购大会员付费订单数',
    `normal_price_repurchase_big_vip_xugou_order_cnt` int COMMENT '正价复购大会员续购付费订单数',
    `normal_price_repurchase_vip_order_cnt` int COMMENT '正价复购同步课付费订单数',
    `normal_price_repurchase_total_review_order_cnt` int COMMENT '正价复购总复习付费订单数',
    `normal_price_repurchase_other_order_cnt` int COMMENT '正价复购其他商品付费订单数',
    `day_timestamp` timestamp COMMENT '时间戳',
    `grade_name_year` string COMMENT '本年第一次活跃年级',
    `stage_name_year` string COMMENT '本年第一次活跃学段',
    `grade_stage_name_year` string COMMENT '本年第一次活跃年级段',
    `user_pay_status_statistics_year` string COMMENT '【知识库不引用】取数用 business_user_pay_status_statistics_year。原：本年第一次活跃付费统计分层',
    `user_pay_status_business_year` string COMMENT '【知识库不引用】取数用 business_user_pay_status_business_year。原：本年第一次活跃付费业务分层',
    `business_user_pay_status_statistics_year` string COMMENT '本年第一次活跃商业化付费分层',
    `u_user` string COMMENT '用户id',
    `user_pay_status_statistics_day` string COMMENT '【知识库不引用】取数用 business_user_pay_status_statistics_day。原：付费分层-统计维度',
    `user_pay_status_business_day` string COMMENT '【知识库不引用】取数用 business_user_pay_status_business_day。原：付费分层-业务维度',
    `business_user_pay_status_statistics_day` string COMMENT '商业化付费分层',
    `business_user_pay_status_business_day` string COMMENT '当天付费分层-业务维度',
    `business_user_pay_status_business_month` string COMMENT '本月第一次活跃时付费分层-业务维度-拆分付费',
    `business_user_pay_status_business_year` string COMMENT '本年第一次活跃时付费分层-业务维度-拆分付费',
    `grade_name_day` string COMMENT '当天用户年级',
    `stage_name_day` string COMMENT '当天用户学段',
    `grade_stage_name_day` string COMMENT '当天用户年级段',
    `normal_price_routine_amount` double COMMENT '正价常规商品营收',
    `normal_price_routine_user_sk` int COMMENT '正价常规商品付费用户',
    `normal_price_routine_order_cnt` int COMMENT '正价常规商品付费订单数',
    `normal_price_first_purchase_routine_amount` double COMMENT '正价首购常规商品营收',
    `normal_price_first_purchase_routine_user_sk` int COMMENT '正价首购常规商品付费用户',
    `normal_price_first_purchase_routine_order_cnt` int COMMENT '正价首购常规商品付费订单数',
    `normal_price_repurchase_routine_amount` double COMMENT '正价复购常规商品营收',
    `normal_price_repurchase_routine_user_sk` int COMMENT '正价复购常规商品付费用户',
    `normal_price_repurchase_routine_order_cnt` int COMMENT '正价复购常规商品付费订单数',
    `team_ids` array < string > COMMENT '全域业绩归属',
    `team_names` array < string > COMMENT '全域业绩归属',
    `user_allocation` array < string > COMMENT '用户全域服务期',
    `normal_price_scheme_amount` double COMMENT '正价方案型商品营收',
    `normal_price_non_scheme_amount` double COMMENT '正价非方案型商品营收',
    `fix_normal_price_amount` double COMMENT '修正的正价营收',
    `fix_normal_price_scheme_amount` double COMMENT '修正的正价方案型商品营收',
    `fix_normal_price_non_scheme_amount` double COMMENT '修正的正价非方案型商品营收',
    `is_tele_belong_day` string COMMENT '已废弃',
    `is_tele_belong_month` string COMMENT '已废弃',
    `is_tele_receive_month` string COMMENT '已废弃',
    `new_normal_price_scheme_amount` double COMMENT '新方案型商品营收',
    `new_normal_price_scheme_zuhepin_amount` double COMMENT '新方案型-组合品营收',
    `new_normal_price_scheme_zuhepin_buchajia_amount` double COMMENT '新方案型-组合品-补差策略营收',
    `new_normal_price_scheme_zuhepin_mulchild_amount` double COMMENT '新方案型-组合品-多孩策略营收',
    `new_normal_price_scheme_zuhepin_highhoardcourse_amount` double COMMENT '新方案型-组合品-高中囤课策略营收',
    `new_normal_price_scheme_zuhepin_padaddpur_amount` double COMMENT '新方案型-组合品-学习机加购策略营收',
    `new_normal_price_scheme_zuhepin_hismem_amount` double COMMENT '新方案型-组合品-历史大会员续购策略营收',
    `new_normal_price_scheme_zuhepin_non_singular_amount` double COMMENT '新方案型-组合品-无策略-单学段营收',
    `new_normal_price_scheme_zuhepin_non_plural_amount` double COMMENT '新方案型-组合品-无策略-多学段营收',
    `new_normal_price_scheme_xugou_common_amount` double COMMENT '新方案型-续购-普通续购营收',
    `new_normal_price_scheme_xugou_stageaddpeiyou_amount` double COMMENT '新方案型-续购-学段加购+培优课加购营收',
    `new_normal_price_scheme_xugou_pad_amount` double COMMENT '新方案型-续购-学习机加购营收',
    `new_normal_price_non_scheme_amount` double COMMENT '新常规型商品营收',
    `fix_new_normal_price_scheme_amount` double COMMENT '修正的新方案型商品营收',
    `fix_new_normal_price_scheme_zuhepin_amount` double COMMENT '修正的新方案型-组合品营收',
    `fix_new_normal_price_scheme_zuhepin_buchajia_amount` double COMMENT '修正的新方案型-组合品-补差策略营收',
    `fix_new_normal_price_scheme_zuhepin_mulchild_amount` double COMMENT '修正的新方案型-组合品-多孩策略营收',
    `fix_new_normal_price_scheme_zuhepin_highhoardcourse_amount` double COMMENT '修正的新方案型-组合品-高中囤课策略营收 ',
    `fix_new_normal_price_scheme_zuhepin_padaddpur_amount` double COMMENT '修正的新方案型-组合品-学习机加购策略营收',
    `fix_new_normal_price_scheme_zuhepin_hismem_amount` double COMMENT '修正的新方案型-组合品-历史大会员续购策略营收',
    `fix_new_normal_price_scheme_zuhepin_non_singular_amount` double COMMENT '修正的新方案型-组合品-无策略-单学段营收',
    `fix_new_normal_price_scheme_zuhepin_non_plural_amount` double COMMENT '修正的新方案型-组合品-无策略-多学段营收',
    `fix_new_normal_price_scheme_xugou_common_amount` double COMMENT '修正的新方案型-续购-普通续购营收',
    `fix_new_normal_price_scheme_xugou_stageaddpeiyou_amount` double COMMENT '修正的新方案型-续购-学段加购+培优课加购营收',
    `fix_new_normal_price_scheme_xugou_pad_amount` double COMMENT '修正的新方案型-续购-学习机加购营收',
    `fix_new_normal_price_non_scheme_amount` double COMMENT '修正的新常规型商品营收',
    `big_vip_kind_day` string COMMENT '历史大会员标签-日',
    `big_vip_kind_week` string COMMENT '历史大会员标签-周',
    `big_vip_kind_month` string COMMENT '历史大会员标签-月',
    `user_strategy_tag_day` string COMMENT '用户策略标签',
    `user_strategy_eligibility_day` string COMMENT '用户策略资格',
    `user_strategy_tag_month` string COMMENT '策略用户分层-月',
    `user_strategy_eligibility_month` string COMMENT '用户策略资格-月',
    `user_strategy_tag_year` string COMMENT '策略用户分层-年',
    `user_strategy_eligibility_year` string COMMENT '用户策略资格-年',
    `big_vip_kind_year` string COMMENT '历史大会员标签-年',
    `user_allocation_month` array < string > COMMENT '用户全域服务期-月') COMMENT '近14天活跃用户日标（商业化）' PARTITIONED BY (`day` int COMMENT '分区字段') ROW FORMAT SERDE 'org.apache.hadoop.hive.ql.io.orc.OrcSerde' STORED AS INPUTFORMAT 'org.apache.hadoop.hive.ql.io.orc.OrcInputFormat' OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.orc.OrcOutputFormat' LOCATION 'tos://yc-data-platform/user/hive/warehouse/aws.db/business_active_user_last_14_day'

-- =====================================================
-- 枚举值
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
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版 | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版 |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版;小初同步品升级补差至小初品资格 | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版;小初同步品升级补差至小初品资格 |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格 | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格 |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格;小初同步品升级补差至小初品资格 | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格;小初同步品升级补差至小初品资格 |
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
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版;小初同步品升级补差至小初品资格 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格;小初同步品升级补差至小初品资格 | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格;小初同步品升级补差至小初品资格 |
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
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版;小初同步品升级补差至小初品资格 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格 | |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格_寒促特别版;小学品升级补差至小初品资格;小初同步品升级补差至小初品资格 | |
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
