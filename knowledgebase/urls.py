from django.urls import path
from . import views

urlpatterns = [
    path('recipes', views.recipes, name='recipes'),
    path('recipes/new/', views.new_recipe, name='new_recipe'),
    path('recipes/my_recipes/', views.my_recipes, name='my_recipes'),
    path('recipes/public_recipes/', views.public_recipes, name='public_recipes'),
    path('recipes/tag-autocomplete/', views.tag_autocomplete, name='tag_autocomplete'),
    path('recipes/show_public_recipe/<int:pk>/', views.show_public_recipe, name='show_public_recipe'),
    path('recipes/show_my_recipe/<int:pk>/', views.show_my_recipe, name='show_my_recipe'),
    path('recipes/copy_public_recipe/<int:pk>/', views.copy_public_recipe, name='copy_public_recipe'),
    path('recipes/edit/<int:pk>/', views.edit_recipe, name='edit_recipe'),
    path('recipes/delete/<int:pk>/', views.delete_recipe, name='delete_recipe'),
]
