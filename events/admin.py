from django.contrib import admin

from events.models import Trip


# Register your models here.
@admin.register(Trip)
class ConstructionAdmin(admin.ModelAdmin):
    model = Trip
    extra = 1