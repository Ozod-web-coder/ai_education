from rest_framework import generics

from apps.core.mixins import CenterScopedMixin
from apps.core.models import Branch
from apps.core.serializers import BranchSerializer

from .models import Course
from .serializers import CourseSerializer


class BranchListView(CenterScopedMixin, generics.ListAPIView):
    serializer_class = BranchSerializer
    pagination_class = None

    def get_queryset(self):
        return Branch.objects.filter(center=self.get_center(), is_active=True)


class CourseListView(CenterScopedMixin, generics.ListAPIView):
    serializer_class = CourseSerializer
    pagination_class = None

    def get_queryset(self):
        return Course.objects.filter(center=self.get_center(), is_active=True)
