from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from apps.catalog.serializers import GroupCardSerializer
from apps.core.exceptions import Conflict
from apps.core.mixins import CenterScopedMixin
from apps.leads.models import Lead

from . import services
from .models import Booking
from .serializers import BookingCreateSerializer, BookingSerializer, GroupSearchQuerySerializer


def _to_api_error(exc: services.BookingError):
    if isinstance(exc, services.GroupNotFound):
        return NotFound(str(exc))
    return Conflict(str(exc))


class GroupSearchView(CenterScopedMixin, generics.GenericAPIView):
    """До 3 групп со свободными местами и ближайшим пробным уроком в выбранные дни и время суток."""

    serializer_class = GroupCardSerializer

    @extend_schema(parameters=[GroupSearchQuerySerializer], responses=GroupCardSerializer(many=True))
    def get(self, request, *args, **kwargs):
        query = GroupSearchQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        groups = services.find_matching_groups(
            self.get_center(),
            level=params["level"],
            weekdays=params["days"],
            period=params["period"],
            branch=params.get("branch"),
            age=params.get("age"),
        )
        return Response(GroupCardSerializer(groups, many=True).data)


class BookingViewSet(CenterScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = BookingSerializer
    pagination_class = None

    def get_queryset(self):
        return (
            Booking.objects.filter(center=self.get_center(), lead__user=self.request.user)
            .select_related("group__course", "group__branch")
            .prefetch_related("group__slots")
        )

    def get_lead(self) -> Lead:
        lead = Lead.objects.filter(center=self.get_center(), user=self.request.user).first()
        if lead is None:
            raise ValidationError("Сначала заполните анкету.")
        return lead

    @extend_schema(request=BookingCreateSerializer, responses={201: BookingSerializer})
    def create(self, request, *args, **kwargs):
        payload = BookingCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        lead = self.get_lead()
        data = payload.validated_data
        try:
            if data["waitlist"]:
                booking = services.join_waitlist(lead=lead, group_id=data["group"])
            else:
                booking = services.create_hold(lead=lead, group_id=data["group"], trial_at=data.get("trial_at"))
        except services.BookingError as exc:
            raise _to_api_error(exc) from exc
        return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=BookingSerializer)
    @action(detail=True, methods=["post"])
    def confirm(self, request, *args, **kwargs):
        try:
            booking = services.confirm_booking(self.get_object())
        except services.BookingError as exc:
            raise _to_api_error(exc) from exc
        return Response(BookingSerializer(self.get_queryset().get(pk=booking.pk)).data)

    @extend_schema(request=None, responses=BookingSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        booking = services.cancel_booking(self.get_object())
        return Response(BookingSerializer(self.get_queryset().get(pk=booking.pk)).data)
