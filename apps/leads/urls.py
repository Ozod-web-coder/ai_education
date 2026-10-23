from django.urls import path
from rest_framework.routers import SimpleRouter

from .admin_views import AdminLeadViewSet
from .views import MyLeadView

router = SimpleRouter()
router.register("admin/leads", AdminLeadViewSet, basename="admin-lead")

urlpatterns = [
    path("lead/", MyLeadView.as_view(), name="my-lead"),
    *router.urls,
]
