from django import template

register = template.Library()

@register.filter
def split(value, arg):
    """将字符串按指定分隔符分割为列表"""
    return value.split(arg)

@register.filter
def strip(value):
    """移除字符串两端的空白字符"""
    return value.strip() 