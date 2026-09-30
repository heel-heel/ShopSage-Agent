# ShopSage · 咖啡消费决策与商家运营 Agent

一个面向咖啡器具与咖啡豆场景的双视角 Agent 演示：消费者获得带证据的选购建议；商家管理员查看匿名洞察与完整 Agent 决策轨迹。

## 已实现能力

- 原生 HTML/CSS/JavaScript 的消费者选购页与管理员工作台；
- FastAPI REST API，JWT 区分 `consumer` 和 `merchant_admin`；
- PostgreSQL/SQLite 持久化商品、行为、画像、运行轨迹与知识文档；
- Chroma 知识检索（本地缺失运行时自动降级为确定性检索）；
- LangGraph 固定编排：约束解析、知识检索、目录过滤、画像分析、排序、引用校验；
- 可复现的规则化排序与 JSON Schema 响应；
- 管理员轨迹回放、知识文件哈希去重和受控增量索引。

## 本地运行

```powershell
conda activate shopsage_env
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

打开 `http://127.0.0.1:8000`。管理员入口为 `/admin`，演示凭据默认为：

```text
merchant@shopsage.demo
demo-admin-password
```

也可在安装 Docker 后运行：

```powershell
docker compose up --build
```

## 数据声明

商品与知识内容均为演示目录；生产数据接入前应使用已授权资料。项目计划使用 [UCSD Amazon Product Reviews](https://mcauleylab.ucsd.edu/public_datasets/data/datasets.html) 筛选咖啡相关公开元数据与评论。当前匿名行为事件由固定随机种子生成，仅用于展示画像和漏斗分析，绝不表示真实订单或消费者行为。

## 评测思路

`tests/` 包含约束解析的最小单元测试。下一步可在 `evaluation/` 建立 40 条问题集，并对比纯 LLM、RAG 与全量 Agent 的引用覆盖率、硬约束满足率和结构化输出成功率。
