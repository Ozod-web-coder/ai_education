from django.db import models

from apps.core.models import Center
from apps.leads.models import Lead


class FaqItem(models.Model):
    """Утверждённая центром база знаний. ИИ отвечает только по ней и по данным центра."""

    class Language(models.TextChoices):
        ANY = "", "Любой"
        RU = "ru", "Русский"
        UZ = "uz", "O'zbekcha"

    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name="faq_items")
    question = models.CharField("вопрос", max_length=300)
    answer = models.TextField("ответ")
    language = models.CharField("язык", max_length=2, choices=Language.choices, blank=True)
    is_active = models.BooleanField("активен", default=True)

    class Meta:
        verbose_name = "вопрос базы знаний"
        verbose_name_plural = "база знаний"

    def __str__(self):
        return self.question


class Conversation(models.Model):
    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name="conversations")
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="conversations")
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "диалог с ИИ"
        verbose_name_plural = "диалоги с ИИ"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.lead} — {self.started_at:%d.%m.%Y %H:%M}"


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", "Ученик"
        ASSISTANT = "assistant", "ИИ"
        TOOL = "tool", "Результат функции"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField(blank=True)
    tool_calls = models.JSONField(null=True, blank=True)
    tool_call_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def as_llm_message(self) -> dict:
        message = {"role": self.role, "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            message["tool_call_id"] = self.tool_call_id
        return message
