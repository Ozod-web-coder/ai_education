from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import BookingViewSet, GroupSearchView

router = SimpleRouter()
router.register("bookings", BookingViewSet, basename="booking")

urlpatterns = [
    path("groups/search/", GroupSearchView.as_view(), name="group-search"),
    *router.urls,
]
