from django.contrib import admin

from .models import Conversation, FaqItem, Message


@admin.register(FaqItem)
class FaqItemAdmin(admin.ModelAdmin):
    list_display = ("question", "center", "language", "is_active")
    list_filter = ("center", "language", "is_active")
    search_fields = ("question", "answer")


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    can_delete = False
    fields = ("created_at", "role", "content", "tool_calls")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("lead", "center", "started_at", "updated_at")
    list_filter = ("center",)
    search_fields = ("lead__name", "lead__phone")
    readonly_fields = ("center", "lead", "started_at", "updated_at")
    inlines = [MessageInline]
