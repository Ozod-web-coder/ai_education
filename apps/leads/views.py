from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.core.mixins import CenterScopedMixin

from .models import Lead
from .serializers import LeadSerializer


class MyLeadView(CenterScopedMixin, generics.GenericAPIView):
    """Анкета текущего пользователя в этом центре.

    GET — получить, PUT/PATCH — создать или обновить (поля можно присылать частями).
    """

    serializer_class = LeadSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "center": self.get_center()}

    def get_lead(self):
        return Lead.objects.filter(center=self.get_center(), user=self.request.user).first()

    def get(self, request, *args, **kwargs):
        lead = self.get_lead()
        if lead is None:
            raise NotFound("Анкета ещё не заполнена.")
        return Response(self.get_serializer(lead).data)

    def put(self, request, *args, **kwargs):
        lead = self.get_lead()
        serializer = self.get_serializer(lead, data=request.data, partial=lead is not None)
        serializer.is_valid(raise_exception=True)
        if lead is None:
            serializer.save(center=self.get_center(), user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        serializer.save()
        return Response(serializer.data)

    patch = put
