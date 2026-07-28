-- =====================================================
-- 全公司订单宽表 dws.topic_order_detail
-- =====================================================
--
--

-- =====================================================
-- 【表粒度】★必填
--   一笔子订单 = 一条记录（order_id + sub_good_sk 唯一）
--   同一订单包含多个子商品时会有多条记录
--
-- =====================================================

-- =====================================================
-- 【业务定位】
--   全公司所有业务的订单（电销、新媒体、入校、体验营等）
--
--
--   与电销专用 aws.crm_order_info 区分：
--   - 本表：全公司所有业务订单
--   - 电销订单表：仅电销业务订单
--
--   营收归属差异：
--   - business_gmv_attribution 按服务期优先级归属到某一业务
--   - 双服务期用户的营收可能归属非电销
--   - 因此：本表筛选电销后的营收 ≠ 电销订单表营收
--
--   选表原则：
--   - 活跃转化分析 → 用本表（全量订单）
--   - 判断用户是否购买过某商品 → 用本表（⚠️ 强制，不可用单业务表）
--   - 电销营收分析 → 用电销订单表（使用电销营收时使用）
--
--   - 服务期营收：team_names
--   - 与活跃表联：u_user
--
--   补充（来源 biMetadata）：
--   覆盖全公司业务线（电销、新媒体、入校、轻课等）的订单宽表，统一看订单、商品、用户、组织架构、
--   GMV 归属、退款、策略标签等。相比单一业务线订单表，更适合做**全域营收、用户购买、商品结构、
--   渠道/组织归因**分析。
--
-- =====================================================

-- =====================================================
-- 【统计口径】
--   订单量 = COUNT(DISTINCT order_id)
--   营收金额 = SUM(order_amount)（先按 order_id 去重）或 SUM(sub_amount)（子订单粒度）
--   转化用户量 = COUNT(DISTINCT u_user)
--
--   正价：order_amount >= 39（不推荐用 is_normal_price）
--   订单、营收、GMV、ARPU 分子、付费金额默认必须筛选 is_test_user = 0，排除测试用户。
--   例外：月报/看板对齐口径下，订单需先 JOIN 同月活跃池，且订单层不筛 is_test_user = 0，以 glossary.md 为准。
--   看营收/GMV/ARPU 分子/付费金额时，默认不筛选 status = '支付成功'；
--   只有用户明确要求支付成功、退款、到账或指定订单状态时，才按需求筛选 status。
--
--   仅统计新增注册/注册用户 LTV 看板口径时，使用到账金额：SUM(arrival_amount)，订单状态 status in ('支付成功','退款成功')。
--   非新增注册场景不得套用该例外，仍以 glossary.md 对应指标口径为准。
--
--   注意：业务指标的权威定义在 glossary.md，本段仅记录"用本表怎么算"
--
--   补充（来源 biMetadata）：
--   - 表内默认是一笔**子订单一行**，直接 count(*) 得到的是子订单行数，不一定等于业务订单数
--   - 看订单量通常用 count(distinct order_id)；看购买用户量通常用 count(distinct user_sk) 或 count(distinct u_user)
--   - 金额类需区分：order_amount / sub_amount / original_amount / discount_amount / total_refund_amt 等，口径不可混用
--
-- =====================================================
-- 【常用关联】（来源 biMetadata）
--
-- | 场景 | Join Key | 说明 |
-- |------|----------|------|
-- | 用户画像 | user_sk / u_user | 可关联 dws.topic_user_info 或 dw.dim_user_his |
-- | 学校地域 | school_sk / city_code | 关联学校、地域维度 |
-- | 组织架构 | workplace_id、department_id、regiment_id、team_id、worker_id | 销售组织链路分析 |
--
-- =====================================================

-- =====================================================
-- 【常用筛选条件】
--   ★必加条件：
--   - is_test_user = 0                       -- 排除测试用户
--     例外：月报/看板对齐口径不加该条件，需先圈活跃池再统计池内订单
--
--   场景条件：
--   - status = '支付成功'                    -- 仅用户明确要求支付成功口径时加；看营收默认不加
--   - order_amount >= 39                     -- 正价订单
--
--   - business_gmv_attribution = '电销'      -- 限定电销业务（⚠️ 与电销订单表口径有差异）
--
--   补充（来源 biMetadata）：
--   - 非分区表，查询前应先加业务过滤条件，避免无条件全表扫
--   - 常见条件：is_test_user = 0、is_clue_seat = 1、business_gmv_attribution、
--     business_user_pay_status_business、商品类目字段等；status 仅在明确要求订单状态时使用
--
-- =====================================================

-- =====================================================
-- 【注意事项】
--
--   ⚠️ 金额字段说明：
--     · order_amount：订单实收金额（★营收统计用此字段，需先按 order_id 去重）
--     · sub_amount：子商品实收金额（子订单粒度用此字段）
--     · original_amount：订单原价
--     · arrival_amount：到账金额
--
--   ⚠️ good_type 已弃用，推荐使用 good_kind_name_level_2
--
--   ⚠️ 业务归属字段说明：
--     · business_gmv_attribution：业务GMV归属划分（★ 统一使用此字段）
--     · business_attribution：业务群归属（b端营收、小学网课营收、轻课营收）
--     · attribution：B/C订单归属
--
--   ⚠️ 电销相关字段（已验证与电销订单表一致）：
--     · workplace_id/regiment_id/worker_id：组织架构字段（100%匹配）
--     · is_clue_seat：线索是否在坐席名下（99.92%匹配）
--     · is_telemarketing_user：是否电销触达用户
--
--   ⚠️ 商品类目有两套体系：
--     · good_kind_name_level_1/2/3：商品 2.0 体系（2026-01-01 起生效）
--     · business_good_kind_name_level_1/2/3：策略组修正后的分类
--
--   补充常见误用（来源 biMetadata）：
--   | 误用 | 说明 |
--   |------|------|
--   | 直接 count(*) 当订单量 | 本表是一笔子订单一行，不是一个业务订单一行 |
--   | 混用多套商品类目 | good_kind_* 与 business_good_kind_* 代表不同分类口径 |
--   | 把 order_amount、sub_amount、real_deductible_price 当同口径金额 | 这些字段语义不同，需按业务需求选取 |
--   | 忽略时间层级补充字段 | 月/年首次付费标签、年级学段补充字段是衍生口径，不是订单原始属性 |
-- =====================================================

-- =====================================================
-- 【数据来源】（来源 biMetadata）
--
-- - 调度实现类：com.onion.etl.dws.TopicOrderDetail
-- - 关键依赖：dw.fact_order、dw.dim_user_regist、dw.fact_order_detail、dw.fact_userauth、
--   dw.fact_order_detail_refund、dw.dim_region
-- - 主流程会补充：商品学科信息、购买前权限截止日、轻课信息、保险/补差价、
--   用户月/年付费标签、线索归属、商品时长修正、策略标签等，再统一写入 dws.topic_order_detail
--
-- =====================================================

CREATE EXTERNAL TABLE `dws`.`topic_order_detail` (
  `order_id` string COMMENT '订单业务id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `create_time` timestamp COMMENT '源系统创建条目的时间 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `create_time_sk` string COMMENT '待补充 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `paid_time` timestamp COMMENT '支付时间 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `paid_time_sk` int COMMENT '支付时间sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `is_normal_price` smallint COMMENT '是否正价订单（不推荐，建议用 order_amount >= 39） |上游：由 ETL 或源表布尔/状态字段映射 |加工：按 ETL 映射为 0/1、true/false 或业务约定值域',
  `is_group_buy` smallint COMMENT '是否团购订单 |上游：由 ETL 或源表布尔/状态字段映射 |加工：按 ETL 映射为 0/1、true/false 或业务约定值域',
  `is_by_manual` smallint COMMENT '是否是手工订单 |上游：由 ETL 或源表布尔/状态字段映射 |加工：按 ETL 映射为 0/1、true/false 或业务约定值域',
  `business_group` string COMMENT '业务群 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `add_time_ms` bigint COMMENT '增加的服务时长 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `add_time_day` int COMMENT '增加的服务时长（天） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `product_id` string COMMENT '产品id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `payment_channel` string COMMENT '支付渠道，微信支付、支付宝支付、银联 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `app_channel` string COMMENT '创建订单的App的下载渠道，苹果是appstore |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `payment_platform` string COMMENT '支付平台[ping++ |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `client_os` string COMMENT '设备类型 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `is_recalled` smallint COMMENT '退款后是否回收权益 |上游：由 ETL 或源表布尔/状态字段映射 |加工：按 ETL 映射为 0/1、true/false 或业务约定值域',
  `shop_name` string COMMENT '推广来源 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `shop_id` string COMMENT '推广来源id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `shop_detail_id` string COMMENT '推广来源明细id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `shop_detail_name` string COMMENT '推广来源明细名称 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `discount_amount` double COMMENT '优惠金额 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `service_amount` double COMMENT '服务费 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `procedures_amount` double COMMENT '手续费 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `arrival_amount` double COMMENT '到账金额 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `register_pay_duration` int COMMENT '付费周期 （支付日期-注册日期） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `order_sn` int COMMENT '用户在当前下单属于第几次购买 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `normal_price_order_sn` int COMMENT '用户在当前下单属于第几次正价购买 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `channel_normal_price_order_sn` int COMMENT '用户在当前下单渠道属于第几次正价购买 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_sk` int COMMENT '商品代理键 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_name` string COMMENT '商品名 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_stage_subject` string COMMENT '商品【学科-学段-类型】数组 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `sub_good_cnt` int COMMENT '子商品的个数 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_subject_cnt` int COMMENT '学科数 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `sub_good_sk` int COMMENT '子商品代理键 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `kind` string COMMENT '子商品的类型，英文[vip |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `stage_id` int COMMENT '学段id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `stage_name` string COMMENT '学段名 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `subject_id` int COMMENT '学科id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `subject_name` string COMMENT '学科名 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `semester_id` int COMMENT '学期 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `semester_name` string COMMENT '学期名 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_original_amount` double COMMENT '商品原价 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `sub_amount` double COMMENT '子商品实收金额（子订单粒度用此字段） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `ss_order_sn` int COMMENT '用户当前学段学科在当前下单属于第几次购买 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `ss_normal_price_order_sn` int COMMENT '用户当前学段学科在当前下单属于第几次正价购买 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `before_order_last_end_time` timestamp COMMENT '购买订单前权限到期日期 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `end_pay_duration` int COMMENT '用户当前学段学科订单支付日期和权益截止日期差值（天数） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `stage_order_sn` int COMMENT '用户当前学段在当前下单属于第几次购买 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `stage_normal_price_order_sn` int COMMENT '用户当前学段在当前下单属于第几次正价购买 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `user_sk` int COMMENT '用户代理键 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `u_user` string COMMENT '用户id（转化用户量用此字段去重） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `role` string COMMENT '用户角色（详见文件末尾枚举值） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `grade` string COMMENT '用户填写年级 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `mid_stage_name` string COMMENT '中学修正学段（详见文件末尾枚举值） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `gender` string COMMENT '用户性别 male男 female女 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `user_attribution` string COMMENT '用户活跃时归属 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `attribution` string COMMENT 'B/C订单归属 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `city_class` string COMMENT '城市分线 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `province` string COMMENT '省 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `province_code` string COMMENT '省code |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `city` string COMMENT '市 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `city_code` string COMMENT '市code |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `area` string COMMENT '区 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `area_code` string COMMENT '区code |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `school_id` string COMMENT '学校id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `school_sk` int COMMENT '学校sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `school_id1` string COMMENT '学校id1 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `school_sk1` int COMMENT '学校sk1 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `is_test_user` smallint COMMENT '是否测试用户（★必加条件：= 0） |上游：由 ETL 或源表布尔/状态字段映射 |加工：按 ETL 映射为 0/1、true/false 或业务约定值域',
  `is_teach_user` smallint COMMENT '是否教学班用户 |上游：由 ETL 或源表布尔/状态字段映射 |加工：按 ETL 映射为 0/1、true/false 或业务约定值域',
  `is_room_user` smallint COMMENT '是否有班用户 |上游：由 ETL 或源表布尔/状态字段映射 |加工：按 ETL 映射为 0/1、true/false 或业务约定值域',
  `is_new_user` smallint COMMENT '是否新用户 |上游：由 ETL 或源表布尔/状态字段映射 |加工：按 ETL 映射为 0/1、true/false 或业务约定值域',
  `is_telemarketing_user` smallint COMMENT '是否是电销触达 |上游：由 ETL 或源表布尔/状态字段映射 |加工：按 ETL 映射为 0/1、true/false 或业务约定值域',
  `regist_time` timestamp COMMENT '用户注册时间 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `is_parent_telemarketing` smallint COMMENT '是否属于家长电销订单 |上游：由 ETL 或源表布尔/状态字段映射 |加工：按 ETL 映射为 0/1、true/false 或业务约定值域',
  `group` array < string > COMMENT '标签 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_sell_kind` string COMMENT '商品售卖类型 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `sell_from` string COMMENT '商品售卖来源 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `is_pad_price_difference_order` smallint COMMENT '是否体验机补差价订单 |上游：由 ETL 或源表布尔/状态字段映射 |加工：按 ETL 映射为 0/1、true/false 或业务约定值域',
  `light_class_before_sum_amount` int COMMENT '轻课营收之前的金额 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `light_class_sum_amount` int COMMENT '轻课营收加上本次的金额 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `before_sum_amount` int COMMENT '订单之前的金额 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `sum_amount` int COMMENT '订单加上这次的金额 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `user_pay_status_statistics` string COMMENT '付费标签：统计维度口径（详见文件末尾枚举值）⚠️建议改用 business_user_pay_status_* |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `user_pay_status_business` string COMMENT '付费标签：业务维度口径（详见文件末尾枚举值）⚠️建议改用 business_user_pay_status_* |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `business_attribution` string COMMENT '业务群归属：b 端营收、小学网课营收、轻课营收 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `original_amount` double COMMENT '订单原价 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `mid_grade` string COMMENT '中学修正年级（详见文件末尾枚举值） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `status` string COMMENT '当前订单状态（常用筛选：支付成功） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_id` string COMMENT '商品id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `dynamic_diff_price_type` string COMMENT '补差价类型 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_year` string COMMENT '商品时长 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_content` string COMMENT '内容标识 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `xugou_order_kind` string COMMENT '续购订单类型 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `xugou_pre_order_id` string COMMENT '续购前序订单id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `discount_id` string COMMENT '优惠券id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `discount_note` string COMMENT '优惠券note |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `discount_price` double COMMENT '优惠券金额（元） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `special_course_type` string COMMENT '课程包类型 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `business_gmv_attribution` string COMMENT '业务GMV归属划分（★ 统一使用此字段，按服务期优先级判断） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `sync_type` smallint COMMENT '同步方式：1-自动判单，2-申诉, 3-七陌导入, 4-专属链接 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `sync_status` smallint COMMENT '同步状态：1-正常，2-异常 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `model_type` string COMMENT '平板型号 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `order_amount` double COMMENT '订单实收金额（★营收统计用此字段，需先按order_id去重） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `order_first_refund_time` timestamp COMMENT '订单首次退费时间 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
  `sku_amount` double COMMENT 'sku 价格 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `sku_name` string COMMENT 'sku名字 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `procedures_rate` double COMMENT '手续费率 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `workplace_id` int COMMENT '销售职场id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `department_id` int COMMENT '学部id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `regiment_id` int COMMENT '团id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `heads_id` int COMMENT '主管组id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `team_id` int COMMENT '小组id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `worker_id` int COMMENT '坐席id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `worker_name` string COMMENT '坐席名称 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `insurance_category` string COMMENT '保险类别 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `sn` string COMMENT 'pad sn |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `yc_from` string COMMENT '机构名称 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `total_refund_amt` double COMMENT '总退款金额 |上游：结果表累计/滚动字段，来源见对应 ETL 聚合逻辑 |加工：累计/滚动口径，非单日新增',
  `team_ids` array < string > COMMENT '全域业绩归属 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `team_names` array < string > COMMENT '全域业绩归属 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_category` string COMMENT '商品类别 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `platform_id` string COMMENT '平台ID |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `business_id` string COMMENT '商户ID |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `tiktok_author_id` string COMMENT '抖音订单直播主播id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `tiktok_author_name` string COMMENT '抖音订单直播主播名称 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `tiktok_first_author_name` string COMMENT '抖音订单直播主播首次名称 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
  `good_type` string COMMENT '商品类型(已弃用,推荐使用 good_kind_name_level_2) |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `phone` string COMMENT '手机号 ,phone字段可能需要base64解码 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `hire_purchase_num` int COMMENT '分期数 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `interest_subsidy_method` string COMMENT '贴息方式 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `hire_purchase_commission` double COMMENT '分期手续费 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `real_deductible_price` double COMMENT '补差总金额 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `deduct_category` string COMMENT '补差类型 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `business_user_pay_status_statistics` string COMMENT '付费标签：商业化统计维度口径（详见文件末尾枚举值；商业化付费会员拆分为大会员付费、非大会员付费） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `regist_user_allocation` array < string > COMMENT '用户注册当天服务期归属 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `business_user_pay_status_business` string COMMENT '付费标签：商业化业务维度口径 ⭐默认字段（付费分层-业务维度；详见文件末尾枚举值） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `correct_team_names` array < string > COMMENT '修正后业绩归属 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `pad_type` string COMMENT '平板类型 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `live_platform_tag` string COMMENT '直播平台标签 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `actual_deduct_amount` double COMMENT '用户实际的抵扣金额，单位：元 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `max_deduct_amount` double COMMENT '该策略的最高抵扣金额，单位：元 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：含最早/最大/最小等聚合逻辑',
  `grade_stage_name_day` string COMMENT '付费当天年级学段 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `grade_name_month` string COMMENT '付费当月年级 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `stage_name_month` string COMMENT '付费当月学段 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `grade_stage_name_month` string COMMENT '付费当月年级学段 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `user_pay_status_statistics_month` string COMMENT '付费当月首次标签新增(统计日期当天注册的)、付费(统计日期之前买过正价课)、老未(统计日期之前注册的) |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `user_pay_status_business_month` string COMMENT '付费当月首次付费标签 付费用户(统计日期之前买过正价课)、新用户(统计日期30天内注册的)、老用户(统计日期30以前注册的) |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `business_user_pay_status_statistics_month` string COMMENT '付费当月首次付费标签新增(统计日期当天注册的)、大会员付费用户(统计日期之前买过大会员商品)、续费用户(统计日期之前买过正价课)、老未(统计日期之前注册的) |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `business_user_pay_status_business_month` string COMMENT '付费当月首次付费标签大会员付费用户(统计日期之前买过大会员商品)、续费用户(统计日期之前买过正价课)、新用户(统计日期30天内注册的)、老用户(统计日期30以前注册的) |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `grade_name_year` string COMMENT '付费当年年级 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `stage_name_year` string COMMENT '付费当年学段 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `grade_stage_name_year` string COMMENT '付费当年年级学段 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `user_pay_status_statistics_year` string COMMENT '付费当年首次付费标签：新增(统计日期当天注册的)、付费(统计日期之前买过正价课)、老未(统计日期之前注册的) |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `user_pay_status_business_year` string COMMENT '付费当年首次付费标签：付费用户(统计日期之前买过正价课)、新用户(统计日期30天内注册的)、老用户(统计日期30以前注册的) |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `business_user_pay_status_statistics_year` string COMMENT '付费当年首次付费标签： 新增(统计日期当天注册的)、大会员付费用户(统计日期之前买过大会员商品)、续费用户(统计日期之前买过正价课)、老未(统计日期之前注册的) |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `business_user_pay_status_business_year` string COMMENT '付费当年首次付费标签：大会员付费用户(统计日期之前买过大会员商品)、续费用户(统计日期之前买过正价课)、新用户(统计日期30天内注册的)、老用户(统计日期30以前注册的) |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_stage_subject_cnt` int COMMENT '学段学科个数 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `sku_group_good_id` string COMMENT 'sku商品组id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_kind_name_level_1` string COMMENT '商品类目-一级（详见文件末尾枚举值） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_kind_name_level_2` string COMMENT '商品类目-二级（详见文件末尾枚举值） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_kind_name_level_3` string COMMENT '商品类目-三级（详见文件末尾枚举值） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_kind_id_level_1` string COMMENT '商品类目-一级id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_kind_id_level_2` string COMMENT '商品类目-二级id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `good_kind_id_level_3` string COMMENT '商品类目-三级id |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `fix_good_kind_id_level_2` string COMMENT '修正-商品类目-二级id(积木块抵扣「升单商品」专用) |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `fix_good_kind_name_level_2` string COMMENT '修正-商品类目-二级(积木块抵扣「升单商品」专用) |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `is_clue_seat` smallint COMMENT '线索是否在坐席名下 0否 1是 |上游：由 ETL 或源表布尔/状态字段映射 |加工：按 ETL 映射为 0/1、true/false 或业务约定值域',
  `fix_good_year` string COMMENT '修正的商品时长（详见文件末尾枚举值） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `business_good_kind_name_level_1` string COMMENT '策略组修正-商品类目-一级（详见文件末尾枚举值） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `business_good_kind_name_level_2` string COMMENT '策略组修正-商品类目-二级（详见文件末尾枚举值） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `business_good_kind_name_level_3` string COMMENT '策略组修正-商品类目-三级（详见文件末尾枚举值） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `fix_deductible_price` double COMMENT '修正-补差价总金额 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `course_timing_kind` string COMMENT '商品分类标签 到期型/时长型（详见文件末尾枚举值） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `course_group_kind` string COMMENT '商品分组标签 私域主推品/公域主推品（详见文件末尾枚举值） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `strategy_type` string COMMENT '策略类型:20260101上线以后为业务数据，之前按规则清洗（详见文件末尾枚举值） |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `strategy_detail` string COMMENT '策略明细：策略及对应的金额明细 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `userauth_exchange_time` timestamp COMMENT '授权转换时间 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `delay_vip_activation_time` timestamp COMMENT '囤课品激活时间 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `multi_child_refund_time` timestamp COMMENT '多孩策略退差价时间 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `user_strategy_tag_day` string COMMENT '策略用户分层-日 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `big_vip_kind_day` string COMMENT '历史大会员标签-日 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `user_strategy_eligibility_day` string COMMENT '用户策略资格-日 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `user_strategy_tag_month` string COMMENT '策略用户分层-月 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `big_vip_kind_month` string COMMENT '历史大会员标签-月 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `user_strategy_eligibility_month` string COMMENT '用户策略资格-月 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `user_strategy_tag_year` string COMMENT '策略用户分层-年 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `big_vip_kind_year` string COMMENT '历史大会员标签-年 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `user_strategy_eligibility_year` string COMMENT '用户策略资格-年 |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无'
) COMMENT '一笔子订单一条记录' ROW FORMAT SERDE 'org.apache.hadoop.hive.ql.io.orc.OrcSerde' STORED AS INPUTFORMAT 'org.apache.hadoop.hive.ql.io.orc.OrcInputFormat' OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.orc.OrcOutputFormat' LOCATION 'tos://yc-data-platform/user/hive/warehouse/dws.db/topic_order_detail' TBLPROPERTIES (
  'alias' = '订单宽表',
  'bucketing_version' = '2',
  'discover.partitions' = 'true',
  'is_core' = 'true',
  'last_modified_by' = 'finebi',
  'last_modified_time' = '1749699296',
  'spark.sql.create.version' = '3.2.1',
  'transient_lastDdlTime' = '1770064955'
)

-- =====================================================
-- 枚举值
-- =====================================================
--
-- ## status（订单状态）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 支付成功 | 已支付 |
-- | 退款成功 | 已退款 |
-- 来源：谭晨、惠慧
--
-- ## user_pay_status_statistics（付费标签-统计维度口径）⚠️诗华提醒应使用business_user_pay_status_*
--
-- > "新增"以注册当天为界
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 付费 | 购买过任一正价商品用户 |
-- | 新增 | 注册当天未正价付费用户 |
-- | 老未 | 注册非当天未正价付费用户 |
-- | *(空)* | 无用户归属订单 |
-- 来源：谭晨
--
-- ## business_user_pay_status_statistics（付费标签-商业化统计维度口径）
--
-- > 在统计维度口径基础上细分高净值用户
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 高净值用户 | 购买过任一高净值商品用户（大会员、组合品） |
-- | 续费用户 | 购买过任一正价商品且非高净值用户 |
-- | 新增 | 注册当天未正价付费用户 |
-- | 老未 | 注册非当天未正价付费用户 |
-- | *(空)* | 无用户归属订单 |
-- 来源：谭晨、惠慧
--
-- ## user_pay_status_business（付费标签-业务维度口径）⚠️诗华提醒应使用business_user_pay_status_*
--
-- > "新用户"以注册30天为界
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 付费用户 | 购买过任一正价商品用户 |
-- | 新用户 | 注册30天内（≤30天）未正价付费用户 |
-- | 老用户 | 注册30天以上（>30天）未正价付费用户 |
-- | *(空)* | 无用户归属订单 |
-- 来源：谭晨
--
-- ## business_user_pay_status_business（付费标签-商业化业务维度口径）⭐默认字段
--
-- > 在业务维度口径基础上细分高净值用户
-- > 字段选择指南：
-- >   默认/无特殊说明 → business_user_pay_status_business ⭐
-- >   需求明确"新用户=当日注册" → business_user_pay_status_statistics
-- >   不需要区分高净值用户 → user_pay_status_statistics 或 user_pay_status_business
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 高净值用户 | 购买过任一高净值商品用户（大会员、组合品） |
-- | 续费用户 | 购买过任一正价商品且非高净值用户 |
-- | 新用户 | 注册30天内（≤30天）未正价付费用户 |
-- | 老用户 | 注册30天以上（>30天）未正价付费用户 |
-- | *(空)* | 无用户归属订单 |
-- 来源：谭晨、惠慧
--
-- ## mid_stage_name（中学修正学段）
--
-- | 枚举值 | 说明 |
-- |--------|------|
-- | 学龄前 | |
-- | 小学 | |
-- | 初中 | |
-- | 高中 | |
-- | 中职 | |
-- | NULL | 未填写 |
-- 来源：谭晨
--
-- ## mid_grade（中学修正年级）
--
-- | 学段 | 年级枚举值 |
-- |------|-----------|
-- | 学龄前 | 学龄前 |
-- | 小学 | 一年级、二年级、三年级、四年级、五年级、六年级 |
-- | 初中 | 七年级、八年级、九年级 |
-- | 高中 | 高一、高二、高三、十年级 |
-- | 中职 | 职一、职二、职三 |
-- | 其他 | 其他、unavailable、NULL |
--
-- ## role（注册时选择的角色）
--
-- > ⚠️ 不能用于判断是否家长，判断家长身份必须使用 real_identity（仅用户表有）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | student | 学生 |
-- | teacher | 老师 |
-- | parents | 历史小程序注册用户默认给的家长身份 |
-- | youzan | 有赞 |
--
-- ## good_kind_name_level_1（商品一级类目）
--
-- > 商品 2.0 体系（2026-01-01 起生效）
--
-- | 枚举值 | 说明 |
-- |--------|------|
-- | 方案型商品 | 组合商品，主力营收来源 |
-- | 零售商品 | 单课程零售 |
-- | 体验品 | 低价体验产品 |
-- | 研学商品 | 研学相关 |
-- | AI课堂 | AI 课程 |
-- | 其他商品 | 其他 |
--
-- ## good_kind_name_level_2（商品二级类目）
--
-- | 枚举值 | 说明 |
-- |--------|------|
-- | 组合商品 | 主力产品（初中品、高中品、小学品等） |
-- | 同步课 | 零售同步课 |
-- | 培优课 | 零售培优课 |
-- | 同步课加培优课 | 组合 |
-- | 升单后加购 | 学段加购 |
-- | 学习机加购 | 平板加购 |
-- | 一年积木块 | 千元品2.0 |
-- | 拓展课 | 拓展课程 |
-- | 活动定金 | 定金 |
-- | 学习机单售 | 学习机单独售卖 |
-- | 学习方法课 | 学习方法 |
-- | 学前启蒙 | 学前 |
-- | 衔接课 | 衔接 |
-- | 试卷库 | 试卷 |
-- | 研学商品 | 研学 |
-- | 体验版组合商品 | 体验版 |
-- | AI课堂 | AI |
-- | 其他体验品 | 体验品 |
-- | 实物商品 | 周边等 |
-- | 未分类课程商品 | 未分类 |
-- | 其他综合类商品 | 其他 |
-- | 其他辅助学习产品 | 辅助产品 |

--
-- ## fix_good_year（修正的商品时长）
--
-- | 类型 | 枚举值示例 |
-- |------|-----------|
-- | 年型 | 1年、2年、3年、4年、5年、6年、12年 |
-- | 天型 | 0天、1天、7天、30天、31天、93天 |
-- | 到期型 | 2026年01月到期、2027年06月到期、2028年06月到期 |
-- | 特殊 | 小学6年品 |
-- 来源：谭晨
--
-- ## course_timing_kind（商品分类标签）
--
-- | 枚举值 | 说明 |
-- |--------|------|
-- | 到期型 | 固定到期日期 |
-- | 时长型 | 从购买日起算时长 |
-- | NULL | 未分类 |
-- 来源：谭晨
--
-- ## course_group_kind（商品分组标签）
--
-- | 枚举值 | 说明 |
-- |--------|------|
-- | 私域主推品 | 电销主推的组合商品 |
-- | 公域主推品 | 新媒体/其他渠道主推 |
-- | NULL | 未分类 |
-- 来源：谭晨
--
-- ## strategy_type（策略类型）
--
-- > 2026-01-01 起为业务数据，之前按规则清洗
--
-- | 枚举值（部分） | 说明 |
-- |---------------|------|
-- | 多孩策略 | 多孩家庭优惠 |
-- | 高中囤课策略 | 高中囤课 |
-- | 学习机加购策略 | 学习机加购 |
-- | 历史大会员续购策略 | 历史大会员续购 |
-- 来源：谭晨

-- =====================================================
-- 关键枚举补充（来源 biMetadata）
-- =====================================================
--
-- ## 是否类（本表常见值域）
--
-- | 字段 | 值域 | 含义 |
-- |------|------|------|
-- | `is_normal_price` / `is_group_buy` / `is_by_manual` / `is_recalled` / `is_test_user` / `is_teach_user` / `is_room_user` / `is_new_user` / `is_telemarketing_user` / `is_parent_telemarketing` / `is_pad_price_difference_order` / `is_clue_seat` | 1 / 0 | 1=是，0=否 |
--
-- ## 付费分层
--
-- | 字段 | 常见取值 |
-- |------|----------|
-- | user_pay_status_statistics | 新增 / 付费 / 老未 |
-- | user_pay_status_business | 付费用户 / 新用户 / 老用户 |
-- | business_user_pay_status_statistics | 新增 / 高净值用户 / 续费用户 / 老未 |
-- | business_user_pay_status_business | 高净值用户 / 续费用户 / 新用户 / 老用户 |
--
-- ## 订单状态与同步状态
--
-- | 字段 | 常见取值 |
-- |------|----------|
-- | status | 支付成功 / 退款成功 等 |
-- | sync_type | 1 自动判单 / 2 申诉 / 3 七陌导入 / 4 专属链接 等 |
-- | sync_status | 1 正常 / 2 异常 |
--
-- ## 开放集合
--
-- - good_kind_name_level_*、business_good_kind_name_level_*、shop_name、strategy_type、
--   strategy_detail、team_names、worker_name 为开放集合，以线上 distinct 与业务定义为准

-- =====================================================
-- 数据库校验（来源 biMetadata）
-- =====================================================
--
-- - 校验脚本：./scripts/hive-inspect.sh -d dws -t topic_order_detail -a
-- - 一次查库快照：非分区表；元数据行数 114,807,490
