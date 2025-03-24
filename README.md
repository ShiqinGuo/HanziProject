# 汉字管理系统 🀄

汉字管理系统提供汉字的增删改查、笔画搜索、图像比较等功能，支持教师管理汉字资源的各种需求。

## 📋 目录

    - [项目概述](#项目概述)
    - [功能特性](#功能特性)
    - [技术架构](#技术架构)
    - [项目结构](#项目结构)
    - [安装部署](#安装部署)
    - [功能详解](#功能详解)
    - [数据模型](#数据模型)
    - [API接口](#api接口)
    - [性能优化](#性能优化)
    - [配置说明](#配置说明)
    - [贡献指南](#贡献指南)
    - [许可证](#许可证)

## 📝 项目概述

汉字教学管理系统旨在提供一个高效、用户友好的平台，用于汉字的管理、学习和教学。系统集成了多种先进技术，如OCR识别、图像相似度比较、汉字笔画分析等，为用户提供全方位的汉字学习体验。

## ✨ 功能特性

### 核心功能

1. **汉字管理**
   - 添加新汉字记录
   - 编辑已有汉字信息
   - 查看汉字详细信息
   - 删除汉字记录

2. **汉字搜索**
   - 基于多条件的汉字搜索
   - 笔画数量搜索
   - 部首搜索
   - 拼音搜索
   - 结构搜索

3. **笔画查询与学习**
   - 汉字笔画顺序展示
   - 笔画数量统计
   - 笔画类型分析

4. **数据导入导出**
   - 批量导入汉字数据
   - 导出汉字数据为多种格式

5. **图像处理与比较**
   - 汉字图像识别
   - 用户书写与标准汉字比较
   - 相似度分析

## 🔧 技术架构

### 后端技术栈

- **框架**: Django 4.2.11
- **数据库**: MySQL
- **缓存**: Redis
- **图像处理**: OpenCV, PIL
- **OCR识别**: EasyOCR
- **深度学习**: PyTorch, TorchVision
- **异步任务**: Concurrent Futures

### 前端技术栈

- **语言**: HTML5, CSS3, JavaScript
- **框架**: jQuery
- **UI组件**: Bootstrap
- **图表**: Chart.js
- **动画**: CSS动画, SVG

### 部署环境

- Docker & Docker Compose
- Nginx
- Gunicorn
- MySQL

## 📁 项目结构

    ```
    hanzi_project/
    │
    ├── hanzi_app/                     # 主应用目录
    │   ├── migrations/                # 数据库迁移文件
    │   ├── static/                    # 应用静态文件
    │   ├── templates/                 # HTML模板
    │   ├── templatetags/              # 自定义模板标签
    │   ├── admin.py                   # 管理界面配置
    │   ├── forms.py                   # 表单定义
    │   ├── generate.py                # 生成标准汉字图像
    │   ├── models.py                  # 数据模型定义
    │   ├── performance_tests.py       # 性能测试脚本
    │   ├── recognition.py             # 汉字识别模块
    │   ├── urls.py                    # URL路由配置
    │   └── views.py                   # 视图函数
    │
    ├── hanzi_project/                 # 项目核心配置
    │   ├── asgi.py                    # ASGI配置
    │   ├── settings.py                # 项目设置
    │   ├── urls.py                    # 项目URL配置
    │   └── wsgi.py                    # WSGI配置
    │
    ├── data/                          # 数据文件目录
    │   ├── ch_match/                  # 汉字匹配数据
    │   ├── upload/                    # 上传的数据
    │   └── 提交数据集含答案/           # 测试数据集
    │
    ├── media/                         # 媒体文件目录
    │   └── standard_images/           # 标准汉字图像
    │
    ├── staticfiles/                   # 收集的静态文件
    │
    ├── templates/                     # 全局模板
    │
    ├── Strokes.txt                    # 汉字笔画数据
    ├── compare.py                     # 图像比较工具
    ├── manage.py                      # Django管理脚本
    ├── requirements.txt               # 项目依赖
    ├── .gitignore                     # Git忽略配置
    └── README.md                      # 项目说明
    ```

## 🚀 安装部署

### 系统要求

- Python 3.8+
- MySQL 8.0+
- Redis 6.0+
- 足够的磁盘空间用于存储汉字图像
- 推荐8GB以上RAM (使用深度学习模型时)

### 使用Docker部署

1. 克隆项目仓库

        ```bash
        git clone https://github.com/ShiqinGuo/hanzi_project.git
        cd hanzi_project
        ```

2. 使用Docker Compose构建并启动服务

        ```bash
        docker-compose up --build
        ```

### 手动部署

1. 克隆项目仓库

        ```bash
        git clone https://github.com/ShiqinGuo/hanzi_project.git
        cd hanzi_project
        ```

2. 创建并激活虚拟环境

        ```bash
        python -m venv venv
        source venv/bin/activate  # Linux/Mac
        venv\Scripts\activate  # Windows
        ```

3. 安装依赖

        ```bash
        pip install -r requirements.txt
        ```

4. 配置数据库

        ```bash
        # 修改settings.py中的数据库设置
        python manage.py migrate
        ```

5. 创建超级用户

        ```bash
        python manage.py createsuperuser
        ```

6. 收集静态文件

        ```bash
        python manage.py collectstatic
        ```

7. 运行服务器

        ```bash
        python manage.py runserver
        ```

## 📚 功能详解

### 1. 汉字管理

#### 添加汉字 (add.html)

- **路径**: `/add/`
- **功能**: 添加新汉字记录至系统
- **实现**: 通过表单收集汉字信息，包括字符、拼音、笔画数、部首等
- **处理流程**:
  1. 用户填写汉字信息表单
  2. 系统验证输入数据有效性
  3. 保存汉字信息到数据库
  4. 自动生成汉字标准图像

#### 查看汉字详情 (detail.html)

- **路径**: `/detail/<hanzi_id>/`
- **功能**: 查看单个汉字的详细信息
- **实现**: 展示汉字的所有属性，包括标准图像、笔画顺序、拼音等
- **特性**:
  - 编辑与删除选项

#### 编辑汉字 (edit.html)

- **路径**: `/edit/<hanzi_id>/`
- **功能**: 修改已有汉字信息
- **实现**: 预填充表单，允许用户修改字段，更新数据库
- **安全措施**: CSRF保护，表单验证

### 2. 汉字搜索 (index.html)

- **路径**: `/`
- **功能**: 系统首页，提供多条件汉字搜索
- **搜索条件**:
  - 汉字字符
  - 拼音
  - 笔画数范围
  - 部首
  - 结构类型
- **实现**:
  - 基于模型Manager自定义查询方法
  - 分页显示结果
  - AJAX动态加载

### 3. 笔画搜索 (stroke_search.html)

- **路径**: `/stroke_search/`
- **功能**: 根据笔画特征搜索汉字
- **实现**:
  - 基于Strokes.txt文件的笔画数据
  - 交互式笔画输入界面
  - 实时匹配
- **特性**:
  - 可视化笔画输入检索
  - 笔画类型过滤

### 4. 数据导入 (import.html)

- **路径**: `/import/`
- **功能**: 批量导入汉字数据
- **支持格式**: JSON
- **实现**:
  - 文件上传处理
  - 数据解析与验证
  - 批量保存到数据库
- **安全措施**:
  - 文件类型验证
  - 大小限制
  - 数据完整性检查

### 5. 图像比较功能 (compare.py)

- **功能**: 比较用户手写汉字与标准汉字的相似度
- **实现**:
  - 使用PyTorch深度学习模型提取特征
  - 计算特征向量余弦相似度
  - 返回相似度评分
- **应用场景**:
  - 汉字书写评估
  - 字形相似度分析
  - 汉字识别辅助

### 6. 汉字识别 (recognition.py)

- **功能**: OCR识别图片中的汉字
- **实现**:
  - 使用EasyOCR引擎
  - 图像预处理增强识别率
  - 结果验证与后处理
- **性能优化**:
  - 批量处理
  - 多线程异步处理

## 💾 数据模型

### Hanzi模型

    ```python
        class Hanzi(models.Model):
        STRUCTURE_CHOICES = [
                ('未知结构', '未知结构'),
                ('左右结构', '左右结构'),
                ('上下结构', '上下结构'),
                ('包围结构', '包围结构'),
                ('独体结构', '独体结构'),
                ('品字结构', '品字结构'),
                ('穿插结构', '穿插结构'),
        ]
        VARIANT_CHOICES = [
                ('简体', '简体'),
                ('繁体', '繁体'),
        ]
        LEVEL_CHOICES = [
                ('A', 'A'),
                ('B', 'B'),
                ('C', 'C'),
        ]

        id = models.CharField('编号', primary_key=True, max_length=5)
        character = models.CharField('汉字', max_length=1)  
        image_path = models.CharField('图片路径', max_length=255)
        stroke_count = models.IntegerField('笔画数')
        structure = models.CharField('结构类型', max_length=20, choices=STRUCTURE_CHOICES, default='未知结构')
        stroke_order = models.CharField('笔顺', max_length=100, blank=True, null=True)
        pinyin = models.CharField('拼音', max_length=50, blank=True, null=True)
        level = models.CharField('等级', max_length=1, choices=LEVEL_CHOICES)
        comment = models.TextField('评语', blank=True, null=True)
        variant = models.CharField('简繁体', max_length=10, choices=VARIANT_CHOICES, default='简体')
        standard_image = models.CharField('标准图片路径', max_length=255, blank=True, null=True)
        crt_time = models.DateTimeField('创建时间', auto_now_add=True)
        upd_time = models.DateTimeField('更新时间', auto_now=True)

        class Meta:
                managed = True  # 启用迁移管理
                db_table = 'hanzi'
                verbose_name = '汉字数据'
                verbose_name_plural = '汉字数据'
    ```

## 🔌 API接口

### 1. 笔画数接口

- **URL**: `/api/stroke_count/<char>/`
- **方法**: GET
- **功能**: 获取指定汉字的笔画数
- **返回格式**: JSON
- **缓存**: 15分钟

### 2. 汉字添加接口

- **URL**: `/api/add_hanzi/`
- **方法**: POST
- **功能**: 添加新汉字
- **参数**: character, pinyin, stroke_count等
- **安全**: CSRF豁免(需前端认证)

### 3. 笔画搜索接口

- **URL**: `/api/stroke_search/`
- **方法**: POST
- **功能**: 根据笔画特征搜索汉字
- **参数**: stroke_types(笔画类型数组)
- **返回**: 匹配汉字列表

## 🚄 性能优化

1. **数据库优化**
   - 字段索引(character, pinyin, stroke_count)
   - 查询优化

2. **缓存策略**
   - 笔画数API结果缓存(15分钟)
   - 会话缓存(24小时)
   - 页面缓存

3. **图像处理优化**
   - 异步生成标准图像
   - 多线程处理批量图像
   - 图像压缩与格式优化

4. **前端性能**
   - 静态资源压缩
   - 懒加载图像
   - AJAX分页减少页面刷新

## ⚙️ 配置说明

### 关键配置项

1. **数据库配置**

        ```python
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.mysql',
                'NAME': 'hanzi_db',
                'USER': 'hanzi_user',
                'PASSWORD': 'password',
                'HOST': 'db',
                'PORT': '3306',
            }
        }
        ```

2. **缓存配置**

        ```python
        CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                'LOCATION': 'redis://redis:6379/1',
            }
        }
        SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
        SESSION_CACHE_ALIAS = 'default'
        SESSION_COOKIE_AGE = 86400  # 24小时
        ```

3. **媒体和静态文件配置**

        ```python
        MEDIA_URL = '/media/'
        MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
        STATIC_URL = '/static/'
        STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
        ```

4. **安全配置**

        ```python
        # 开发环境设置
        if DEBUG:
            SECURE_SSL_REDIRECT = False
            SESSION_COOKIE_SECURE = False
            CSRF_COOKIE_SECURE = False
            SECURE_HSTS_SECONDS = 0
            SECURE_HSTS_INCLUDE_SUBDOMAINS = False
            SECURE_HSTS_PRELOAD = False
        ```

## 📞 联系方式

- 项目创建人: 郭士钦
- 电子邮件: <1158220122@stu.jiangnan.edu.cn>
- 项目链接: [GitHub](https://github.com/ShiqinGuo/hanzi_project)

---

🔄 最后更新: 2025年3月24日
