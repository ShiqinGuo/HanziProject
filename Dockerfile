FROM python:3.9-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    default-libmysqlclient-dev \
    fonts-wqy-zenhei \  # 基础中文字体
    # 新增字体配置
    && mkdir -p /usr/share/fonts/custom \
    && cp simkai.ttf /usr/share/fonts/custom/ \
    && fc-cache -f -v
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 收集静态文件
RUN python manage.py collectstatic --noinput

# 设置字体环境
ENV FONTCONFIG_PATH=/etc/fonts

# 启动命令
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "hanzi_project.wsgi:application"]