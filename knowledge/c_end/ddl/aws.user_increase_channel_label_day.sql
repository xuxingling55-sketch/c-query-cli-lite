-- =====================================================
-- 用户增长渠道标签日表 aws.user_increase_channel_label_day
-- =====================================================
-- 【表粒度】
--   每个用户一条记录；分区 day（int，yyyyMMdd）；T+1
--
-- 【使用场景】
--   - 查看2025年之后注册用户的渠道归因标签（一级/二级/三级）
--   - 区分投放 vs 免费用户来源
--
-- 【业务定位】
--   根据 apk/api 点击归因逻辑，以**优先 api 归因、再 apk 归因**的方式对注册量打渠道标签。
--   上游数据来自 aws.user_increase_new_add_day。
--
-- 【统计口径】
--   查渠道标签（示例）：
--     SELECT u_user
--          , regist_channel_label1 AS `一级标签`
--          , regist_channel_label2 AS `二级标签`
--          , regist_channel_label3 AS `三级标签`
--          , apk_channel AS `apk渠道id`
--          , api_channel AS `api渠道id`
--     FROM aws.user_increase_channel_label_day
--     WHERE regist_timestamp BETWEEN '${start}' AND '${end}'
--
-- 【数据来源】
--   aws.user_increase_new_add_day
--
-- 【常用关联】
--   本表.u_user = dw.dim_user.u_user / aws.user_increase_new_add_day.u_user
--
-- 【常用筛选条件】
--   ★必加：
--   - regist_timestamp BETWEEN '${start}' AND '${end}'（按注册时间筛选）
-- =====================================================

CREATE TABLE aws.user_increase_channel_label_day (
    regist_timestamp TIMESTAMP COMMENT '用户注册时间',
    month STRING COMMENT '月份',
    u_user STRING COMMENT '用户id',
    stage STRING COMMENT '注册时的学段',
    regist_channel_label1 STRING COMMENT '一级标签（详见文件末尾枚举值）',
    regist_channel_label2 STRING COMMENT '二级标签（详见文件末尾枚举值）',
    regist_channel_label3 STRING COMMENT '三级标签',
    channel STRING COMMENT '注册渠道',
    user_attribution STRING COMMENT '用户归属',
    apk_channel STRING COMMENT 'apk渠道id',
    api_channel STRING COMMENT 'api渠道id',
    day INT COMMENT '分区日期 yyyyMMdd'
)
USING orc
PARTITIONED BY (day)
COMMENT '用户增长的渠道标签日表'
TBLPROPERTIES (
    'alias' = '用户增长的渠道标签日表',
    'bucketing_version' = '2',
    'transient_lastDdlTime' = '1766479225'
);

-- =====================================================
-- 枚举值
-- =====================================================
--
-- ## regist_channel_label1（一级标签）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 投放 | 投放来源用户 |
-- | 免费 | 免费来源用户 |
-- | 其他 | 其他来源 |
--
-- ## regist_channel_label2（二级标签 —— 按一级分组）
--
-- > 当 regist_channel_label1 = '投放' 时：
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | cpa | CPA 渠道 |
-- | 信息流 | 信息流投放 |
-- | 厂商渠道 | 厂商渠道投放 |
-- | 学习机 | 学习机渠道 |
-- | 其他 | 其他投放 |
--
-- > 当 regist_channel_label1 = '免费' 时：
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 厂商渠道 | 免费厂商渠道 |
-- | 其他 | 其他免费来源 |
-- | 以上 | 以上分类汇总 |
