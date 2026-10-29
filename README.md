# 仓库同步

单管理员使用的仓库定时同步工具。从 GitHub 或 Gitee 的 HTTPS 地址拉取上游，在本机保留镜像，并按配置保存到本地目录、GitHub、Gitee 或 WebDAV。

## 环境

- Python 3.11 或更高版本，以及 [uv](https://docs.astral.sh/uv/)
- Node.js `^20.19.0` 或 `>=22.12.0`，以及 npm
- Git

## 启动

在仓库根目录执行：

```bash
make dev
```

第一次运行会把 `.env.example` 复制为 `.env`。浏览器打开 `http://127.0.0.1:5173`，用 `.env` 里的 `INITIAL_ADMIN_PASSWORD` 登录。示例里的默认值是 `change-me`，登录后请到设置里修改密码。

后端监听 `http://127.0.0.1:8000`。前端开发服务器把 `/api` 代理到后端，登录 Cookie 留在前端这个来源上。

## 配置

复制 `.env.example` 为 `.env` 后按需修改。`.env` 不进入 Git。已有的环境变量优先于 `.env` 中的同名项。布尔值用 `1` 表示开启，`0` 表示关闭。

| 变量 | 作用 |
| --- | --- |
| `INITIAL_ADMIN_PASSWORD` | 首次启动时创建管理员的密码。管理员已经存在时，只改这一项不会改变登录密码。 |
| `ADMIN_PASSWORD_RESET` | 设为 `1` 时，启动用上面的密码重置管理员，并让已有登录失效。重置成功后改回 `0`，否则每次启动都会再次重置。 |
| `DATA_DIR` | 数据目录，存放 SQLite、加密密钥和内部镜像。相对路径相对于仓库根目录。留空时使用仓库下的 `data`。 |
| `DATABASE_URL` | 数据库连接。留空时使用数据目录下的 `app.db`。可改为 `postgresql+psycopg://...` 或 `mysql+pymysql://...?charset=utf8mb4`。 |
| `SECRET_KEY` | 加密 GitHub、Gitee 令牌和 WebDAV 密码。留空时自动生成 `secret.key` 并放进数据目录。设定后请保持不变，更换后已保存的令牌无法解密。 |
| `SCHEDULER_ENABLED` | 设为 `1` 时按仓库调度自动同步。设为 `0` 时仍可手动同步，不跑定时任务。 |
| `ALLOW_FILE_UPSTREAMS` | 设为 `1` 时允许把本机绝对路径当作上游。默认关闭，上游只接受 GitHub 和 Gitee 的 HTTPS 地址。 |
| `CORS_ORIGINS` | 允许浏览器携带登录 Cookie 的来源，多个用英文逗号分隔。默认是 `http://127.0.0.1:5173,http://localhost:5173`。 |
| `GIT_TIMEOUT_SECONDS` | 单次 Git 命令的超时秒数，默认 `600`。 |
| `BACKEND_PORT` | 后端端口的记录，默认 `8000`。`make dev` 不读取 `.env`。 |
| `FRONTEND_PORT` | 前端端口的记录，默认 `5173`。`make dev` 不读取 `.env`。 |
| `BACKEND_URL` | 前端代理目标的记录，默认 `http://127.0.0.1:8000`。`make dev` 不读取 `.env`。 |

GitHub、Gitee 令牌和 WebDAV 账号在登录后的设置页填写，不写在 `.env` 里。

## 端口

`make dev` 的端口来自 Makefile：

```bash
make dev BACKEND_PORT=9000 FRONTEND_PORT=4173
```

这时后端是 `http://127.0.0.1:9000`，浏览器打开 `http://127.0.0.1:4173`。前端端口改变后，把 `.env` 里的 `CORS_ORIGINS` 改成新的前端地址，再重新启动。

## 常用命令

```bash
make dev        # 同时启动前端和后端
make backend    # 只启动后端
make frontend   # 只启动前端
make test       # 后端 pytest，以及前端测试和主题校验
```

## 目录

- `backend/`：FastAPI 接口，依赖由 uv 管理
- `frontend/`：Vite 和 React 界面
- `deploy/`：Docker Compose 部署文件，用法见 [deploy/README.md](deploy/README.md)
- `data/`：运行后生成，不进入 Git
- `docs/`：功能、架构和需求说明

## Docker 部署

在 `deploy` 目录把 `.env.example` 复制为 `.env`，修改管理员密码后执行 `docker compose up -d --build`。浏览器打开 `http://127.0.0.1:8080`。卷、代理和重置密码见 [deploy/README.md](deploy/README.md)。

更细的行为见 [docs/功能说明.md](docs/功能说明.md)，模块划分见 [docs/架构说明.md](docs/架构说明.md)。

## 许可证

Copyright 2026 mirxiong

本项目采用 [Apache License 2.0](LICENSE)。主题预设的来源和同一许可证见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
