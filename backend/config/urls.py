from django.urls import include, path, re_path
from django.views.generic import TemplateView

urlpatterns = [
    path("api/", include("routing.urls")),
    # Everything else is handled by the React single-page app.
    re_path(r"^(?!api/|static/).*$", TemplateView.as_view(template_name="index.html")),
]
