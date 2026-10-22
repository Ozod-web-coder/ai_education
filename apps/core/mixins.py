from django.shortcuts import get_object_or_404

from .models import Center


class CenterScopedMixin:
    """Для вью под /api/c/<center_slug>/: достаёт центр из URL."""

    def get_center(self) -> Center:
        if not hasattr(self, "_center"):
            self._center = get_object_or_404(Center, slug=self.kwargs["center_slug"], is_active=True)
        return self._center
