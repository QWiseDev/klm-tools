# KLM Tools

KLM Tools 是一个本地工具集合页面。当前已接入的第一个工具是“抖音去水印”：粘贴 `https://v.douyin.com/...` 短链后，可以解析可用视频分辨率、在线播放预览并下载。

首页是工具集合，后续可以继续添加其他工具。

## 单独分享某个工具

工具打开后会把工具 id 写到地址参数里，方便单独分享给别人。

抖音去水印工具地址：

```text
http://127.0.0.1:8765/?tool=douyin-video
```

线上部署时，把域名替换成你的服务域名即可：

```text
https://your-domain.example/?tool=douyin-video
```

## 推荐方式：Docker Compose 使用线上镜像

推荐直接使用仓库里的 `docker-compose.yml`。它会拉取 GitHub Actions 构建并发布到 GHCR 的线上镜像：

```bash
docker compose up -d
```

访问：

```text
http://127.0.0.1:8765
```

默认镜像地址：

```text
ghcr.io/qwisedev/klm-tools:latest
```

停止服务：

```bash
docker compose down
```

更新到最新线上镜像：

```bash
docker compose pull
docker compose up -d
```

## 方式二：docker run 使用线上镜像

不想使用 compose 时，可以直接运行线上镜像：

```bash
docker run -d \
  --name klm-tools \
  --restart unless-stopped \
  -p 8765:8765 \
  ghcr.io/qwisedev/klm-tools:latest
```

停止并删除容器：

```bash
docker rm -f klm-tools
```

## 二次开发：本地 Docker Compose 构建

二次开发、改代码、本地调试时使用 `docker-compose.local.yml`。这个文件会从当前源码构建镜像：

```bash
docker compose -f docker-compose.local.yml up --build
```

后台运行：

```bash
docker compose -f docker-compose.local.yml up --build -d
```

停止本地开发容器：

```bash
docker compose -f docker-compose.local.yml down
```

## 方式四：本地构建并打包 Docker 镜像

需要把镜像保存成 tar 文件时使用脚本：

```bash
IMAGE_NAME=klm-tools \
IMAGE_TAG=local \
OUTPUT_TAR=dist/klm-tools-docker.tar \
./scripts/docker-build.sh
```

脚本行为：

- 构建镜像：`klm-tools:local`
- 如果设置了 `OUTPUT_TAR`，会执行 `docker save` 输出 tar 文件

只构建不打包：

```bash
IMAGE_NAME=klm-tools IMAGE_TAG=local ./scripts/docker-build.sh
```

## 方式五：源码直接启动

本机有 Python 时，可以不走 Docker：

```bash
./douyin_tool_server.py --host 127.0.0.1 --port 8765
```

访问：

```text
http://127.0.0.1:8765
```

## GitHub Actions

`.github/workflows/docker-build.yml` 会在 `main` 分支 push 时执行：

- 构建 Docker 镜像
- 推送到 GHCR：
  - `ghcr.io/qwisedev/klm-tools:latest`
  - `ghcr.io/qwisedev/klm-tools:<commit-sha>`
- 额外上传一个 Docker tar artifact

如果 GHCR 包不可拉取，需要在 GitHub 仓库或 Package 设置里确认 package visibility 和权限。

## 项目结构

```text
Dockerfile                       # 容器镜像定义
docker-compose.yml               # 推荐使用：拉取 GHCR 线上镜像
docker-compose.local.yml         # 二次开发使用：从本地源码 build
scripts/docker-build.sh          # 本地构建和可选 docker save 打包脚本
douyin_tool_server.py            # 通用本地 Web 服务
douyin_download.py               # 抖音命令行下载脚本，也可独立使用
tools/
  __init__.py                    # 后端工具注册和路由分发
  douyin_video.py                # 抖音去水印工具后端
web/
  index.html                     # 工具集合页面和工具视图
  app.js                         # 前端工具注册、导航和控制器
  styles.css                     # 页面样式
```

## 添加新工具

1. 在 `tools/` 新增后端模块，例如 `tools/example_tool.py`。
2. 在模块里提供 `META`、`route_get()`、`route_post()`。
3. 在 `tools/__init__.py` 导入模块并加入 `TOOLS`。
4. 在 `web/index.html` 新增一个 `data-tool-view="example-tool"` 的视图。
5. 在 `web/app.js` 的 `TOOL_DEFINITIONS` 里注册工具。
6. 在 `web/app.js` 中实现该工具自己的 controller。

后端工具模块示例：

```python
META = {
    "id": "example-tool",
    "name": "示例工具",
    "category": "通用",
    "description": "一句话说明这个工具做什么。",
    "status": "ready",
}

def route_get(handler, parsed, *, send_body: bool) -> bool:
    return False

def route_post(handler, parsed) -> bool:
    if parsed.path == "/api/example/run":
        data = handler.read_json_body()
        handler.send_json({"ok": True, "input": data})
        return True
    return False
```

前端注册示例：

```js
{
  id: "example-tool",
  label: "示例工具",
  category: "通用",
  description: "一句话说明这个工具做什么。",
  badge: "已接入",
  viewSelector: '[data-tool-view="example-tool"]',
  controller: initExampleTool,
}
```

## 设计约定

- `docker-compose.yml` 面向部署，使用线上镜像。
- `docker-compose.local.yml` 面向二次开发，使用本地源码 build。
- 后端主服务只做静态资源、健康检查、工具清单和路由分发。
- 每个工具模块只处理自己的 API 前缀。
- 前端每个工具都有独立 `data-tool-view` 和 controller。
- 工具如果需要访问外部资源，优先通过后端代理，避免浏览器跨域、Referer 或 Range 请求限制。
