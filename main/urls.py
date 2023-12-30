from django.contrib.auth import views as auth_views
from django.urls import path

from main import views

urlpatterns = [
    path('main', views.main_view, name='main'),
]
