from django.contrib.auth import views as auth_views
from django.urls import path

from main import views

urlpatterns = [
    path('home', views.home_view, name='home'),
    path('contacts', views.contacts_view, name='contacts'),
    path('privacypolice', views.privacypolice_view, name='privacypolice'),
    path('disclaimer', views.disclaimer_view, name='disclaimer'),
    path('impressum', views.impressum_view, name='impressum'),
    path('help', views.help_view, name='help'),
    path('login/', auth_views.LoginView.as_view(template_name='main/login.html'), name='login'),
]
