# 问鼎·C 端私域数据趋势看板

这是 NX 独立报表的路线 A 版本：页面读取脱敏 JSON 快照，不在浏览器中查询数仓。

## 生成快照

在 `c-query-cli-lite` 项目根目录执行：

```bash
python3 scripts/key_metrics_dashboard_push.py \
  --date YYYY-MM-DD \
  --engine starrocks \
  --standalone-output independent_reports/c_end_private_metrics \
  --skip-card
```

真实取数只读取本机未提交的 `config.json` 或受管环境变量。数据库账号、密码和令牌不得写入本目录。

## 本地检查

```bash
python3 -m json.tool independent_reports/c_end_private_metrics/monitor.yaml >/dev/null
python3 -m json.tool independent_reports/c_end_private_metrics/public/data/report.json >/dev/null
python3 -m unittest tests.test_key_metrics_dashboard_push tests.test_c_end_private_metrics_report -v
```

确认页面数字与快照一致、数据日期正确、没有敏感字段后，再提交功能分支和 MR。

## Preview 验收

MR 检查通过后打开：

```text
https://wowdata.guanghexinzhi.cn/_preview/c-end-private-metrics/
```

检查电脑和手机显示、日期、核心指标、图表、空数据状态、刷新页面和相对路径资源。Preview 验收通过后才能合并。

## 正式发布

合并到 `main` 后由流水线自动发布：

```text
https://wowdata.guanghexinzhi.cn/c-end-private-metrics/
```

发布后核对页面数据日期和完整 Git SHA。不要通过 SSH 手工覆盖页面。

## 更新与回滚

每次更新都重新生成快照，并走“功能分支 → MR → Preview → 合并”。生产异常时使用 GitLab 的 `rollback_production` 恢复上一版本。
