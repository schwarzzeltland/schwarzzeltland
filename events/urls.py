from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('trip', views.trip, name='trip'),
    path('trip/delete/<int:pk>/', views.delete_trip, name='delete_trip'),
    path('trip/edit/<int:pk>/', views.edit_trip, name='edit_trip'),
    path('trip/edit/', views.edit_trip, name='edit_trip'),
    path('trip/show/<int:pk>/', views.show_trip, name='show_trip'),
    path('trip/check_trip_material/<int:pk>/', views.check_trip_material, name='check_trip_material'),
    path('location', views.location, name='location'),

]
