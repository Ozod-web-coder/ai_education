from django.contrib import admin

from .models import Question, TestAnswer, TestSession, WritingTask


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "level", "correct_option", "is_active")
    list_filter = ("level", "is_active")
    search_fields = ("text",)


@admin.register(WritingTask)
class WritingTaskAdmin(admin.ModelAdmin):
    list_display = ("prompt", "level", "min_words", "is_active")
    list_filter = ("level", "is_active")


class TestAnswerInline(admin.TabularInline):
    model = TestAnswer
    extra = 0
    can_delete = False
    readonly_fields = ("question", "chosen_option", "is_correct", "answered_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(TestSession)
class TestSessionAdmin(admin.ModelAdmin):
    list_display = ("lead", "center", "status", "declared_level", "mc_level", "writing_level", "final_level",
                    "confidence", "needs_review", "started_at")
    list_filter = ("center", "status", "needs_review", "final_level", "confidence")
    search_fields = ("lead__name", "lead__phone")
    readonly_fields = ("center", "lead", "declared_level", "mc_level", "writing_task", "writing_text",
                       "writing_level", "writing_scores", "writing_comment", "started_at", "finished_at")
    fields = readonly_fields + ("status", "final_level", "confidence", "needs_review")
    inlines = [TestAnswerInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Методист поправил итоговый уровень — переносим его в заявку.
        if "final_level" in form.changed_data and obj.final_level:
            obj.lead.assessed_level = obj.final_level
            obj.lead.save(update_fields=["assessed_level", "updated_at"])
