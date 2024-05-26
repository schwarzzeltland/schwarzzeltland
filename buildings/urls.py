from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('construction', views.constructions, name='constructions'),
    path('material', views.material, name='material'),
    path('material/edit', views.edit_material, name='edit_material'),
    path('construction/edit', views.edit_construction, name='edit_constructions'),

]
