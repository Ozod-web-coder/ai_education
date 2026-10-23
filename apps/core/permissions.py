from rest_framework.permissions import BasePermission


class IsCenterStaff(BasePermission):
    """Сотрудник этого центра (или суперпользователь).

    Вью должна наследовать CenterScopedMixin: центр берётся из URL.
    Сотрудником становятся в админке Django: is_staff + поле «центр» + telegram_id.
    """

    message = "Нет доступа: вы не сотрудник этого центра."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active and user.is_staff):
            return False
        if user.is_superuser:
            return True
        return user.center_id == view.get_center().id
