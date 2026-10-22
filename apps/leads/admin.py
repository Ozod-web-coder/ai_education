from django.contrib import admin

from .models import Lead


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = (
        "__str__", "center", "phone", "telegram", "age", "declared_level", "assessed_level", "status", "created_at"
    )
    list_filter = ("center", "status", "assessed_level", "source")
    search_fields = ("name", "phone", "parent_phone", "user__telegram_username")
    list_select_related = ("center", "user")
    readonly_fields = ("telegram", "personal_data_consent_at", "parent_consent_at", "created_at", "updated_at")

    @admin.display(description="Telegram")
    def telegram(self, lead):
        if not lead.user:
            return "—"
        return f"@{lead.user.telegram_username}" if lead.user.telegram_username else f"id {lead.user.telegram_id}"
