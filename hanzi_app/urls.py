from django.urls import path
from . import views

app_name = 'hanzi_app'

urlpatterns = [
    path('', views.index, name='index'),
    path('hanzi/<str:hanzi_id>/', views.hanzi_detail, name='hanzi_detail'),
    path('get_stroke_count/<str:char>/', views.get_stroke_count, name='get_stroke_count'),
    path('generate_id/', views.generate_id, name='generate_id'),
    path('add/', views.add_hanzi, name='add'),
    path('delete/<str:hanzi_id>/', views.delete_hanzi, name='delete_hanzi'),
    path('edit/<str:hanzi_id>/', views.edit_hanzi, name='edit_hanzi'),
    path('update/<str:hanzi_id>/', views.update_hanzi, name='update_hanzi'),
    path('import/', views.import_view, name='import'),#返回导入页面 
    path('import-data/', views.import_data, name='import_data'),#提交导入任务
    path('import-data-view/', views.import_data_view, name='import_data_view'),#返回数据处理页面
    path('export/', views.export_hanzi, name='export_hanzi'),
    path('export-page/', views.export_page, name='export_page'),
    path('download/<str:filename>/', views.download_file, name='download_file'),
    path('clear-selected/', views.clear_selected, name='clear_selected'),
    path('get_stroke_order/<str:char>/', views.get_stroke_order_api, name='get_stroke_order_api'),
    path('stroke-search/', views.stroke_search, name='stroke_search'),
    path('cleanup_exports/', views.cleanup_exports, name='cleanup_exports'),
    path('delete_export_file/<str:filename>/', views.delete_export_file, name='delete_export_file'),
    path('api/logs/', views.capture_frontend_logs, name='capture_frontend_logs'),
    path('api/logs/delete/', views.delete_logs, name='delete_logs'),
    path('logs/', views.view_frontend_logs, name='view_frontend_logs'),
    path('check-import-status/', views.check_import_status, name='check_import_status'),
    path('delete-import-file/', views.delete_import_file, name='delete_import_file'),
    path('check-import-task/', views.check_import_task, name='check_import_task'),
]