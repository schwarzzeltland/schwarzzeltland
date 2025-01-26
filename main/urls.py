from django.contrib.auth import views as auth_views
from django.urls import path, include

from main import views

urlpatterns = [
    path('home', views.home_view, name='home'),
    path('organization', views.organization_view, name='organization'),
    path('create_organization', views.create_organization, name='create_organization'),
    path('change_admin/<int:pk>/', views.change_admin, name='change_admin'),
    path('change_material_manager/<int:pk>/', views.change_material_manager, name='change_material_manager'),
    path('change_event_manager/<int:pk>/', views.change_event_manager, name='change_event_manager'),
    path('delete_membership/<int:pk>/', views.delete_membership, name='delete_membership'),
    path('add_user', views.add_user, name='add_user'),
    path('contacts', views.contacts_view, name='contacts'),
    path('privacypolice', views.privacypolice_view, name='privacypolice'),
    path('disclaimer', views.disclaimer_view, name='disclaimer'),
    path('impressum', views.impressum_view, name='impressum'),
    path('help', views.help_view, name='help'),
    path('login/', auth_views.LoginView.as_view(template_name='main/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='main/password_reset_form.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='main/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='main/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='main/password_reset_complete.html'), name='password_reset_complete'),
    path('register', views.register, name='register'),
    path('activate/<uidb64>/<token>/', views.activate, name='activate'),
    path('register/email_verification/', views.email_verification, name='email_verification'),
    path('invalid_activationlink/', views.invalid_activation_link, name='invalid_activation_link'),
]
