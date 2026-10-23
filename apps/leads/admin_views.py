from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.core.mixins import CenterScopedMixin
from apps.core.permissions import IsCenterStaff

from .admin_serializers import BEFORE_CONFIRMATION, AdminLeadDetailSerializer, AdminLeadSerializer
from .duplicates import duplicate_map
from .models import Lead
from .services import decline_lead


class LeadPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class AdminLeadViewSet(
    CenterScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Заявки центра для администратора (Telegram Mini App).

    Доступ: сотрудник этого центра. Менять можно статус, заметку, курс, имя и телефон.
    """

    permission_classes = [IsCenterStaff]
    pagination_class = LeadPagination
    http_method_names = ["get", "patch", "post", "delete", "head", "options"]

    def get_serializer_class(self):
        return AdminLeadSerializer if self.action == "list" else AdminLeadDetailSerializer

    def get_serializer_context(self):
        context = {**super().get_serializer_context(), "center": self.get_center()}
        if self.action != "stats":
            context["duplicates"] = duplicate_map(self.get_center())
        return context

    def get_queryset(self):
        queryset = (
            Lead.objects.filter(center=self.get_center())
            .select_related("user", "desired_course")
            .prefetch_related("bookings__group__course", "bookings__group__branch")
            .order_by("-created_at")
        )
        if self.action != "list":
            return queryset

        params = self.request.query_params
        if search := params.get("search", "").strip():
            queryset = queryset.filter(id__in=self._search_ids(search))
        if statuses := [s for s in params.get("status", "").split(",") if s]:
            queryset = queryset.filter(status__in=statuses)
        if course := params.get("course"):
            if course.isdigit():
                queryset = queryset.filter(Q(desired_course_id=course) | Q(bookings__group__course_id=course)).distinct()
        return queryset

    def _search_ids(self, search: str) -> list[int]:
        """Регистронезависимый поиск по имени, телефону и @username.

        Делаем в Python: на SQLite (БД по умолчанию) icontains не различает регистр у кириллицы,
        поэтому «алиш» не нашло бы «Алишер». Для центра на тысячи заявок это быстро.
        """
        needle = search.casefold()
        tg_needle = needle.lstrip("@")
        rows = Lead.objects.filter(center=self.get_center()).values_list("id", "name", "phone", "user__telegram_username")
        return [
            lead_id
            for lead_id, name, phone, username in rows
            if needle in (name or "").casefold()
            or needle in (phone or "")
            or (tg_needle and tg_needle in (username or "").casefold())
        ]

    def update(self, request, *args, **kwargs):
        self.student_notification = None
        response = super().update(request, *args, **kwargs)
        if self.student_notification is not None:
            response.data["student_notification"] = self.student_notification
        return response

    def perform_update(self, serializer):
        was_declined = serializer.instance.status == Lead.Status.DECLINED
        lead = serializer.save()
        # Уведомляем один раз при переходе в «Отказался», а не при каждом сохранении заявки.
        if lead.status == Lead.Status.DECLINED and not was_declined:
            self.student_notification = decline_lead(lead)

    @extend_schema(
        parameters=[
            OpenApiParameter("search", str, description="Имя, телефон или @username"),
            OpenApiParameter("status", str, description="Статусы через запятую"),
            OpenApiParameter("course", int, description="id курса"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=None, responses=AdminLeadDetailSerializer)
    @action(detail=True, methods=["post"])
    def confirm(self, request, *args, **kwargs):
        """Администратор связался с учеником: ставит «Подтверждена» и время связи."""
        lead = self.get_object()
        if not lead.contacted_at:
            lead.contacted_at = timezone.now()
        if lead.status in BEFORE_CONFIRMATION:
            lead.status = Lead.Status.CONFIRMED
        lead.save(update_fields=["contacted_at", "status", "updated_at"])
        return Response(self.get_serializer(lead).data)

    @extend_schema(responses={200: dict})
    @action(detail=False, methods=["get"])
    def stats(self, request, *args, **kwargs):
        """Сколько заявок в каждом статусе — для счётчиков в фильтре."""
        rows = Lead.objects.filter(center=self.get_center()).values("status").annotate(n=Count("id"))
        counts = {row["status"]: row["n"] for row in rows}
        return Response({"total": sum(counts.values()), "by_status": counts})
