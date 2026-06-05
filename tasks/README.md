# 内置脚本说明

本目录包含项目内置的自动化任务脚本，主要用于各类网站/应用的自动签到。

## 脚本列表

| 脚本名称 | 功能描述 | 必需环境变量 | 可选环境变量 |
|---------|---------|-------------|-------------|
| [ikuuu.py](#ikuuupy) | iKuuu 自动签到 | `MY_EMAIL`, `MY_PWD` | - |
| [pttime.py](#pttimepy) | PTTime 站点自动签到 | `PTTIME_COOKIE`, `PTTIME_UID` | `PTTIME_PROXY` |
| [smzdm.py](#smzdmpy) | 什么值得买自动签到 | `SMZDM_COOKIE` | - |
| [tieba.py](#tiebapy) | 百度贴吧自动签到 | `TIEBA_COOKIE` | - |
| [fnclub.py](#fnclubpy) | 飞牛Nas论坛自动签到 | `FNNAS_COOKIE` | - |
| [aliyunpan.py](#aliyunpanpy) | 阿里云盘自动签到 | `ALIYUN_REFRESH_TOKEN` | - |
| [bilibili.py](#bilibilipy) | B站多功能签到 | `BILIBILI_COOKIE` | `COIN_NUM`, `COIN_TYPE`, `SILVER2COIN`, `RECEIVE_VIP_PRIVILEGE` |
| [v2ex.py](#v2expy) | V2EX 论坛自动签到 | `V2EX_COOKIE` | `V2EX_PROXY`, `V2EX_SSL_VERIFY` |
| [nodeseek.py](#nodeseekpy) | NodeSeek 论坛自动签到 | `NODESEEK_COOKIE` | `NODESEEK_RANDOM`, `NODESEEK_PROXY` |

---

## 详细说明

### ikuuu.py

**功能：**
- 自动登录 ikuuu.org
- 执行每日签到
- 获取剩余流量信息

**环境变量：**
- `MY_EMAIL`: 登录邮箱（必需）
- `MY_PWD`: 登录密码（必需）

**配置示例：**
```yaml
tasks:
  - name: "iKuuuCheckin"
    schedule: "0 8 * * *"
    script: "tasks/ikuuu.py"
    description: "iKuuu 每日签到"
    enabled: true
    env:
      MY_EMAIL: "your_email@example.com"
      MY_PWD: "your_password"
```

---

### pttime.py

**功能：**
- 自动签到 PTTime 站点
- 获取签到天数和魔力值信息
- 支持代理配置

**环境变量：**
- `PTTIME_COOKIE`: 登录 cookie（必需）
- `PTTIME_UID`: 用户 ID（必需）
- `PTTIME_PROXY`: 代理地址，格式为 `host:port` 或 `user:pass@host:port`（可选）

**配置示例：**
```yaml
tasks:
  - name: "PTTimeCheckin"
    schedule: "0 9 * * *"
    script: "tasks/pttime.py"
    description: "PTTime 每日签到"
    enabled: true
    env:
      PTTIME_COOKIE: "your_cookie_here"
      PTTIME_UID: "12345"
      PTTIME_PROXY: "http://127.0.0.1:7890"  # 可选
```

---

### smzdm.py

**功能：**
- 自动签到获取奖励
- 显示金币、碎银、等级信息

**环境变量：**
- `SMZDM_COOKIE`: 登录 cookie（必需）

**配置示例：**
```yaml
tasks:
  - name: "SMZDMCheckin"
    schedule: "0 10 * * *"
    script: "tasks/smzdm.py"
    description: "什么值得买每日签到"
    enabled: true
    env:
      SMZDM_COOKIE: "your_cookie_here"
```

---

### tieba.py

**功能：**
- 自动签到所有关注的贴吧
- 显示签到统计信息

**环境变量：**
- `TIEBA_COOKIE`: 登录 cookie，需包含 `BDUSS`（必需）

**配置示例：**
```yaml
tasks:
  - name: "TiebaCheckin"
    schedule: "0 11 * * *"
    script: "tasks/tieba.py"
    description: "百度贴吧每日签到"
    enabled: true
    env:
      TIEBA_COOKIE: "BDUSS=xxx; other=value"
```

---

### fnclub.py

**功能：**
- 自动签到飞牛论坛
- 获取打卡动态信息

**环境变量：**
- `FNNAS_COOKIE`: 登录 cookie（必需）

**配置示例：**
```yaml
tasks:
  - name: "FNNASCheckin"
    schedule: "0 12 * * *"
    script: "tasks/fnclub.py"
    description: "飞牛Nas论坛每日签到"
    enabled: true
    env:
      FNNAS_COOKIE: "your_cookie_here"
```

---

### aliyunpan.py

**功能：**
- 自动签到阿里云盘
- 获取签到奖励

**环境变量：**
- `ALIYUN_REFRESH_TOKEN`: 阿里云盘 refresh token（必需）

**配置示例：**
```yaml
tasks:
  - name: "AliyunPanCheckin"
    schedule: "0 13 * * *"
    script: "tasks/aliyunpan.py"
    description: "阿里云盘每日签到"
    enabled: true
    env:
      ALIYUN_REFRESH_TOKEN: "your_refresh_token_here"
```

---

### bilibili.py

**功能：**
- B站漫画签到
- B站直播签到
- 视频投币任务
- 观看视频任务
- 分享视频任务
- 银瓜子换硬币
- 领取大会员权益

**环境变量：**
- `BILIBILI_COOKIE`: B站登录 Cookie（必需，格式: `key1=value1; key2=value2`）
- `COIN_NUM`: 每日投币数量（默认5）
- `COIN_TYPE`: 投币类型（1=关注用户视频，其他=分区视频，默认1）
- `SILVER2COIN`: 是否兑换银瓜子为硬币（true/false，默认false）
- `RECEIVE_VIP_PRIVILEGE`: 是否领取大会员权益（true/false，默认false）

**配置示例：**
```yaml
tasks:
  - name: "BilibiliDaily"
    schedule: "0 14 * * *"
    script: "tasks/bilibili.py"
    description: "B站每日任务"
    enabled: true
    env:
      BILIBILI_COOKIE: "SESSDATA=xxx; bili_jct=xxx"
      COIN_NUM: "5"
      COIN_TYPE: "1"
      SILVER2COIN: "true"
      RECEIVE_VIP_PRIVILEGE: "true"
```

---

### v2ex.py

**功能：**
- 自动登录 V2EX 论坛
- 执行每日签到获取金币
- 获取用户信息（用户名、余额、连续签到天数）

**环境变量：**
- `V2EX_COOKIE`: V2EX 登录 Cookie（必需，格式: `key1=value1; key2=value2`）
- `V2EX_PROXY`: 代理服务器地址（可选，如 `http://127.0.0.1:7890`）
- `V2EX_SSL_VERIFY`: 是否验证 SSL 证书（可选，true/false，默认false）

**配置示例：**
```yaml
tasks:
  - name: "V2EXCheckin"
    schedule: "0 15 * * *"
    script: "tasks/v2ex.py"
    description: "V2EX 每日签到"
    enabled: true
    env:
      V2EX_COOKIE: "A2=xxx; PB3_SESSION=xxx"
      V2EX_PROXY: "http://127.0.0.1:7890"  # 可选
```

---

### nodeseek.py

**功能：**
- 自动签到 NodeSeek 论坛
- 获取鸡腿奖励信息
- 支持随机/固定鸡腿模式

**环境变量：**
- `NODESEEK_COOKIE`: 登录 cookie（必需）
- `NODESEEK_RANDOM`: 是否随机鸡腿，true/false（可选，默认 true）
- `NODESEEK_PROXY`: 代理地址，格式为 `host:port` 或 `user:pass@host:port`（可选）

**依赖：**
- `curl_cffi`: 用于模拟浏览器请求，绕过反爬虫

**配置示例：**
```yaml
tasks:
  - name: "NodeSeekCheckin"
    schedule: "0 16 * * *"
    script: "tasks/nodeseek.py"
    description: "NodeSeek 每日签到"
    enabled: true
    env:
      NODESEEK_COOKIE: "your_cookie_here"
      NODESEEK_RANDOM: "true"  # 可选，true=随机鸡腿，false=固定5个鸡腿
      NODESEEK_PROXY: "http://127.0.0.1:7890"  # 可选
```

---

## 如何获取 Cookie

### 通用方法

1. 使用 Chrome 或 Edge 浏览器登录目标网站
2. 按 `F12` 打开开发者工具
3. 切换到 **Network/网络** 标签
4. 刷新页面，找到任意请求
5. 在请求头中找到 `Cookie` 字段
6. 复制整个 Cookie 字符串

### 注意事项

- Cookie 通常包含会话信息，可能有时效性
- 建议定期更新 Cookie 以保持签到正常
- 部分网站可能需要特定的 Cookie 字段，请参考各脚本的文档字符串

---

## 添加新脚本

如需添加新的签到脚本，请参考以下步骤：

1. 在 `tasks/` 目录下创建新的 Python 文件
2. 参考现有脚本的结构编写代码
3. 添加详细的文档字符串（功能描述、环境变量说明）
4. 在 `config.yml` 中添加任务配置
5. 测试脚本：`python tasks/your_script.py`

**脚本模板：**

```python
#!/usr/bin/env python3
"""
站点名称 自动签到任务

功能：
- 功能1
- 功能2

环境变量：
- ENV_VAR1: 说明（必需）
- ENV_VAR2: 说明（可选）
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from logger import log_info, log_success, log_error, log_warning, log_debug


def main():
    """主函数"""
    log_info("🚀 任务开始")
    # 实现签到逻辑
    log_success("✅ 签到成功")
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

