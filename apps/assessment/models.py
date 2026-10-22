from django.core.exceptions import ValidationError
from django.db import models

from apps.catalog.models import Level
from apps.core.models import Center
from apps.leads.models import Lead


class Question(models.Model):
    """Вопрос с вариантами ответа. Общий банк для всех центров."""

    level = models.CharField("уровень", max_length=2, choices=Level.choices)
    text = models.TextField("вопрос")
    options = models.JSONField("варианты", help_text='Список строк, например ["am", "is", "are", "be"]')
    correct_option = models.PositiveSmallIntegerField("номер верного варианта (с 0)")
    is_active = models.BooleanField("активен", default=True)

    class Meta:
        verbose_name = "вопрос теста"
        verbose_name_plural = "вопросы теста"

    def __str__(self):
        return f"[{self.level}] {self.text[:60]}"

    def clean(self):
        if not isinstance(self.options, list) or not 2 <= len(self.options) <= 6:
            raise ValidationError({"options": "Нужно от 2 до 6 вариантов."})
        if self.correct_option >= len(self.options):
            raise ValidationError({"correct_option": "Номер верного варианта вне списка."})


class WritingTask(models.Model):
    """Письменное задание для уровней B1 и выше. Оценивает ИИ, итог сводит бэкенд."""

    level = models.CharField("уровень", max_length=2, choices=Level.choices)
    prompt = models.TextField("задание (на английском)")
    min_words = models.PositiveSmallIntegerField("минимум слов", default=60)
    is_active = models.BooleanField("активно", default=True)

    class Meta:
        verbose_name = "письменное задание"
        verbose_name_plural = "письменные задания"

    def __str__(self):
        return f"[{self.level}] {self.prompt[:60]}"


class TestSession(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "Идёт тест"
        WRITING = "writing", "Ждём письменный ответ"
        COMPLETED = "completed", "Завершён"
        ABANDONED = "abandoned", "Брошен"

    class Confidence(models.TextChoices):
        HIGH = "high", "Высокая"
        MEDIUM = "medium", "Средняя"
        LOW = "low", "Низкая"

    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name="test_sessions")
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="test_sessions")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    declared_level = models.CharField("уровень со слов", max_length=2, choices=Level.choices, blank=True)
    current_question = models.ForeignKey(
        Question, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    mc_level = models.CharField("уровень по тесту", max_length=2, choices=Level.choices, blank=True)

    writing_task = models.ForeignKey(WritingTask, on_delete=models.SET_NULL, null=True, blank=True)
    writing_text = models.TextField("письменный ответ", blank=True)
    writing_level = models.CharField("уровень письма (ИИ)", max_length=2, choices=Level.choices, blank=True)
    writing_scores = models.JSONField("оценки письма (ИИ)", null=True, blank=True)
    writing_comment = models.TextField("комментарий ИИ", blank=True)

    final_level = models.CharField("итоговый уровень", max_length=2, choices=Level.choices, blank=True)
    confidence = models.CharField("уверенность", max_length=10, choices=Confidence.choices, blank=True)
    needs_review = models.BooleanField("нужна проверка методиста", default=False)

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "прохождение теста"
        verbose_name_plural = "прохождения теста"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.lead} — {self.final_level or self.get_status_display()}"


class TestAnswer(models.Model):
    session = models.ForeignKey(TestSession, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="+")
    chosen_option = models.PositiveSmallIntegerField()
    is_correct = models.BooleanField()
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["session", "question"], name="one_answer_per_question"),
        ]
