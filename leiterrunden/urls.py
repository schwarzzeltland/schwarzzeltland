from django.urls import path

from leiterrunden import views


urlpatterns = [
    path("leiterrunden/protokolle/", views.meeting_minutes_list, name="meeting_minutes_list"),
    path("leiterrunden/protokolle/erstellen/", views.meeting_minutes_create, name="meeting_minutes_create"),
    path("leiterrunden/protokolle/<int:pk>/", views.meeting_minutes_detail, name="meeting_minutes_detail"),
    path("leiterrunden/protokolle/<int:pk>/bearbeiten/", views.meeting_minutes_edit, name="meeting_minutes_edit"),
    path("leiterrunden/protokolle/<int:pk>/duplizieren/", views.meeting_minutes_duplicate, name="meeting_minutes_duplicate"),
    path("leiterrunden/protokolle/<int:pk>/aendern/", views.meeting_minutes_revise, name="meeting_minutes_revise"),
    path("leiterrunden/protokolle/<int:pk>/annehmen/", views.meeting_minutes_accept, name="meeting_minutes_accept"),
    path("leiterrunden/protokolle/<int:pk>/loeschen/", views.meeting_minutes_delete, name="meeting_minutes_delete"),
    path("leiterrunden/protokolle/<int:pk>/export/pdf/", views.meeting_minutes_pdf, name="meeting_minutes_pdf"),
]
