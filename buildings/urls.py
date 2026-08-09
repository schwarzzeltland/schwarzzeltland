from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('construction', views.constructions, name='constructions'),
    path('material', views.material, name='material'),
    path('material/edit/<int:pk>/', views.edit_material, name='edit_material'),
    path('material/create', views.create_material, name='create_material'),
    path('construction/edit/<int:pk>/', views.edit_construction, name='edit_constructions'),
    path('construction/edit/', views.edit_construction, name='edit_constructions'),
    path('construction/check_material/<int:pk>/', views.check_material, name='check_material'),
    path('construction/delete/<int:pk>/', views.delete_construction, name='delete_construction'),
    path('construction/show/<int:pk>/', views.show_construction, name='show_construction'),
    path('material/delete/<int:pk>/', views.delete_material, name='delete_material'),
    path('material/show/<int:pk>/', views.show_material, name='show_material'),
    path('material/containers/', views.material_container_list, name='material_container_list'),
    path('material/containers/create/', views.material_container_create, name='material_container_create'),
    path('material/containers/<int:pk>/', views.material_container_detail, name='material_container_detail'),
    path('material/containers/<int:pk>/edit/', views.material_container_edit, name='material_container_edit'),
    path('material/containers/<int:pk>/delete/', views.material_container_delete, name='material_container_delete'),
    path('material/containers/<int:pk>/qr/', views.material_container_qr, name='material_container_qr'),
    path('material/containers/qr-sheet/', views.material_container_qr_sheet, name='material_container_qr_sheet'),
    path('material/scan/<uuid:scan_code>/', views.material_container_scan, name='material_container_scan'),
]
