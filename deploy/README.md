# Docker 部署

浏览器只打开 Web 容器。Nginx 提供前端页面，并把 `/api` 转到后端。登录 Cookie 留在这一个地址上。

后端镜像里带有 Git。SQLite、加密密钥和内部镜像放在数据卷 `/data`。设置页里的「本地目录」使用另一个卷，容器内路径是 `/mirrors`。

## 准备

需要 Docker Engine 和 Docker Compose v2。在 `deploy` 目录执行：

```bash
cp .env.example .env
```

打开 `.env`，把 `INITIAL_ADMIN_PASSWORD` 改成自己的密码。用域名或局域网地址访问时，把 `CORS_ORIGINS` 改成浏览器地址栏中的完整来源，例如 `http://192.168.1.10:8080`。改了 `WEB_PORT` 时，来源里的端口也要一起改。

## 启动

```bash
docker compose up -d --build
```

构建完成后打开 `http://127.0.0.1:8080`。第一次启动用 `.env` 里的密码登录，然后在设置里修改。

查看状态和日志：

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f web
```

停止：

```bash
docker compose down
```

`down` 不会删除数据卷。加上 `-v` 会删掉数据库、密钥和镜像。

## 文件

| 文件 | 作用 |
| --- | --- |
| `docker-compose.yml` | 定义后端、Web、两个数据卷 |
| `backend.Dockerfile` | Python 3.12、uv 安装依赖、Git |
| `frontend.Dockerfile` | 构建前端，再用 Nginx 提供页面 |
| `nginx.conf` | 静态页面和 `/api` 反向代理 |
| `entrypoint.sh` | 准备 `/data`、`/mirrors` 后以降权用户启动 |
| `.env.example` | 部署用环境变量说明 |

仓库根目录的 `.dockerignore` 用来避开本地虚拟环境、依赖目录和数据库。

## 数据

| 容器路径 | 内容 |
| --- | --- |
| `/data` | `app.db`、`secret.key`、未指定本地目录时的内部镜像 |
| `/mirrors` | 设置里选择「本地」保存方式时使用的目录 |

在设置的本地目录输入框填写 `/mirrors`。容器没有图形界面，页面上的「选择目录」无法弹出系统窗口。

GitHub 或 Gitee 需要代理时，在设置里填写容器能访问的地址。访问宿主机上的代理可以用 `http://host.docker.internal:7897`。`127.0.0.1` 指的是容器自己，不是宿主机。

## 更新

拉取新代码后在 `deploy` 目录重新构建：

```bash
docker compose up -d --build
```

数据卷会保留。不要更换 `SECRET_KEY`，也不要删掉 `/data/secret.key`，否则已保存的令牌无法解密。

## 重置管理员密码

在 `.env` 里把 `ADMIN_PASSWORD_RESET` 设为 `1`，确认 `INITIAL_ADMIN_PASSWORD` 是要使用的新密码，然后执行：

```bash
docker compose up -d
```

登录成功后把 `ADMIN_PASSWORD_RESET` 改回 `0`，再执行一次上面的命令。否则下次启动还会重置密码。
