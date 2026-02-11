# LiteCron

<div align="center">

![logo](/assets/logo.png)

![Docker](https://img.shields.io/badge/Docker-20.10+-blue?logo=docker)
![Python](https://img.shields.io/badge/Python-3.11+-green?logo=python)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Web UI](https://img.shields.io/badge/Web_UI-Flask-orange)

**Lightweight Cron Job Scheduler**, run Python scripts with Docker.

[English](./README_EN.md) | [中文](./README.md)

</div>

## Core Features

- 🐳 **Dockerized Deployment** - One-click startup, environment isolation
- ⏰ **Cron Expressions** - Flexible scheduling rules
- 🐍 **Python Scripts** - Native Python 3.11+ support
- 🌐 **Web Management Interface** - View status and manage tasks in browser
- 🔔 **Notification System** - Support Webhook and NTFY notifications
- 📊 **Execution Logs** - Automatically record task output
- 🔒 **Environment Variables** - Secure configuration management

## Directory Structure

```
lite-cron/
├── 📄 config.yml                 # Task configuration file
├── 📄 config.example.yml         # Configuration example file
├── 🐳 Dockerfile                 # Docker image build file
├── 🐳 compose.yml                # Container orchestration config
├── 🐳 compose.example.yml        # Container orchestration example
├── 📜 manage.py                  # Management script (Python, interactive menu)
├── 📝 requirements.txt           # Python dependencies
├── 📁 src/                       # Source code directory
│   ├── webapp.py                 # Web management interface (Flask)
│   ├── notify.py                 # Notification module
│   ├── make_cron.py              # Generate crontab configuration
│   ├── make_env.py               # Generate environment variables
│   ├── task_wrapper.py           # Task execution wrapper (Python)
│   ├── entrypoint.sh             # Container startup entry
│   ├── 📁 template/              # HTML templates
│   │   └── index.html            # Main page template
│   └── 📁 static/                # Static assets
│       ├── app.js                # Frontend logic
│       └── style.css             # Styles
├── 📁 tasks/                     # Task scripts (built-in, add new scripts manually)
│   ├── ikuuu.py                  # iKuuu check-in
│   ├── pttime.py                 # PTTime check-in
│   ├── smzdm.py                  # SMZDM check-in
│   ├── tieba.py                  # Baidu Tieba check-in
│   ├── fnclub.py                 # FNClub check-in
│   └── aliyunpan.py              # Aliyun Drive check-in
├── 📁 data/                      # Persistent data directory
└── 📁 logs/                      # Runtime logs directory
```

## Quick Start

### Requirements

| Software | Minimum | Recommended |
|----------|-----------|----------|
| Docker | 20.10+ | 24.0+ |
| Docker Compose | 2.0+ | 2.20+ |
| Python | 3.8+ | 3.11+ |
| Git | Any | Latest |

### 1. Clone Repository

```bash
git clone https://github.com/pdone/lite-cron.git
cd lite-cron
```

### 2. Configure Tasks

Copy and edit configuration:

```bash
cp config.example.yml config.yml
vim config.yml
```

Example configuration:

```yaml
tasks:
  - name: "ExampleTask"
    schedule: "0 2 * * *"  # Daily at 2 AM
    script: "tasks/example.py"
    description: "Example task"
    enabled: true
    env:
      API_KEY: "your_key"

# Notification config
notify:
  on_failure: true
  webhook:
    url: "https://hooks.example.com/send"
    method: "POST"
```

> Full example see [config.example.yml](./config.example.yml)

### 3. Start Container

#### Using Docker Compose

```bash
cp compose.example.yml compose.yml
docker compose up -d
```

> Full example see [compose.example.yml](./compose.example.yml)

![Docker](/assets/usage.png)

#### Manual Build and Start
```bash
# Build and start
python manage.py build
python manage.py start

# Check status
python manage.py status
```

### 4. Access Web Interface

Open browser: **http://localhost:5000**

![WebUI](/assets/page.png)

## Usage Guide

### Management Script

`manage.py` provides interactive menu and command-line modes:

#### Interactive Menu (Recommended)

```bash
python manage.py              # Start interactive menu
```

![Manage Menu](/assets/manage.png)

#### Command Line Mode

```bash
# Container Management
python manage.py start        # Start container
python manage.py stop         # Stop container
python manage.py restart      # Restart container
python manage.py status       # Check status
python manage.py logs         # View logs
python manage.py shell        # Enter container
python manage.py reload       # Reload configuration

# Task Execution
python manage.py list           # List scheduled tasks
python manage.py run TaskName   # Run specific task
python manage.py run --all      # Run all enabled tasks
python manage.py tasklogs       # View task logs
python manage.py validate       # Validate configuration

# System Maintenance
python manage.py build              # Build image
python manage.py build v1.0.0       # Build with tag
python manage.py build --no-cache   # Force reinstall dependencies
python manage.py update             # Update project
python manage.py clean              # Clean old logs
python manage.py notify "message"   # Send test notification
python manage.py help               # Show help
```

### Writing Task Scripts

Reference `tasks/example.py`:

```python
#!/usr/bin/env python3
"""
Task Description: One sentence to describe the task
"""
import os
import sys
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Read configuration from environment variables
API_KEY = os.environ.get('API_KEY')


def main():
    """Main function: task logic"""
    try:
        logger.info("🚀 Task started")

        # Task logic
        logger.info("📋 Executing...")
        result = do_something(API_KEY)

        if result:
            logger.info("✅ Task succeeded")
            return 0
        else:
            logger.warning("⚠️ Task failed")
            return 1

    except Exception as e:
        logger.error(f"❌ Task exception: {str(e)}")
        return 1

    finally:
        logger.info("🏁 Task ended")


def do_something(api_key: str) -> bool:
    """Business logic function"""
    # Implement your task logic
    return True


if __name__ == '__main__':
    sys.exit(main())
```

## Configuration

### Task Configuration

| Field | Description | Example |
|------|------|------|
| `name` | Task name (unique) | `"DailyCheck"` |
| `schedule` | Cron expression | `"0 9 * * *"` |
| `script` | Script path | `"tasks/job.py"` |
| `description` | Task description | `"Daily check-in"` |
| `enabled` | Whether enabled | `true` / `false` |
| `env` | Task-specific env vars | `KEY: "value"` |

### Cron Expressions

```
* * * * *
│ │ │ │ └── Weekday (0-7, 0 and 7 are Sunday)
│ │ │ └──── Month (1-12)
│ │ └────── Day (1-31)
│ └──────── Hour (0-23)
└────────── Minute (0-59)
```

### Common Cron Examples

| Expression | Description |
|--------|------|
| `0 2 * * *` | Daily at 2 AM |
| `*/5 * * * *` | Every 5 minutes |
| `0 9 * * 1` | Every Monday at 9 AM |
| `30 4 * * 0,6` | Every Sat/Sun at 4:30 AM |
| `0 */3 * * *` | Every 3 hours |
| `0 0 1 * *` | First day of month |
| `0 0 * * 0` | Every Sunday midnight |

**Online Tool**: [Crontab Guru](https://crontab.guru/) - Cron expression generator and validator

### Notification Configuration

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

## Troubleshooting

### Container Won't Start

```bash
# Check if port is occupied
netstat -tlnp | grep 5000

# View detailed error
docker compose logs

# Check configuration syntax
python manage.py validate
```

### Tasks Not Running

```bash
# 1. Check container status
python manage.py status

# 2. Check container logs
python manage.py logs

# 3. Validate cron expression
python manage.py list

# 4. Confirm task is enabled
# Check enabled: true in config.yml
```

### Notifications Not Received

1. Verify `config.yml` notification settings
2. Check if Webhook URL is accessible
3. Confirm NTFY server configuration
4. Send test notification:

```bash
python manage.py notify "message"                    # Send test notification
python manage.py notify "message" -l                 # With last 15 lines of logs
python manage.py notify "message" -l -n 30           # With last 30 lines
python manage.py notify "message" --log-lines 20     # Same, using long option
python manage.py help                                # Show help
```

### View Logs

```bash
# View container logs
python manage.py logs

# View task logs
python manage.py tasklogs

```

## Performance Optimization

### Container Optimization

- Use `python:3.11-slim` to reduce image size
- Use `--no-cache-dir` to reduce pip install size
- Set reasonable health check intervals

### Task Optimization

- Avoid long-blocking tasks
- Use connection pools for HTTP connections
- Set reasonable timeout values

### Log Optimization

- Clean old logs regularly: `python manage.py clean`
- Use INFO log level in production
- Monitor log file sizes

## Comparison with Similar Projects

| Feature | LiteCron | Airflow | Celery | Cron |
|------|----------|---------|--------|------|
| Deployment Complexity | ⭐ Simple | ⭐⭐⭐ Complex | ⭐⭐ Medium | ⭐ Simple |
| Web UI | ✅ Built-in | ✅ Powerful | ❌ Extra config needed | ❌ None |
| Python Native | ✅ | ✅ | ✅ | ❌ |
| Lightweight | ✅ | ❌ | ❌ | ✅ |
| Notification System | ✅ Built-in | ⚠️ Needs config | ⚠️ Needs config | ❌ |
| Best For | Personal/Small projects | Large enterprises | Medium projects | Simple scheduling |

**LiteCron is suitable for**:
- Personal server automation
- Small project scheduled tasks
- Scenarios requiring simple Web UI
- Docker deployment environments

## Contributing

Pull Requests and Issues are welcome!

### Submitting PR

1. Fork this repository
2. Create branch: `git checkout -b feature/xxx`
3. Commit changes: `git commit -m "feat: add new feature"`
4. Push branch: `git push origin feature/xxx`
5. Create Pull Request

### Code Standards

- 📝 Use comments
- 🎯 Add type annotations to functions
- ⏱️ Record start/end time
- 🎨 Use emoji markers in logs
- 🚪 Return 0 (success) or 1 (failure)

## License

MIT License - See [LICENSE](/LICENSE) file

## Acknowledgments

- [Flask](https://flask.palletsprojects.com/) - Web framework
- [Croniter](https://croniter.readthedocs.io/) - Cron expression parser
- [Docker](https://www.docker.com/) - Containerization

---

🔗 **Links**:
- [Project Repository](https://github.com/pdone/lite-cron)
- [Issue Tracker](https://github.com/pdone/lite-cron/issues)
