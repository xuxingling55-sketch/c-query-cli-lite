# 商品知识库（可迁移版）

版本：2026-07-09  
适用对象：C 端商业化、APP、电销、私域活跃、商品结构、转化效率、营收归因分析  
迁移方式：可整文件复制到其他机器人的知识库。使用时优先遵循本文口径；如果业务方临时指定了不同口径，必须在结论里明示差异。

## 1. 最重要的总原则

1. 商品分析默认使用订单明细表 `dws.topic_order_detail`。
2. 活跃、活跃转化率、活跃 ARPU、活跃客单价默认使用活跃表 `aws.business_active_user_last_14_day`。
3. 如果把商品订单和活跃用户放在一起看，必须先圈定活跃用户池，再统计活跃池内用户的商品订单。
4. 商品营收默认看正价 GMV：`sub_amount`，并默认筛选 `is_test_user = 0`、`original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')`。
5. 订单表是子订单粒度，订单量必须用 `COUNT(DISTINCT order_id)`，不能用 `COUNT(*)`。
6. 商品类目优先使用 `business_good_kind_name_level_1/2/3`，这是策略组修正后的业务口径；`good_name` 只作为补充识别，不作为首选口径。

## 2. 默认数据表

### 2.1 订单明细表

表名：`dws.topic_order_detail`

用途：

- 看商品营收、GMV、订单量、付费用户、商品结构。
- 判断用户是否买过某类商品。
- 分析组合品、零售商品、续购、家庭包、从小学、定金、蓄水品等。

核心字段：

| 字段 | 用途 |
| --- | --- |
| `u_user` | 用户 ID，统计付费用户时用它去重 |
| `order_id` | 订单 ID，统计订单量时用它去重 |
| `paid_time_sk` | 支付日期，常见格式为 `yyyymmdd` |
| `paid_time` | 支付时间，做“支付先后顺序”时使用 |
| `sub_amount` | 子商品实收金额，商品拆解营收默认用这个 |
| `order_amount` | 主订单实收金额，如果使用它，必须先按 `order_id` 去重 |
| `original_amount` | 订单原价，正价筛选常用 `original_amount >= 39` |
| `arrival_amount` | 到账金额，只在新增注册 LTV 等到账口径下使用 |
| `status` | 订单状态，营收默认不筛；只有明确要支付成功/退款/到账时才筛 |
| `is_test_user` | 测试用户标识，订单营收默认排除测试用户 |
| `business_gmv_attribution` | 业务 GMV 归属，商业化私域默认看 `电销` 和 `商业化` |
| `business_good_kind_name_level_1` | 策略组一级商品类目 |
| `business_good_kind_name_level_2` | 策略组二级商品类目 |
| `business_good_kind_name_level_3` | 策略组三级商品类目 |
| `good_kind_name_level_1/2/3` | 商品 2.0 类目，非首选，但可辅助排查 |
| `good_id` | 商品 ID |
| `sku_group_good_id` | SKU 组商品 ID，如表中可用，商品 ID 精准匹配优先考虑它 |
| `good_name` | 商品名称，适合辅助模糊识别 |
| `sku_name` | SKU 名称 |
| `good_year` | 商品时长 |
| `good_content` | 商品内容标识 |
| `special_course_type` | 课程包类型 |
| `is_pad_price_difference_order` | 学习机/平板补差价订单标识 |
| `model_type` | 平板型号 |
| `pad_type` | 平板类型，如表中可用可用于学习机分析 |

### 2.2 活跃表

表名：`aws.business_active_user_last_14_day`

用途：

- 看 C 端/私域活跃用户。
- 看活跃用户转化率、活跃 ARPU、活跃客单价。
- 做用户分层、学段分层、活跃池内商品转化分析。

核心字段：

| 字段 | 用途 |
| --- | --- |
| `day` | 活跃日期 |
| `u_user` | 用户 ID |
| `user_sk` | 用户代理键 |
| `grade_name_month` | 本月第一次活跃时年级 |
| `stage_name_month` | 本月第一次活跃时学段 |
| `business_user_pay_status_statistics_month` | 统计维度用户分层，常用于新增、老未、续费、高净值 |
| `business_user_pay_status_business_month` | 业务维度用户分层 |
| `normal_price_amount` | 活跃口径正价营收 |
| `normal_price_user_sk` | 活跃口径正价付费用户 |
| `business_gmv_attribution` | 活跃口径营收归属 |
| `team_names` | 服务期/业绩归属，判断服务期营收时可用 |

禁用规则：

- 不要用无 `business_` 前缀的 `user_pay_status_*` 字段作为默认用户分层。
- 不要用订单表直接替代活跃表计算整体活跃 ARPU。
- 不要用 `dws.topic_user_active_detail_day` 直接作为活跃人数分母。

## 3. 渠道和营收归属

`business_gmv_attribution` 是订单和活跃营收归属的核心字段。

常见解释：

| 取值 | 对外表达 |
| --- | --- |
| `商业化` | APP 渠道 |
| `电销` | 电销渠道 |
| `商业化-电商` | 电商渠道，默认不放入商业化私域 GMV，除非业务方明确要求 |
| `新媒体视频` | 新媒体视频渠道 |
| `新媒体变现` | 新媒体变现渠道 |
| `体验营` | 体验营 |
| `入校` | 入校 |

默认私域/商业化营收只看：

```sql
business_gmv_attribution IN ('电销','商业化')
```

如果要看全公司或渠道大盘，可以显式加入 `商业化-电商`、`新媒体视频` 等渠道，并在结论里写清楚口径变化。

## 4. 商品分类口径

### 4.1 组合品

定义：

```sql
business_good_kind_name_level_1 = '组合品'
```

用途：

- 方案型商品、主力正价商品分析。
- 组合品转化率、组合品客单价、组合品 ARPU、组合品营收贡献。
- 学段 × 用户分层下的核心承接效率分析。

组合品常见指标：

- 组合品付费用户：活跃池中购买过组合品的去重用户。
- 组合品转化率：组合品付费用户 / 活跃用户。
- 组合品营收：组合品订单 `SUM(sub_amount)`。
- 组合品客单价：组合品营收 / 组合品付费用户。
- 组合品 ARPU：组合品营收 / 活跃用户。

### 4.2 零售商品

定义：

```sql
business_good_kind_name_level_1 = '零售商品'
```

用途：

- 低门槛商品、货架承接、非组合品承接分析。
- 2026 年暑促分析中，零售商品转化下滑和 198 商品取消相关，是新增、老未、小低承接变弱的重要线索。

注意：

- 零售商品 ARPU 如果要和整体活跃 ARPU 同看，必须保证订单用户在活跃池内。
- 不要用全量订单用户直接除以活跃用户，否则会和整体 ARPU 对不齐。

### 4.3 续购

定义：

```sql
business_good_kind_name_level_1 = '续购'
```

用途：

- 续费用户商品承接。
- 去年同期对比时，部分场景需要把 `组合品 + 续购` 一起看，尤其是高净值用户、续费用户、历史大会员相关分析。

组合品 + 续购口径：

```sql
business_good_kind_name_level_1 IN ('组合品','续购')
```

### 4.4 家庭包

定义：

```sql
business_good_kind_name_level_3 = '小初高品'
```

订单占比口径：

- 分子：家庭包订单量。
- 分母：组合品订单量。

SQL 条件：

```sql
-- 分子
business_good_kind_name_level_3 = '小初高品'

-- 分母
business_good_kind_name_level_1 = '组合品'
```

解释口径：

- 家庭包属于组合品里的多学段/多孩子策略承接。
- 看贡献时同时看订单占比、营收占比、客单价变化，避免只看订单数。

### 4.5 从小学

定义：

- 分子：`小学品加拓展`
- 分母：`小学品 + 小学品加拓展`
- 营收：要包含单科部分，不能只看组合包壳子的金额。

SQL 条件：

```sql
-- 分子
business_good_kind_name_level_3 = '小学品加拓展'

-- 分母
business_good_kind_name_level_3 IN ('小学品','小学品加拓展')
```

解释口径：

- 从小学用于判断小学系列产品结构升级。
- 分析时至少同时看订单占比、营收占比、客单价。

### 4.6 蓄水品

业务定义：

- 蓄水量口径：在指定蓄水周期购买“同步课 + 培优课”流量品的用户。
- 2026 年暑促常用蓄水周期：5 月 22 日至 6 月 30 日。
- 用户必须去重。

转大口径：

1. 先圈购买过蓄水品的用户。
2. 转大支付时间必须不早于蓄水品支付时间。
3. 只要用户买过蓄水品，该用户之后所有转大订单都算转大营收。
4. 累计转大要包含 5 月、6 月、7 月三个月的转大数据。
5. 7 月累计转大只统计 7 月内的转大订单。

历史卡片口径示例：

```text
蓄水量
蓄水用户：16,550人
累计转大：1,415人 / 8.55% / ¥470.63万
7月累计转大：799人 / 4.83% / ¥233.43万
```

去年对比：

- 今年：5 月 22 日至 6 月 30 日买过蓄水品，在 7 月活跃后付款的转化。
- 去年：5 月 22 日至 6 月 30 日买过蓄水品和 198 商品，在 7 月活跃后付款的转化。

注意：

- 不能只看 7 月转大，累计转大需要包括 5、6、7 月。
- 不能把转大支付时间早于蓄水支付时间的订单算进去。
- 如果用商品名称识别蓄水品，必须复核商品清单，不能只靠模糊匹配。

### 4.7 定金

分析目标：

- 买定金的都是什么用户。
- 定金用户付尾款时买了什么商品。
- 定金贡献了多少营收，与去年差异是什么。

核心口径：

1. 用户分层必须使用“购买定金时”的标签，不要用后置标签。
2. 付尾款商品要按尾款订单的商品类目拆解。
3. 定金贡献可以拆成定金订单、尾款订单、定金用户后续订单，具体看业务问题。

常见用户分层：

- 新增
- 老未
- 续费
- 高净值
- 高净值细分层

### 4.8 198 商品

业务含义：

- 198 属于低门槛承接商品。
- 2026 年货架变化中，取消 198 商品是零售商品转化率下滑的重要原因之一。
- 对续费/蓄水对比时，去年同期常需要把 198 和蓄水品放在同一低门槛蓄水口径里看。

分析注意：

- 如果今年没有 198，不能直接拿今年蓄水品和去年蓄水品单独对比。
- 更合理的去年对照是“蓄水品 + 198”。

### 4.9 平板/学习机加购

常用字段：

- `is_pad_price_difference_order`
- `model_type`
- `pad_type`
- `sku_name`
- `good_name`

分析方式：

- 看平板加购订单占比。
- 看平板加购客单价。
- 看非平板订单客单价。
- 判断客单价提升到底来自平板加购比例变化，还是组合品本体价格提升。

历史判断：

- 在 2026 年暑促首周分析中，平板加购客单价较高，但订单占比下降，所以不是组合品客单价提升的主因。

## 5. 用户分层和学段

### 5.1 用户分层

活跃分析默认使用：

```sql
business_user_pay_status_statistics_month
```

常见分层：

- 新增
- 老未
- 续费用户
- 高净值用户
- 汇总

注意：

- 看定金用户时，要用购买定金当时的用户标签。
- 看续费用户转化时，如业务方要求，可以单独拆蓄水品用户和非蓄水品用户。
- 如果要排除定金用户，必须明确写出排除条件；默认不要擅自排除。

### 5.2 学段

常用年级归类：

| 学段 | 年级 |
| --- | --- |
| 小低 | 一年级、二年级、三年级 |
| 小高 | 四年级、五年级、六年级 |
| 初中 | 七年级、八年级、九年级 |
| 高中 | 高一、高二、高三 |

活跃分析建议用 `grade_name_month` 做年级归类。订单分析可用订单上的年级字段辅助，但如果要和活跃池对齐，应以活跃池年级为准。

## 6. 核心指标计算

### 6.1 商品营收

默认：

```sql
SUM(sub_amount)
```

默认筛选：

```sql
u_user IS NOT NULL
AND is_test_user = 0
AND original_amount >= 39
AND business_gmv_attribution IN ('电销','商业化')
```

### 6.2 商品订单量

```sql
COUNT(DISTINCT order_id)
```

### 6.3 商品付费用户

```sql
COUNT(DISTINCT u_user)
```

### 6.4 活跃用户数

先按用户去重，再统计：

```sql
COUNT(DISTINCT u_user)
```

如果同一用户一天多行或一个月多行，必须先做用户级去重。

### 6.5 整体活跃 ARPU

默认使用活跃表：

```sql
SUM(normal_price_amount) / COUNT(DISTINCT u_user)
```

不要用订单表商品拆解金额直接替代整体活跃 ARPU。

### 6.6 商品 ARPU

当商品 ARPU 要和活跃指标同表展示时：

```text
商品 ARPU = 活跃池内该商品营收 / 活跃用户数
```

关键限制：

- 有订单的用户必须在活跃池里。
- 商品订单日期必须在分析周期内。
- 商品订单筛选要和整体营收口径尽量一致。
- 组合品 ARPU + 零售商品 ARPU 通常应小于或等于整体 ARPU；如果超过，优先检查是否混用了订单口径和活跃口径，或是否纳入了活跃池外订单。

### 6.7 商品转化率

```text
商品转化率 = 活跃池内购买该商品的去重用户数 / 活跃用户数
```

例：

```text
组合品转化率 = 活跃池内组合品付费用户 / 活跃用户
零售商品转化率 = 活跃池内零售商品付费用户 / 活跃用户
组合品 + 续购转化率 = 活跃池内购买组合品或续购的用户 / 活跃用户
```

### 6.8 商品客单价

```text
商品客单价 = 商品营收 / 商品付费用户
```

注意：

- 客单价按付费用户，不按订单量。
- 如果业务明确要订单客单价，才使用 `商品营收 / 订单量`，并在结论里说明。

### 6.9 同比变化

建议同时输出：

- 今年
- 去年
- 绝对变化
- 相对变化

转化率要特别看相对变化，因为不同分母下只看百分点容易低估差异。

```text
绝对变化 = 今年 - 去年
相对变化 = (今年 - 去年) / 去年
```

## 7. 可复用 SQL 模板

### 7.1 商品营收和订单结构

```sql
SELECT
    business_good_kind_name_level_1,
    business_good_kind_name_level_3,
    COUNT(DISTINCT order_id) AS order_cnt,
    COUNT(DISTINCT u_user) AS pay_user_cnt,
    SUM(sub_amount) AS gmv
FROM dws.topic_order_detail
WHERE paid_time_sk BETWEEN ${start_day} AND ${end_day}
  AND u_user IS NOT NULL
  AND is_test_user = 0
  AND original_amount >= 39
  AND business_gmv_attribution IN ('电销','商业化')
GROUP BY 1, 2
ORDER BY gmv DESC;
```

### 7.2 活跃池内商品转化

```sql
WITH active_pool AS (
    SELECT DISTINCT
        u_user
    FROM aws.business_active_user_last_14_day
    WHERE day BETWEEN ${start_day} AND ${end_day}
      AND u_user IS NOT NULL
),
orders AS (
    SELECT
        o.u_user,
        o.business_good_kind_name_level_1,
        COUNT(DISTINCT o.order_id) AS order_cnt,
        SUM(o.sub_amount) AS gmv
    FROM dws.topic_order_detail o
    JOIN active_pool a
      ON o.u_user = a.u_user
    WHERE o.paid_time_sk BETWEEN ${start_day} AND ${end_day}
      AND o.u_user IS NOT NULL
      AND o.is_test_user = 0
      AND o.original_amount >= 39
      AND o.business_gmv_attribution IN ('电销','商业化')
    GROUP BY 1, 2
)
SELECT
    business_good_kind_name_level_1,
    COUNT(DISTINCT u_user) AS pay_user_cnt,
    SUM(order_cnt) AS order_cnt,
    SUM(gmv) AS gmv,
    COUNT(DISTINCT u_user) / NULLIF((SELECT COUNT(*) FROM active_pool), 0) AS conversion_rate,
    SUM(gmv) / NULLIF(COUNT(DISTINCT u_user), 0) AS aov,
    SUM(gmv) / NULLIF((SELECT COUNT(*) FROM active_pool), 0) AS arpu
FROM orders
GROUP BY 1;
```

### 7.3 学段 × 用户分层 × 商品表现

```sql
WITH active_pool AS (
    SELECT DISTINCT
        u_user,
        CASE
            WHEN grade_name_month IN ('一年级','二年级','三年级') THEN '小低'
            WHEN grade_name_month IN ('四年级','五年级','六年级') THEN '小高'
            WHEN grade_name_month IN ('七年级','八年级','九年级') THEN '初中'
            WHEN grade_name_month IN ('高一','高二','高三') THEN '高中'
            ELSE '其他'
        END AS stage_group,
        business_user_pay_status_statistics_month AS user_segment
    FROM aws.business_active_user_last_14_day
    WHERE day BETWEEN ${start_day} AND ${end_day}
      AND u_user IS NOT NULL
),
product_orders AS (
    SELECT
        o.u_user,
        SUM(CASE WHEN o.business_good_kind_name_level_1 = '组合品' THEN o.sub_amount ELSE 0 END) AS combo_gmv,
        COUNT(DISTINCT CASE WHEN o.business_good_kind_name_level_1 = '组合品' THEN o.order_id END) AS combo_order_cnt
    FROM dws.topic_order_detail o
    JOIN active_pool a
      ON o.u_user = a.u_user
    WHERE o.paid_time_sk BETWEEN ${start_day} AND ${end_day}
      AND o.is_test_user = 0
      AND o.original_amount >= 39
      AND o.business_gmv_attribution IN ('电销','商业化')
    GROUP BY 1
)
SELECT
    a.stage_group,
    a.user_segment,
    COUNT(DISTINCT a.u_user) AS active_user_cnt,
    COUNT(DISTINCT CASE WHEN p.combo_gmv > 0 THEN a.u_user END) AS combo_pay_user_cnt,
    SUM(p.combo_gmv) AS combo_gmv,
    COUNT(DISTINCT CASE WHEN p.combo_gmv > 0 THEN a.u_user END)
        / NULLIF(COUNT(DISTINCT a.u_user), 0) AS combo_conversion_rate,
    SUM(p.combo_gmv)
        / NULLIF(COUNT(DISTINCT CASE WHEN p.combo_gmv > 0 THEN a.u_user END), 0) AS combo_aov,
    SUM(p.combo_gmv)
        / NULLIF(COUNT(DISTINCT a.u_user), 0) AS combo_arpu
FROM active_pool a
LEFT JOIN product_orders p
  ON a.u_user = p.u_user
GROUP BY 1, 2;
```

### 7.4 家庭包订单占比

```sql
SELECT
    COUNT(DISTINCT CASE
        WHEN business_good_kind_name_level_3 = '小初高品'
        THEN order_id
    END) AS family_order_cnt,
    COUNT(DISTINCT CASE
        WHEN business_good_kind_name_level_1 = '组合品'
        THEN order_id
    END) AS combo_order_cnt,
    COUNT(DISTINCT CASE
        WHEN business_good_kind_name_level_3 = '小初高品'
        THEN order_id
    END) / NULLIF(COUNT(DISTINCT CASE
        WHEN business_good_kind_name_level_1 = '组合品'
        THEN order_id
    END), 0) AS family_order_ratio,
    SUM(CASE
        WHEN business_good_kind_name_level_3 = '小初高品'
        THEN sub_amount ELSE 0
    END) AS family_gmv,
    SUM(CASE
        WHEN business_good_kind_name_level_1 = '组合品'
        THEN sub_amount ELSE 0
    END) AS combo_gmv
FROM dws.topic_order_detail
WHERE paid_time_sk BETWEEN ${start_day} AND ${end_day}
  AND u_user IS NOT NULL
  AND is_test_user = 0
  AND original_amount >= 39
  AND business_gmv_attribution IN ('电销','商业化');
```

### 7.5 从小学订单占比

```sql
SELECT
    COUNT(DISTINCT CASE
        WHEN business_good_kind_name_level_3 = '小学品加拓展'
        THEN order_id
    END) AS extension_order_cnt,
    COUNT(DISTINCT CASE
        WHEN business_good_kind_name_level_3 IN ('小学品','小学品加拓展')
        THEN order_id
    END) AS primary_series_order_cnt,
    COUNT(DISTINCT CASE
        WHEN business_good_kind_name_level_3 = '小学品加拓展'
        THEN order_id
    END) / NULLIF(COUNT(DISTINCT CASE
        WHEN business_good_kind_name_level_3 IN ('小学品','小学品加拓展')
        THEN order_id
    END), 0) AS extension_order_ratio,
    SUM(CASE
        WHEN business_good_kind_name_level_3 = '小学品加拓展'
        THEN sub_amount ELSE 0
    END) AS extension_gmv,
    SUM(CASE
        WHEN business_good_kind_name_level_3 IN ('小学品','小学品加拓展')
        THEN sub_amount ELSE 0
    END) AS primary_series_gmv
FROM dws.topic_order_detail
WHERE paid_time_sk BETWEEN ${start_day} AND ${end_day}
  AND u_user IS NOT NULL
  AND is_test_user = 0
  AND original_amount >= 39
  AND business_gmv_attribution IN ('电销','商业化');
```

## 8. 典型分析框架

### 8.1 解释 ARPU 增长

不要直接说“ARPU 提升”。应按这个顺序解释：

1. 活跃用户规模怎么变。
2. 付费用户规模怎么变。
3. 整体转化率怎么变。
4. 客单价怎么变。
5. 再定位 ARPU 是由转化率拉动，还是客单价拉动。
6. 最后拆到商品结构：组合品、零售商品、续购、定金、家庭包、平板等。

表达模板：

```text
ARPU 同比提升，主要不是因为活跃规模增加，而是商品结构和组合品承接变化带来的。
拆开看，组合品转化率/客单价变化贡献了主要增量；零售商品转化率下滑，对新增和老未的低门槛承接形成拖累。
```

### 8.2 判断商品结构变化

至少看四层：

1. 一级类目：组合品、零售商品、续购。
2. 三级类目：家庭包、小学品、小学品加拓展、小初高品等。
3. 策略商品：定金、蓄水品、198、平板加购。
4. 用户层：新增、老未、续费、高净值。

### 8.3 做营收归因

建议拆三类贡献：

1. 商品层：组合品、零售商品、续购、定金、蓄水、家庭包、平板。
2. 用户层：新增、老未、续费、高净值。
3. 渠道层：APP、电销、新媒体视频、电商等。

分析时优先输出：

- 营收金额。
- 营收占比。
- 订单占比。
- 转化率。
- 客单价。
- ARPU。
- 去年同期。
- 同比绝对变化和相对变化。

## 9. 近期已验证的业务结论

这些是历史分析结论，不是永久规则。迁移到其他机器人后，可作为分析假设，但不要不取数就当作最新事实。

### 9.1 2026 年暑促首周，小低组合品转化低的核心原因

周期：2026 年 7 月 1 日至 7 月 7 日，常见对比为 2025 年同期。

结论：

- 小低营收下降不只是私域问题，新媒体视频和 APP 也明显下滑。
- 小低组合品转化率下降，是营收下降的核心原因之一。
- 电销线索外呼深度不是小低独有短板；小低与小高的拨打深度差异不大。
- 小低销售沟通中并不是完全没讲产品，而是对低年级家长的“先试试、适不适合、孩子能不能坚持、买大包是否值得”的顾虑承接不足。
- 竞品不是小低未转化的主因。未买用户明确提到竞品/线下替代的比例很低。
- 198 等低门槛承接商品取消后，零售商品转化下滑，影响了新增、老未、小低用户的前置承接。

关键数据摘录：

- 小低组合品转化率：0.683% 降至 0.524%，相对下降 23.28%。
- 小低组合品营收：327.6 万降至 284.9 万，下降 13.03%。
- 新媒体视频小低 GMV：353.6 万降至 202.5 万，下降 42.7%。
- APP 小低 GMV：90.7 万降至 45.9 万，下降 49.4%。
- 电销小低 GMV：324.4 万至 324.0 万，基本持平。
- 电商小低 GMV：17.0 万升至 21.7 万；但订单数和付费用户数下降，所以不能简单说电商营收下滑。

### 9.2 小低未转化的销售侧原因

样本：小低未买且有沟通用户。

用户明确表达的主要原因：

- 想先试试、想从低门槛开始。
- 价格或组合包决策压力。
- 对产品形式、使用方式、课程效果有疑问。
- 低年级适配顾虑，例如孩子太小、坐不住、是否适合。
- 已有课程或替代方案。
- 竞品/线下机构提及比例低，不是主因。

销售侧问题：

- 销售推进动作不少，但很多沟通过早进入大包、优惠、活动截止。
- 对低年级家长需要的风险解除不足。
- 对“为什么现在要买、为什么适合低年级、如果孩子坚持不了怎么办”的解释不够。

### 9.3 续费用户和蓄水品

分析续费用户时，要拆：

1. 买过蓄水品的续费用户。
2. 没买过蓄水品的续费用户。

原因：

- 买过蓄水品的用户，通常组合品转化率更高。
- 没买过蓄水品的续费用户占比和转化变化，会显著影响续费整体转化率。
- 对比去年时，去年低门槛口径应包含蓄水品和 198。

### 9.4 高净值用户

高净值分析不要只看汇总，要拆：

- 学段。
- 高净值细分层。
- 整体商品。
- 组合品 + 续购。
- 营收、转化率、客单价、ARPU。
- 去年同期和同比变化。

特别注意：

- 如果整体客单价上涨，但组合品客单价下降，增长可能来自非组合品、续购、平板、定金尾款或其他高客单商品。
- 去年数据中要把 `business_good_kind_name_level_1 = '续购'` 和组合品一起看，避免低估历史大会员/续购贡献。

## 10. 常见坑

1. 组合品 ARPU + 零售商品 ARPU 超过整体 ARPU：通常是口径混用。检查是否订单用户不在活跃池、渠道筛选不一致、金额字段不一致。
2. 用 `COUNT(*)` 当订单量：错误。订单表是子订单粒度。
3. 用 `order_amount` 直接求和：容易重复。商品拆解默认用 `sub_amount`。
4. 活跃 ARPU 用订单表算：容易和看板不齐。整体活跃 ARPU 默认用活跃表 `normal_price_amount`。
5. 商品分析混用 `good_kind_*` 和 `business_good_kind_*`：默认使用 `business_good_kind_*`。
6. 默认筛 `status = '支付成功'`：不建议。营收默认不筛订单状态；到账或支付成功专题才筛。
7. 新增注册 LTV 套用商业化 GMV 口径：错误。新增注册 LTV 用 `arrival_amount` 和订单状态 `支付成功/退款成功`。
8. 看蓄水转大时忽略支付先后：错误。转大支付时间必须不早于蓄水支付时间。
9. 看去年蓄水对比时漏掉 198：容易造成去年低门槛承接低估。
10. 说“电商也在跌”前要拆营收、订单数、付费用户。可能营收涨、订单和用户跌。

## 11. 迁移给其他机器人时的使用说明

建议把本文作为“商品分析优先知识库”，并给机器人以下执行规则：

1. 用户问商品、营收、GMV、订单、组合品、零售商品、续购、定金、蓄水、家庭包、从小学时，优先查本文。
2. 用户问活跃、转化率、ARPU、客单价时，先判断是不是活跃口径；如果是，优先用活跃表。
3. 用户要求“和第一部分对齐”“和看板对齐”时，优先使用活跃表口径，不要擅自改成订单表口径。
4. 用户要求商品结构归因时，订单表可以用，但必须说明商品 ARPU 是活跃池内商品订单营收除以活跃用户。
5. 每次输出同比结论时，尽量同时给今年、去年、绝对变化、相对变化。
6. 所有临时业务口径变更都要写在结果前面，避免后续文档口径混乱。

## 12. 本知识库来源

本知识库来自以下本地资料和已验证分析：

- `knowledge/c_end/glossary.md`
- `knowledge/c_end/ddl/dws.topic_order_detail.sql`
- `knowledge/c_end/ddl/aws.business_active_user_last_14_day.sql`
- `scripts/key_metrics_dashboard_push.py`
- `reports/20260708_xiaodi_revenue_decline_analysis.md`
- `reports/20260709_xiaodi_sales_comms_conversion_analysis.md`
- `reports/20260709_xiaodi_combo_conversion_revenue_attribution.md`
- 2026 年 7 月围绕“组合品、零售商品、定金、蓄水、家庭包、从小学、高净值、小低转化”的多轮口径校验

