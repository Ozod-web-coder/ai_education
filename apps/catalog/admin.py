from django.contrib import admin

from .models import Course, Group, GroupSlot


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("name", "center", "subject", "price_per_month", "is_active")
    list_filter = ("center", "subject", "is_active")


class GroupSlotInline(admin.TabularInline):
    model = GroupSlot
    extra = 2


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "center", "course", "branch", "level", "capacity", "start_date", "is_active")
    list_filter = ("center", "branch", "level", "is_active")
    search_fields = ("name", "teacher_name")
    inlines = [GroupSlotInline]
