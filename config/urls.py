"""Root URL configuration for FSP Draft."""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),

    # OpenAPI 3.0 & Swagger UI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # Modular API routes
    path('api/', include('identity.urls')),
    path('api/', include('profiles.urls')),
    path('api/', include('assessment.urls')),
    path('api/', include('matching.urls')),
    path('api/', include('outreach.urls')),
    path('api/', include('fsp_sync.urls')),

    # Mock FSP IdP & Registry (AI-08 / dev / test)
    path('idp/', include('fsp_mock.urls')),
    path('registry/', include('fsp_mock.registry_urls')),
]
