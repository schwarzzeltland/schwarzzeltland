from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('trip', views.trip, name='trip'),
    path('location', views.location, name='location'),

]
