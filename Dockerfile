FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（清理缓存 + 不安装推荐包）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    cron \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Python 依赖层
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用文件层
COPY src/ ./
COPY tasks/ ./tasks/

# 设置权限并创建日志目录
RUN chmod +x entrypoint.sh logger.sh

ENTRYPOINT ["./entrypoint.sh"]
