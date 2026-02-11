# LiteCron

<div align="center">

![logo](/assets/logo.png)

![Docker](https://img.shields.io/badge/Docker-20.10+-blue?logo=docker)
![Python](https://img.shields.io/badge/Python-3.11+-green?logo=python)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Web UI](https://img.shields.io/badge/Web_UI-Flask-orange)

**轻量级定时任务调度器**，基于 Docker 运行 Python 脚本。

[English](./README_EN.md) | [中文](./README.md)

</div>

## 核心功能

- 🐳 **Docker 化部署** - 一键启动，环境隔离
- ⏰ **Cron 表达式** - 灵活配置定时规则
- 🐍 **Python 脚本** - 原生支持 Python 3.11+
- 🌐 **Web 管理界面** - 浏览器中查看状态和管理任务
- 🔔 **通知系统** - 支持 Webhook 和 NTFY 多种通知方式
- 📊 **执行日志** - 自动记录任务输出
- 🔒 **环境变量** - 安全的配置管理

## 目录结构

```
lite-cron/
├── 📄 config.yml                 # 任务配置文件
├── 📄 config.example.yml         # 配置示例文件
├── 🐳 Dockerfile                 # 镜像构建文件
├── 🐳 compose.yml                # 容器编排配置
├── 🐳 compose.example.yml        # 容器编排配置示例
├── 📜 manage.py                  # 管理脚本（Python实现，支持交互式菜单）
├── 📝 requirements.txt           # Python 依赖
├── 📁 src/                       # 源代码目录
│   ├── webapp.py                 # Web 管理界面（Flask）
│   ├── notify.py                 # 通知模块
│   ├── make_cron.py              # 生成 crontab 配置文件
│   ├── make_env.py               # 生成环境变量配置文件
│   ├── task_wrapper.py           # 任务执行包装器（Python）
│   ├── entrypoint.sh             # 容器启动入口
│   ├── 📁 template/              # HTML 模板目录
│   │   └── index.html            # 主页面模板
│   └── 📁 static/                # 静态资源目录
│       ├── app.js                # 前端交互逻辑
│       └── style.css             # 样式文件
├── 📁 tasks/                     # 任务脚本目录（项目内置，可手动添加新脚本）
│   ├── ixxxu.py                  # ixxxu 签到
│   ├── pxxxme.py                 # Pxxxme 签到
│   ├── smzdm.py                  # 什么值得买签到
│   ├── tieba.py                  # 百度贴吧签到
│   ├── fnclub.py                 # 飞牛Nas论坛签到
│   └── aliyunpan.py              # 阿里云盘签到
├── 📁 data/                      # 持久化数据目录
└── 📁 logs/                      # 运行时日志目录
```

## 快速开始

### 环境要求

| 软件 | 最低版本 | 推荐版本 |
|------|-----------|----------|
| Docker | 20.10+ | 24.0+ |
| Docker Compose | 2.0+ | 2.20+ |
| Python | 3.8+ | 3.11+ |
| Git | 任意 | 最新 |

### 1. 克隆项目

```bash
git clone https://github.com/pdone/lite-cron.git
cd lite-cron
```

### 2. 配置任务

复制并编辑配置文件：

```bash
cp config.example.yml config.yml
vim config.yml
```

示例配置：

```yaml
tasks:
  - name: "ExampleTask"
    schedule: "0 2 * * *"  # 每天凌晨2点
    script: "tasks/example.py"
    description: "示例任务"
    enabled: true
    env:
      API_KEY: "your_key"

# 通知配置
notify:
  on_failure: true
  webhook:
    url: "https://hooks.example.com/send"
    method: "POST"
```

> 完整示例见 [config.example.yml](./config.example.yml)

### 3. 启动容器

#### 使用 Docker Compose

```bash
cp compose.example.yml compose.yml
docker compose up -d
```

> 完整示例见 [compose.example.yml](./compose.example.yml)

![Docker](/assets/usage.png)

#### 手动构建并启动容器
```bash
# 构建并启动
python manage.py build
python manage.py start

# 查看状态
python manage.py status
```

### 4. 访问 Web 界面

打开浏览器访问：**http://localhost:5000**

![WebUI](/assets/page_cn.png)

## 使用指南

### 管理脚本

`manage.py` 提供交互式菜单和命令行两种使用方式：

#### 交互式菜单（推荐）

```bash
python manage.py              # 启动交互式菜单
```

![Manage Menu](/assets/manage.png)

#### 命令行模式

```bash
# 容器管理
python manage.py start        # 启动容器
python manage.py stop         # 停止容器
python manage.py restart      # 重启容器
python manage.py status       # 查看状态
python manage.py logs         # 查看日志
python manage.py shell        # 进入容器
python manage.py reload       # 重新加载配置

# 任务执行
python manage.py list           # 查看定时任务计划
python manage.py run TaskName   # 执行指定任务
python manage.py run --all      # 执行所有已启用任务
python manage.py tasklogs       # 查看任务日志
python manage.py validate       # 验证配置

# 系统维护
python manage.py build              # 构建镜像
python manage.py build v1.0.0       # 构建并指定标签
python manage.py build --no-cache   # 强制重新安装依赖
python manage.py update             # 更新项目
python manage.py clean              # 清理旧日志
python manage.py notify "消息"      # 发送测试通知
python manage.py help               # 查看帮助
```

### 编写任务脚本

参考 `tasks/example.py`：

```python
#!/usr/bin/env python3
"""
任务描述：一句话说明任务功能
"""
import os
import sys
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 从环境变量读取配置
API_KEY = os.environ.get('API_KEY')


def main():
    """主函数：任务逻辑"""
    try:
        logger.info("🚀 任务开始")

        # 任务逻辑
        logger.info("📋 执行操作...")
        result = do_something(API_KEY)

        if result:
            logger.info("✅ 任务成功")
            return 0
        else:
            logger.warning("⚠️ 任务失败")
            return 1

    except Exception as e:
        logger.error(f"❌ 任务异常: {str(e)}")
        return 1

    finally:
        logger.info("🏁 任务结束")


def do_something(api_key: str) -> bool:
    """业务逻辑函数"""
    # 实现你的任务逻辑
    return True


if __name__ == '__main__':
    sys.exit(main())
```

## 配置说明

### 任务配置

| 字段 | 说明 | 示例 |
|------|------|------|
| `name` | 任务名称（唯一） | `"DailyCheck"` |
| `schedule` | Cron 表达式 | `"0 9 * * *"` |
| `script` | 脚本路径 | `"tasks/job.py"` |
| `description` | 任务描述 | `"每日签到"` |
| `enabled` | 是否启用 | `true` / `false` |
| `env` | 专属环境变量 | `KEY: "value"` |

### Cron 表达式

```
* * * * *
│ │ │ │ └── 星期 (0-7, 0和7都代表星期日)
│ │ │ └──── 月份 (1-12)
│ │ └────── 日期 (1-31)
│ └──────── 小时 (0-23)
└────────── 分钟 (0-59)
```

### 常用 Cron 示例

| 表达式 | 说明 |
|--------|------|
| `0 2 * * *` | 每天凌晨 2 点 |
| `*/5 * * * *` | 每 5 分钟 |
| `0 9 * * 1` | 每周一上午 9 点 |
| `30 4 * * 0,6` | 每周六和周日凌晨 4:30 |
| `0 */3 * * *` | 每 3 小时 |
| `0 0 1 * *` | 每月第一天 |
| `0 0 * * 0` | 每周日午夜 |

**在线工具**: [Crontab Guru](https://crontab.guru/) - Cron 表达式在线生成器和验证

### 通知配置

#### Webhook

```yaml
notify:
  webhook:
    url: "https://hooks.example.com/send"
    method: "POST"
    content_type: "application/json"
    headers: |
      Authorization: Bearer your_token
```

#### NTFY

```yaml
notify:
  ntfy:
    url: "https://ntfy.sh"
    topic: "lite-cron"
    priority: "3"
    username: "user"
    password: "pass"
```

## 故障排查

### 容器无法启动

```bash
# 检查端口是否被占用
netstat -tlnp | grep 5000

# 查看详细错误
docker compose logs

# 检查配置文件语法
python manage.py validate
```

### 任务没有执行

```bash
# 1. 查看容器状态
python manage.py status

# 2. 检查容器日志
python manage.py logs

# 3. 验证 cron 表达式
python manage.py list

# 4. 确认任务已启用
# 检查 config.yml 中 enabled: true
```

### 通知没有收到

1. 验证 `config.yml` 中的通知配置
2. 检查 Webhook URL 是否可访问
3. 确认 NTFY 服务器配置正确
4. 发送测试通知：

```bash
python manage.py notify "消息"                    # 发送测试通知
python manage.py notify "消息" -l                 # 发送测试通知附带最近 15 行日志
python manage.py notify "消息" -l -n 30           # 发送测试通知附带最近 30 行日志
python manage.py notify "消息" --log-lines 20     # 同上，使用长参数
python manage.py help                             # 查看帮助
```

### 查看日志

```bash
# 查看容器日志
python manage.py logs

# 查看任务日志
python manage.py tasklogs

```

## 性能优化

### 容器优化

- 使用 `python:3.11-slim` 减少镜像体积
- 使用 `--no-cache-dir` 减少 pip 安装体积
- 合理设置健康检查间隔

### 任务优化

- 避免长时间阻塞的任务
- 使用连接池复用 HTTP 连接
- 设置合理的超时时间

### 日志优化

- 定期清理旧日志：`python manage.py clean`
- 生产环境使用 INFO 日志级别
- 监控日志文件大小

## 与类似项目对比

| 特性 | LiteCron | Airflow | Celery | Cron |
|------|----------|---------|--------|------|
| 部署复杂度 | ⭐ 简单 | ⭐⭐⭐ 复杂 | ⭐⭐ 中等 | ⭐ 简单 |
| Web UI | ✅ 内置 | ✅ 强大 | ❌ 需额外配置 | ❌ 无 |
| Python 原生 | ✅ | ✅ | ✅ | ❌ |
| 轻量级 | ✅ | ❌ | ❌ | ✅ |
| 通知系统 | ✅ 内置 | ⚠️ 需配置 | ⚠️ 需配置 | ❌ |
| 适合场景 | 个人/小型项目 | 大型企业 | 中型项目 | 简单定时 |

**LiteCron 适合**：
- 个人服务器自动化
- 小型项目的定时任务
- 需要简单 Web 界面的场景
- Docker 化部署环境

## 贡献指南

欢迎提交 Pull Request 或 Issue！

### 提交 PR

1. Fork 本项目
2. 创建分支：`git checkout -b feature/xxx`
3. 提交更改：`git commit -m "feat 添加新功能"`
4. 推送分支：`git push origin feature/xxx`
5. 创建 Pull Request

### 代码规范

- 📝 使用中文注释
- 🎯 函数添加类型注解
- ⏱️ 记录开始/结束时间
- 🎨 使用 emoji 标记日志
- 🚪 返回 0（成功）或 1（失败）

## 许可证

MIT License - 详见 [LICENSE](/LICENSE) 文件

## 致谢

- [Flask](https://flask.palletsprojects.com/) - Web 框架
- [Croniter](https://croniter.readthedocs.io/) - Cron 表达式解析
- [Docker](https://www.docker.com/) - 容器化技术

---

🔗 **链接**:
- [项目地址](https://github.com/pdone/lite-cron)
- [问题反馈](https://github.com/pdone/lite-cron/issues)
