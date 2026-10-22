from django.contrib import admin

from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("lead", "group", "status", "trial_at", "expires_at", "confirmed_at", "created_at")
    list_filter = ("center", "status", "group__branch")
    search_fields = ("lead__name", "lead__phone", "group__name")
    raw_id_fields = ("lead", "group")
