# 这确保应用在Django启动时导入
from .celery import app as celery_app

__all__ = ('celery_app',)
