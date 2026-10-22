from django.urls import path

from .views import MyLeadView

urlpatterns = [
    path("lead/", MyLeadView.as_view(), name="my-lead"),
]
