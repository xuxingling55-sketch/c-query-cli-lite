# 公共规则

## SQL 生成规则

- 只允许生成 `SELECT` 或 `WITH ... SELECT` 查询。
- 禁止 `DROP`、`DELETE`、`UPDATE`、`INSERT`、`ALTER`、`CREATE`、`TRUNCATE`、`REPLACE`、`MERGE`、`GRANT`、`REVOKE`。
- 必须包含明确的时间或分区过滤，常见字段包括 `dt`、`p_date`、`pt`、`day`、`paid_time_sk`。
- 使用 `JOIN` 时必须显式写明 `JOIN` 类型和 `ON` 条件。
- 禁止 `select *`，必须列出业务方需要的字段。
- 默认 `LIMIT 10000`，不允许超过 `10000`。
- 输出字段建议加中文别名，方便业务同事查看 Excel。

## 查询引擎规则

- 优先使用 `StarRocks`。
- 超过 15 分钟或 StarRocks 超时后，自动切换到 `SparkSQL`。
- 真实账号密码只写入本机 `config.json`，不要提交到 Git。

## 需求澄清规则

如果业务方没有说清楚以下内容，AI 必须先追问：

- 时间范围。
- 指标口径。
- 是否需要分渠道、分端、分商品类目或分活跃/付费分层。
- “转化”具体指注册转化、渠道订单转化还是活跃用户转化。
