from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Branch, Center, User


class BranchInline(admin.TabularInline):
    model = Branch
    extra = 0


@admin.register(Center)
class CenterAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "default_language", "is_active", "created_at")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [BranchInline]


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "center", "address", "is_active")
    list_filter = ("center", "is_active")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "first_name", "telegram_username", "phone", "telegram_id", "center", "is_staff")
    list_filter = ("is_staff", "is_superuser", "is_active", "center")
    search_fields = ("username", "first_name", "telegram_username", "phone")
    ordering = ("-date_joined",)
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Профиль", {"fields": ("first_name", "telegram_id", "telegram_username", "phone", "language", "center")}),
        ("Права", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Даты", {"fields": ("last_login", "date_joined")}),
    )
