# naive-fin-data
朴实无华的金融数据项目

## 功能
- 使用 `yfinance` 抓取 A 股与港股历史行情（降低 AkShare 行情端点波动影响）
- 使用 `akshare` 获取 A 股与港股股票代码列表
- A 股与港股分别提供单标的抓取和全量抓取函数
- 全量抓取支持周期参数：`1m,5m,15m,30m,60m,1d`
- 数据落盘路径：`data/{type}/{market}/{code}/{period}/{yyyyMMdd}.parquet`
- 行情 parquet 列名归一化为英文：`timestamp,open,high,low,close,adj_close,volume,code`
- 股票代码列表导出路径：`data/{type}/{market}/code.jsonl`（存在则按 code 更新）

## 安装
```bash
pip install -r requirements.txt
```

## 命令
```bash
# A 股单标的抓取
PYTHONPATH=src python -m naive_fin_data.cli single-a --code 600519 --period 1d --output-root data

# A 股全量抓取（可选 limit）
PYTHONPATH=src python -m naive_fin_data.cli full-a --period 1m --output-root data --limit 10

# 港股单标的抓取
PYTHONPATH=src python -m naive_fin_data.cli single-hk --code 00005 --period 1d --output-root data

# 港股全量抓取（可选 limit）
PYTHONPATH=src python -m naive_fin_data.cli full-hk --period 5m --output-root data --limit 10

# 导出全部 A 股代码
PYTHONPATH=src python -m naive_fin_data.cli codes-a --output-root data

# 导出全部港股代码
PYTHONPATH=src python -m naive_fin_data.cli codes-hk --output-root data
```

## 测试
```bash
pip install -r requirements-dev.txt
# 仅保留集成测试（真实调用外部接口）
PYTHONPATH=src pytest -q -m integration
```

## GitHub Action
工作流文件：`.github/workflows/daily-fetch.yml`

- 每天 UTC `22:00`（北京时间次日 `06:00`）自动执行
- 对 A 股与港股分别抓取周期：`1m,5m,15m,30m,60m,1d`
- `workflow_dispatch` 支持可选输入 `limit`；不传则全量抓取
- 抓取完成后会 `git add data` 并推送到当前分支

