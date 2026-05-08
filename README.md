# RAG 知识库

企业级 RAG 知识库教程项目。

## 第 2 章 启动指引

### 1. 准备环境变量

```bash
cp .env.example .env
# 按需填写 COS 凭据；若暂不验证 COS，可保留空值
```

### 2. 启动 PostgreSQL

```bash
docker compose up -d
```

### 3. 启动后端

```bash
cd backend
uv sync
uv run alembic upgrade head        # 空迁移，确保 alembic 配置就绪
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

健康检查：

- http://localhost:8000/api/health
- http://localhost:8000/api/health/db
- http://localhost:8000/api/health/cos

### 4. 启动前端

```bash
cd frontend
npm install
npm run gen:api      # 从 http://localhost:8000/openapi.json 生成接口 TS 类型
npm run dev
```

访问 http://localhost:5173 ，首页应显示三个健康检查全部 ok。

> 后端接口签名/Pydantic schema 改动后，重新跑 `npm run gen:api` 即可同步前端类型。
> 生成产物 `frontend/src/types/schema.d.ts` 不进 git，每位学员本地按需生成。
