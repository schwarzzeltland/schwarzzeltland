from django.contrib.auth import views as auth_views
from django.urls import path

from main import views

urlpatterns = [
    path('home', views.home_view, name='home'),
    path('organization', views.organization_view, name='organization'),
    path('change_admin/<int:pk>/', views.change_admin, name='change_admin'),
    path('change_material_manager/<int:pk>/', views.change_material_manager, name='change_material_manager'),
    path('delete_membership/<int:pk>/', views.delete_membership, name='delete_membership'),
    path('add_user', views.add_user, name='add_user'),
    path('contacts', views.contacts_view, name='contacts'),
    path('privacypolice', views.privacypolice_view, name='privacypolice'),
    path('disclaimer', views.disclaimer_view, name='disclaimer'),
    path('impressum', views.impressum_view, name='impressum'),
    path('help', views.help_view, name='help'),
    path('login/', auth_views.LoginView.as_view(template_name='main/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]
