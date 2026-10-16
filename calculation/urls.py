from django.urls import path
from . import views

urlpatterns = [
    path("calculations/autocomplete/category/", views.calculation_category_autocomplete, name="calculation_category_autocomplete"),
    path("calculations/", views.calculation_list, name="calculation_list"),
    path("events/<int:trip_pk>/calculation/", views.calculation_detail, name="calculation_detail"),
    path("events/<int:trip_pk>/calculation/pdf/<str:report_type>/", views.calculation_export_pdf, name="calculation_export_pdf"),
    path("events/<int:trip_pk>/calculation/lines/<int:pk>/delete/", views.calculation_line_delete, name="calculation_line_delete"),
    path("events/<int:trip_pk>/calculation/lines/<int:pk>/edit/", views.calculation_line_edit, name="calculation_line_edit"),
    path("events/<int:trip_pk>/calculation/groups/create/", views.calculation_participant_group_edit, name="calculation_participant_group_create"),
    path("events/<int:trip_pk>/calculation/groups/<int:pk>/edit/", views.calculation_participant_group_edit, name="calculation_participant_group_edit"),
    path("events/<int:trip_pk>/calculation/groups/<int:pk>/delete/", views.calculation_participant_group_delete, name="calculation_participant_group_delete"),
    path("events/<int:trip_pk>/calculation/education/create/", views.calculation_education_edit, name="calculation_education_create"),
    path("events/<int:trip_pk>/calculation/education/<int:pk>/edit/", views.calculation_education_edit, name="calculation_education_edit"),
    path("subsidy-profiles/", views.subsidy_profile_list, name="subsidy_profiles"),
]
