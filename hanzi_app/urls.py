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
    path('import/', views.import_data, name='import_data'),
    path('export/', views.export_data, name='export_data'),
    path('download/<str:filename>/', views.download_file, name='download_file'),
    path('clear-selected/', views.clear_selected, name='clear_selected'),
]