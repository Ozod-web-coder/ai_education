from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.utils import timezone


class Language(models.TextChoices):
    RU = "ru", "Русский"
    UZ = "uz", "O'zbekcha"
    EN = "en", "English"


class Center(models.Model):
    """Учебный центр — клиент SaaS. Все данные привязаны к центру."""

    name = models.CharField("название", max_length=200)
    slug = models.SlugField("код", unique=True)
    bot_token = models.CharField(
        "токен Telegram-бота",
        max_length=100,
        blank=True,
        help_text="Нужен для проверки initData из Mini App этого центра.",
    )
    admin_phone = models.CharField(
        "телефон администрации",
        max_length=32,
        blank=True,
        help_text="Показывается ученику в уведомлении, если администратор отметил отказ от записи.",
    )
    default_language = models.CharField(
        "язык по умолчанию", max_length=2, choices=Language.choices, default=Language.RU
    )
    is_active = models.BooleanField("активен", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "учебный центр"
        verbose_name_plural = "учебные центры"

    def __str__(self):
        return self.name


class Branch(models.Model):
    center = models.ForeignKey(Center, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField("название", max_length=200)
    address = models.CharField("адрес", max_length=300, blank=True)
    is_active = models.BooleanField("активен", default=True)

    class Meta:
        verbose_name = "филиал"
        verbose_name_plural = "филиалы"

    def __str__(self):
        return f"{self.center} — {self.name}"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, username, password, **extra_fields):
        if not username:
            raise ValueError("Нужен username")
        user = self.model(username=self.model.normalize_username(username), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(username, password, **extra_fields)

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(username, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Аккаунт: ученик/родитель из Telegram или сотрудник центра.

    Фамилию и email не храним намеренно. Имя ученика — в Lead.name:
    аккаунтом может пользоваться родитель.
    """

    username = models.CharField(
        "логин", max_length=150, unique=True, validators=[UnicodeUsernameValidator()]
    )
    first_name = models.CharField("имя в профиле", max_length=150, blank=True)
    telegram_id = models.BigIntegerField(unique=True, null=True, blank=True)
    telegram_username = models.CharField("username в Telegram", max_length=32, blank=True)
    phone = models.CharField(
        "телефон", max_length=20, blank=True, help_text="Подтверждён кнопкой «Отправить номер» в Telegram."
    )
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.RU)
    center = models.ForeignKey(
        Center,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff",
        help_text="Только для сотрудников центра. У учеников пусто.",
    )
    is_staff = models.BooleanField("сотрудник (доступ в админку)", default=False)
    is_active = models.BooleanField("активен", default=True)
    date_joined = models.DateTimeField("дата регистрации", default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"

    def get_full_name(self):
        return self.first_name or self.username

    def get_short_name(self):
        return self.get_full_name()
