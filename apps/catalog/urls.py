from django.urls import path

from .views import BranchListView, CourseListView

urlpatterns = [
    path("branches/", BranchListView.as_view(), name="branch-list"),
    path("courses/", CourseListView.as_view(), name="course-list"),
]
