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
| [bilibili.py](#bilibilipy) | B站多功能签到 | `BILIBILI_COOKIE` | `COIN_NUM`, `SKIP_COIN`, `SKIP_SHARE`, `SILVER2COIN`, `RECEIVE_VIP_PRIVILEGE`, `LIVE_ROOM_DANMU`, `LIVE_DANMU_MSG` |
| [v2ex.py](#v2expy) | V2EX 论坛自动签到 | `V2EX_COOKIE` | `V2EX_PROXY`, `V2EX_SSL_VERIFY` |
| [nodeseek.py](#nodeseekpy) | NodeSeek 论坛自动签到 | `NODESEEK_COOKIE` | `NODESEEK_RANDOM`, `NODESEEK_PROXY` |
| [zhutix.py](#zhutixpy) | 致美化网站自动签到 | `ZHUTIX_COOKIE` | `ZHUTIX_PROXY` |

> 💡 **代理共享**：多个脚本需要使用同一代理时，可在 `config.yml` 顶部用 YAML 锚点声明一次，下方任务通过 `*proxy` 引用。详见 [共享代理配置](#共享代理配置)。

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
      PTTIME_PROXY: *proxy  # 引用共享代理（可选）
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
- 登录奖励（+5 EXP）
- 观看视频任务（+5 EXP，使用 heartbeat 心跳上报）
- 分享视频任务（+5 EXP）
- 投币任务（每枚 +10 EXP，最多 5 枚 = 50 EXP）
- 直播间弹幕签到（可选，发送弹幕完成直播任务）
- 银瓜子换硬币（可选）
- 领取大会员权益（可选，基于 vipStatus 判定）

**实现要点：**
- 从 `BILIBILI_COOKIE` 中提取 `SESSDATA` 和 `bili_jct` 双字段独立使用，兼容 `;` 和 `; ` 两种分隔符，规避 cookie 字符串分隔符差异导致的 CSRF 解析失败问题
- 通过 `/x/member/web/exp/reward` 预检查任务状态，已完成任务自动跳过
- 观看任务改用 popular 接口获取视频（含真实 cid）+ heartbeat 心跳上报
- 大会员判定基于 `vipStatus`（生效中），覆盖月度/年度两种类型
- 所有响应统一 None 安全处理，避免 `'NoneType' object has no attribute 'get'`

**环境变量：**
- `BILIBILI_COOKIE`: B站登录 Cookie（必需，需包含 `SESSDATA` 和 `bili_jct`）
- `COIN_NUM`: 每日投币数量（默认5）
- `SKIP_COIN`: 是否跳过投币任务（true/false，默认false，节省硬币）
- `SKIP_SHARE`: 是否跳过分享任务（true/false，默认false）
- `SILVER2COIN`: 是否兑换银瓜子为硬币（true/false，默认false）
- `RECEIVE_VIP_PRIVILEGE`: 是否领取大会员权益（true/false，默认false）
- `LIVE_ROOM_DANMU`: 直播间弹幕签到 room_id，多个用逗号分隔（可选）
- `LIVE_DANMU_MSG`: 弹幕内容（默认"签到"）

**依赖：**
- `requests`

**配置示例：**
```yaml
tasks:
  - name: "Bilibili"
    schedule: "0 8 * * *"
    script: "tasks/bilibili.py"
    description: "B站每日任务"
    enabled: true
    env:
      BILIBILI_COOKIE: "SESSDATA=xxx; bili_jct=xxx; DedeUserID=xxx"
      COIN_NUM: "5"
      SKIP_COIN: "false"
      SKIP_SHARE: "false"
      SILVER2COIN: "false"
      RECEIVE_VIP_PRIVILEGE: "false"
      # LIVE_ROOM_DANMU: "30858592,22637261"  # 可选
      # LIVE_DANMU_MSG: "签到"                 # 可选
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
      V2EX_PROXY: *proxy  # 引用共享代理（可选）
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
      NODESEEK_PROXY: *proxy   # 引用共享代理（可选）
```

---

### zhutix.py

**功能：**
- 自动签到致美化网站
- 获取锋币奖励信息
- 获取连续签到天数
- 自动识别"已签到/未到签到时间"状态，不误报失败

**环境变量：**
- `ZHUTIX_COOKIE`: 登录 Cookie（必需，格式: `key1=value1; key2=value2`）
  - 必须包含名为 `b2_token` 的字段，否则接口返回 403。建议在浏览器登录后从开发者工具复制「全部 Cookie」（含 `b2_token`），而非仅复制 `wordpress_logged_in` 等字段。
- `ZHUTIX_PROXY`: 代理服务器地址（可选，如 `http://127.0.0.1:7890`）

**依赖：**
- `curl_cffi`: 用于模拟浏览器请求，绕过反爬虫

**状态码说明：**
致美化 B2 主题 `userMission` 接口可能返回简单状态码：
- 正常 dict → 签到成功，包含锋币奖励信息
- `3` → 今日已签到（不算失败）
- `1` → 未到签到时间，签到周期尚未重置（不算失败）
- 其他未知响应 → 按失败处理，触发通知

**配置示例：**
```yaml
tasks:
  - name: "ZhuTiX"
    schedule: "0 11 * * *"
    script: "tasks/zhutix.py"
    description: "致美化网站签到"
    enabled: true
    env:
      ZHUTIX_COOKIE: "your_cookie_here"
      ZHUTIX_PROXY: *proxy  # 引用共享代理（可选）
```

> ⚠️ **注意**：致美化签到周期并非凌晨 0 点重置，建议把执行时间设置在上午（如 11:00），避免凌晨触发时服务器尚未重置签到周期。

---

## 共享代理配置

多个脚本需要使用同一代理时，可在 `config.yml` 顶部用 YAML 锚点声明一次，下方任务通过 `*proxy` 引用。修改代理只需改一处，所有引用处自动生效。

```yaml
# 顶部声明（只需一次）
proxy: &proxy
  http://127.0.0.1:7890

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

**说明：**
- `&proxy` 定义锚点（名字可自定义，如 `&my_proxy`）
- `*proxy` 引用锚点，YAML 解析时会被替换为实际值
- 不使用代理时，注释掉顶部的 `proxy:` 字段，并删除任务中对应的 `*_PROXY: *proxy` 行
- 锚点只能作为独立的值出现，不能用在字符串拼接里（如 `prefix *proxy` 不会被替换）
- 需要不同代理时，可声明多个锚点（如 `&proxy`、`&proxy_us`）

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
- Cookie 字符串过长时，可在 YAML 中用双引号跨行或 `>-` 折叠块写法提高可读性（YAML 会自动将换行折叠为空格）

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

