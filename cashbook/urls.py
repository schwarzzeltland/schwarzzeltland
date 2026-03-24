from django.urls import path

from cashbook import views


urlpatterns = [
    path("cashbooks/", views.cashbook_list, name="cashbook_list"),
    path("cashbooks/create/", views.cashbook_create, name="cashbook_create"),
    path("cashbooks/export/summary/", views.cashbook_export_summary_csv, name="cashbook_export_summary_csv"),
    path("cashbooks/<int:pk>/", views.cashbook_detail, name="cashbook_detail"),
    path("cashbooks/<int:pk>/edit/", views.cashbook_edit, name="cashbook_edit"),
    path("cashbooks/<int:pk>/delete/", views.cashbook_delete, name="cashbook_delete"),
    path("cashbooks/<int:pk>/export/csv/", views.cashbook_export_csv, name="cashbook_export_csv"),
    path("cashbooks/<int:pk>/export/receipts-zip/", views.cashbook_export_receipts_zip, name="cashbook_export_receipts_zip"),
    path("cashbooks/autocomplete/category/", views.cashbook_category_autocomplete, name="cashbook_category_autocomplete"),
    path("cashbooks/<int:cashbook_pk>/entries/create/", views.cashbook_entry_create, name="cashbook_entry_create"),
    path("cashbooks/<int:cashbook_pk>/entries/<int:pk>/edit/", views.cashbook_entry_edit, name="cashbook_entry_edit"),
    path("cashbooks/<int:cashbook_pk>/entries/<int:pk>/delete/", views.cashbook_entry_delete, name="cashbook_entry_delete"),
]
