# C端 query_cli 业务术语

本文件是业务同事和 Agent 查询口径前的术语入口。详细计算方式与表来源见 `glossary/【C端取数】_query_cli.md`。

## 核心对象

| 术语 | 含义 | 主要表 |
|---|---|---|
| 注册用户 | 在指定日期范围内完成注册的 C 端用户 | `aws.user_increase_new_add_day` |
| 注册渠道 | 注册用户对应的一级、二级、三级渠道标签 | `aws.user_increase_channel_label_day` |
| C端活跃用户 | C 端/私域口径下的活跃用户 | `aws.business_active_user_last_14_day` |
| 订单用户 | 在订单表中产生订单行为的用户 | `dws.topic_order_detail` |
| 子订单 | `dws.topic_order_detail` 的明细粒度，一笔主订单可对应多条子订单 | `dws.topic_order_detail` |

## 核心指标

| 术语 | 标准口径 | 注意事项 |
|---|---|---|
| 注册用户数 | `COUNT(DISTINCT u_user)` | 必须限定 `day` 时间范围 |
| 注册用户 LTV | 注册 cohort 在订单窗口内的到账金额 / 注册用户数 | 金额通常使用 `arrival_amount` |
| 活跃用户数 | 对活跃用户字段去重 | `aws.business_active_user_last_14_day` 只代表 C 端/私域活跃 |
| 活跃用户转化率 | `pay_user_cnt / active_user_cnt` | 付费用户必须去重，不能直接累加标记字段 |
| 订单量 | `COUNT(DISTINCT order_id)` | 不能使用 `COUNT(*)` 代表订单量 |
| GMV | 按场景汇总 `sub_amount`、`order_amount` 或 `arrival_amount` | 必须说明金额字段与订单状态 |
| 正价订单 | 满足场景 SQL 中正价条件的订单 | 常见条件为 `original_amount >= 39` |

## 关键维度

| 术语 | 含义 | 常见字段 |
|---|---|---|
| 注册日期 | 用户完成注册的日期 | `day`、`regist_day` |
| 订单日期 | 订单支付日期 | `paid_time_sk` |
| 端口 | 用户注册或活跃来源端 | `u_from`、`os`、`client_os` |
| 渠道一级标签 | 注册渠道一级分类 | `regist_channel_label1` |
| 渠道二级标签 | 注册渠道二级分类 | `regist_channel_label2` |
| 业务 GMV 归属 | 订单 GMV 业务归属 | `business_gmv_attribution` |
| 商品 2.0 类目 | 商品类目体系 | `good_kind_name_level_1`、`good_kind_name_level_2` |
| 策略组商品类目 | 策略组口径商品类目 | `business_good_kind_name_level_1` |

## 易混淆术语

| 易混点 | 正确理解 |
|---|---|
| C端活跃 vs 全公司活跃 | `aws.business_active_user_last_14_day` 只代表 C 端/私域活跃，不代表全公司活跃 |
| 订单量 vs 子订单行数 | 订单量必须按 `order_id` 去重，子订单行数不能直接当订单量 |
| 商品 2.0 类目 vs 策略组商品类目 | 两套类目字段不能混用，输出时必须明确字段名 |
| LTV 金额 vs GMV | LTV 通常看注册 cohort 的到账金额，GMV 按订单或商品归属汇总 |
| 支付成功 vs 退款成功 | 不同场景包含的订单状态不同，必须以场景 SQL 和口径说明为准 |

## Agent 使用要求

当用户提到上述术语时，Agent 应先映射到对应场景，再用 `c-query-cli ask "<用户问题>" --dry-run` 生成 DSL 和 SQL。如果用户没有提供时间范围，必须先反问。
