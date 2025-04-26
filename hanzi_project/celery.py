import os
from celery import Celery

# 设置django设置模块的默认值
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hanzi_project.settings')

# 创建Celery应用实例
app = Celery('hanzi_project')

# 使用字符串配置，这样worker不需要序列化配置对象
app.config_from_object('django.conf:settings', namespace='CELERY')

# 显式设置Redis作为broker和backend
app.conf.broker_url = 'redis://localhost:6379/0'
app.conf.result_backend = 'redis://localhost:6379/0'

# 从所有已注册的Django应用中加载任务模块
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}') 