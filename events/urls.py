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
    path('location/edit/<int:pk>/', views.edit_location, name='edit_location'),
    path('location/edit/', views.edit_location, name='edit_location'),
    path('location/show/<int:pk>/', views.show_location, name='show_location'),
    path('location/delete/<int:pk>/', views.delete_location, name='delete_location'),
    path('trip/summary/<int:pk>/', views.construction_summary, name='construction_summary'),

]
