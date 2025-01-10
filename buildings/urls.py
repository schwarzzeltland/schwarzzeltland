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
]
