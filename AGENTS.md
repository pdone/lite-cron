# LiteCron - Agent Development Guide

LiteCron is a lightweight Docker-based Python cron job scheduler with WebUI and notification support.

## Quick Reference

### Essential Commands

```bash
# Interactive menu (recommended)
python manage.py

# Container management
python manage.py start|stop|restart|status|logs|shell|build|update

# Task management
python manage.py list                    # List scheduled tasks
python manage.py run <TaskName>          # Run specific task (in container)
python manage.py run --all               # Run all enabled tasks (in container)
python manage.py run-local <TaskName>    # Run task locally (no Docker required)
python manage.py run-local --all         # Run all enabled tasks locally
python manage.py tasklogs                # View task logs
python manage.py validate                # Validate config.yml

# Notifications
python manage.py notify "message"        # Send test notification
python manage.py notify "message" -l     # With recent logs
python manage.py notify "message" -l -n 30  # With 30 lines of logs

# Maintenance
python manage.py clean                   # Clean logs older than 7 days
python manage.py build [--no-cache]      # Build Docker image
python manage.py build v1.0.0            # Build with custom tag
```

### Local Development

```bash
pip install -r requirements.txt
python src/webapp.py                     # Run WebUI locally (port 5000)
python tasks/ikuuu.py                    # Test task script directly
```

## Architecture

### Directory Structure

```
lite-cron/
├── manage.py              # Main management script (interactive + CLI)
├── config.yml             # Task configuration (GITIGNORED - user-specific)
├── config.example.yml     # Configuration template
├── compose.yml            # Docker compose (GITIGNORED)
├── compose.example.yml    # Docker compose template
├── Dockerfile             # Python 3.11-slim based
├── requirements.txt       # Dependencies: PyYAML, requests, Flask, croniter, curl_cffi
├── src/                   # Core source (runs in container as /app/)
│   ├── entrypoint.sh      # Container entrypoint - starts cron + WebUI
│   ├── task_wrapper.py    # Task execution wrapper with notifications
│   ├── webapp.py          # Flask WebUI (port 5000)
│   ├── notify.py          # Notification module (Webhook + NTFY)
│   ├── make_cron.py       # Generates crontab from config.yml
│   ├── make_env.py        # Generates .env from config.yml
│   ├── logger.py          # Python logging (file + stdout)
│   ├── logger.sh          # Shell logging (for entrypoint.sh)
│   ├── template/          # Flask templates
│   └── static/            # Static assets
├── tasks/                 # Task scripts (user-facing)
│   ├── ikuuu.py, pttime.py, smzdm.py, tieba.py, fnclub.py,
│   ├── aliyunpan.py, bilibili.py, v2ex.py, nodeseek.py, zhutix.py
│   └── README.md          # Task documentation
├── logs/                  # Runtime logs (date-based: YYYYMMDD.log)
└── data/                  # Persistent data
```

### Key Architecture Points

1. **Container Path Mapping**: `src/` maps to `/app/` in container. Task scripts reference paths relative to `/app/`.

2. **Environment Variable Flow**:
   - `config.yml` → `make_env.py` → `/app/.env` → loaded by `task_wrapper.py`
   - Task env vars are prefixed: `TaskName_KEY` in container → `KEY` in task script
   - Global env vars set via `global_env` in config.yml

3. **Task Execution Chain**:
   - Cron triggers → `task_wrapper.py <TaskName> <script_path>` → actual script
   - Wrapper handles: env setup, logging, timing, failure notifications
   - Execution modes: `cron` (default), `webui`, `cli` (via `LITECRON_EXEC_MODE`)

4. **Notification System**:
   - Configured in `config.yml` under `notify` section
   - Supports Webhook (JSON/form/text) and NTFY
   - Auto-triggers on task failure (configurable for success too)
   - `notify.py` can be called standalone for testing

## Task Script Conventions

### Standard Template

```python
#!/usr/bin/env python3
"""
Task Name - Brief description

Environment Variables:
- VAR_NAME: Description (required)
- OPTIONAL_VAR: Description (optional)
"""
import os
import sys

# Import project logger (REQUIRED - don't use standard logging)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import log_info, log_success, log_error, log_warning, log_debug, log_response_detail

# Read env vars
MY_VAR = os.environ.get("MY_VAR")


def main() -> int:
    """Main function - returns 0 for success, 1 for failure"""
    log_info("🚀 Task started")
    
    try:
        # Task logic here
        result = do_something()
        if result:
            log_success("✅ Task completed")
            return 0
        else:
            log_warning("⚠️ Task failed")
            return 1
    except Exception as e:
        log_error(f"❌ Error: {str(e)}")
        return 1
    finally:
        log_info("🏁 Task finished")


if __name__ == "__main__":
    sys.exit(main())
```

### Critical Rules for Task Scripts

1. **Always use project logger**: `from logger import log_info, ...` - NOT `import logging`
2. **Return codes**: `0` = success, `1` = failure (wrapper uses this for notifications)
3. **Env var access**: Use `os.environ.get("KEY")` - vars are set by task_wrapper
4. **Script location**: Place in `tasks/` directory
5. **Path references**: Script runs in `/app/` context inside container
6. **失败必须记录站点返回原文**: 请求失败、解析失败或接口返回异常时调用
   `log_response_detail(response)`。响应完整原文落盘到 `logs/responses/<日期>/`；
   主日志只输出状态码、URL、响应长度、落盘路径与摘要（短响应内联全文，长响应记片段），
   避免大段 HTML 冲垮 WebUI 日志视图

### Adding New Tasks

1. Create script in `tasks/` following template above
2. Add to `config.yml`:
   ```yaml
   tasks:
     - name: "TaskName"
       schedule: "0 2 * * *"      # Cron expression (5 fields)
       script: "tasks/myscript.py"
       description: "What it does"
       enabled: true
       env:
         MY_VAR: "value"
   ```
3. Test locally: `python tasks/myscript.py`
4. Rebuild container if adding new pip dependencies: `python manage.py build`

## 环境变量命名规范

为在“模块解耦”与“配置一致性”之间取得平衡，所有任务的环境变量遵循统一规范：**以任务名为前缀进行命名空间化**。

### 核心原则

1. **一律使用任务名前缀**：任务的所有 env 键必须以 `<任务名大写>_` 前缀声明，例如 `IKUUU_COOKIE`、`BILIBILI_COOKIE`、`V2EX_PROXY`。
   - 前缀不是冗余噪声，而是标识“该凭据/配置属于哪个任务”的语义信息，可避免多任务同名键冲突。
   - `make_env.py` 会自动为 `config.yml` 中 `task.env` 的键加上 `任务名_` 前缀；`task_wrapper.py` 注入时会同时保留带前缀与去前缀两种形态，脚本读取带前缀的名字即可。

2. **凭据类命名要语义准确**：
   - 站点 Cookie 统一用 `<TASK>_COOKIE`（如 `IKUUU_COOKIE`、`V2EX_COOKIE`）。
   - 账号密码类用 `<TASK>_EMAIL` / `<TASK>_PWD`（如 `IKUUU_EMAIL` / `IKUUU_PWD`）。
   - Token 类按真实语义命名，不要硬塞进 `COOKIE` 家族，如阿里云盘用 `ALIYUN_REFRESH_TOKEN`。

3. **可选开关也要带前缀**：功能开关、参数同样遵循前缀规范，避免全局裸键。例如 Bilibili 的 `BILIBILI_COIN_NUM`、`BILIBILI_SKIP_COIN`、`BILIBILI_SILVER2COIN` 等，而非裸 `COIN_NUM`、`SKIP_COIN`。

4. **脚本内统一读取带前缀的名字**：`os.environ.get("<TASK>_XXX")`，保证配置层键名与脚本读取一致，便于全局检索与审查。

### 不要合并跨任务的凭据变量

Cookie / Token 是**站点专属**凭据（iKuuu 的 Cookie 不能用于 V2EX），禁止将不同任务的 cookie 合并成同一个 `COOKIE` 变量。合并会破坏脚本独立部署与解耦性（同一 shell 下多个脚本会争抢同一变量），且语义不成立。

### 真正全局的资源用“值共享、键命名空间化”

代理、时区等**真正全局**的资源，可通过以下方式共享值，但键名仍保持任务前缀：

- `global_env`：所有任务共享（如 `TZ: "Asia/Shanghai"`）。
- YAML 锚点：在 `config.yml` 顶部用 `proxy: &proxy "..."` 声明一次，任务中通过 `任务名_PROXY: *proxy` 引用。改代理只需改一处，同时各任务键名仍是 `V2EX_PROXY`、`NODESEEK_PROXY` 等命名空间化形态。

### 反例与修正

| 反例（避免） | 正确写法 |
|---|---|
| `MY_EMAIL` / `MY_PWD` | `IKUUU_EMAIL` / `IKUUU_PWD` |
| 裸 `COIN_NUM` / `SKIP_COIN` | `BILIBILI_COIN_NUM` / `BILIBILI_SKIP_COIN` |
| 多任务共用一个 `COOKIE` | 各任务独立的 `<TASK>_COOKIE` |

## Configuration

### config.yml Structure

```yaml
tasks:
  - name: "TaskName"           # Unique identifier
    schedule: "0 2 * * *"      # Cron: min hour day month weekday
    script: "tasks/script.py"  # Relative to /app/
    description: "Description"
    enabled: true/false
    env:
      KEY: "value"             # Task-specific env vars

global_env:                    # Optional: shared across all tasks
  TZ: "Asia/Shanghai"

notify:
  on_failure: true             # Notify on task failure (default: true)
  on_success: false            # Notify on success (default: false)
  webhook:
    url: "https://..."
    method: "POST"
    content_type: "application/json"
    headers: |
      Authorization: Bearer token
  ntfy:
    url: "https://ntfy.sh"
    topic: "mytopic"
    priority: "3"

webui:
  debug: false                 # Flask debug mode
```

### 共享变量（YAML 锚点）

多个任务需要使用同一代理地址时，可在 `config.yml` 顶部用 YAML 锚点声明一次，下方任务通过 `*proxy` 引用，修改代理只需改一处。

```yaml
# 顶部声明锚点（只需一次）
proxy: &proxy "http://127.0.0.1:7890"

tasks:
  - name: "V2EX"
    env:
      V2EX_PROXY: *proxy      # 引用共享代理
  - name: "NodeSeek"
    env:
      NODESEEK_PROXY: *proxy  # 引用共享代理
  - name: "ZhuTiX"
    env:
      ZHUTIX_PROXY: *proxy    # 引用共享代理
```

说明：
- `&proxy` 定义锚点（名字可自定义，如 `&my_proxy`）
- `*proxy` 引用锚点，YAML 解析时会被替换为实际值
- 不使用代理时，注释掉顶部的 `proxy:` 字段，并删除任务中对应的 `*_PROXY: *proxy` 行（否则引用会解析失败）
- 锚点只能作为独立的值出现，不能用在字符串拼接里（如 `prefix *proxy` 不会被替换）
- 需要不同代理时，可声明多个锚点（如 `&proxy`、`&proxy_us`）

> ⚠️ **注意**：WebUI 切换任务启用状态时通过 `ruamel.yaml` 直接修改 `enabled` 字段并原样 dump，以完整保留锚点、别名与注释，避免 `safe_load` 展开别名后回灌覆盖。

### Cron Expression Format

```
* * * * *
│ │ │ │ └── Weekday (0-7, 0=7=Sunday)
│ │ │ └──── Month (1-12)
│ │ └────── Day (1-31)
│ └──────── Hour (0-23)
└────────── Minute (0-59)

Examples:
0 2 * * *       # Daily at 2 AM
*/5 * * * *     # Every 5 minutes
0 9 * * 1       # Every Monday at 9 AM
```

## Docker Details

### Build & Deploy

```bash
# First time setup
cp config.example.yml config.yml
cp compose.example.yml compose.yml
# Edit config.yml with your settings
python manage.py build
python manage.py start

# Rebuild after code changes
python manage.py build         # Uses cache (fast)
python manage.py build --no-cache  # Force reinstall deps

# Rebuild after config changes only
python manage.py restart       # No rebuild needed - config is volume-mounted
```

### Volume Mounts (in compose.yml)

- `./config.yml:/app/config.yml:ro` - Config (read-only)
- `./tasks:/app/tasks:ro` - Task scripts (read-only)
- `./logs:/app/logs` - Log output
- `./data:/app/data` - Persistent data

### Container Environment

- `TZ=Asia/Shanghai` - Timezone
- `WEBUI=true` - Enable WebUI
- `WEBUI_PORT=5000` - WebUI port
- `LOG_LEVEL=INFO` - Logging level

## WebUI

- Default: http://localhost:5000
- Features: Task list, manual execution, log viewer, config editor
- API endpoints: `/api/status`, `/api/tasks`, `/api/logs`, `/api/tasks/<name>/run`, `/api/tasks/<name>/toggle`

## Common Pitfalls

1. **Forgetting logger import**: Tasks MUST use `from logger import ...`, not standard `logging`
2. **Wrong return code**: Must return `0`/`1`, not `True`/`False`
3. **Path confusion**: Scripts run in `/app/` inside container, not project root
4. **Missing rebuild**: New pip packages require `python manage.py build`
5. **Config changes**: Editing `config.yml` only needs `restart`, not `build`

## Testing

```bash
# Validate config syntax
python manage.py validate

# Test task manually (locally, no Docker)
python manage.py run-local TaskName

# Or run inside the container (container must be running)
python manage.py run TaskName

# Test notification
python manage.py notify "Test message" -l

# Check container status
python manage.py status

# View logs
python manage.py logs          # Container logs
python manage.py tasklogs      # Task execution logs
```

## Code Style

- Python 3.11+ with type hints
- Chinese comments and docstrings preferred
- Emoji markers in logs: 🚀 start, ✅ success, ❌ error, ⚠️ warning, 🏁 end
- No linter/formatter configured - keep code clean manually

## Git Commit Convention

- Commit message prefix 使用 `feat`、`fix`、`docs` 等，但 **`feat` 后不加冒号**
- 示例：`feat 添加新功能`（正确），`feat: 添加新功能`（错误）

## References

- [Crontab Guru](https://crontab.guru/) - Cron expression validator
- [Croniter Docs](https://croniter.readthedocs.io/) - Python cron parser
- [Flask Docs](https://flask.palletsprojects.com/) - Web framework
- [Docker Docs](https://docs.docker.com/) - Container platform
