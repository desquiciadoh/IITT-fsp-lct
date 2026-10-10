"""FSP Mock IdP URLs."""

from django.urls import path

from fsp_mock import views

urlpatterns = [
    path(
        "realms/fsp/.well-known/openid-configuration",
        views.OidcDiscoveryView.as_view(),
        name="oidc-discovery",
    ),
    path(
        ".well-known/openid-configuration",
        views.OidcDiscoveryView.as_view(),
        name="oidc-discovery-root",
    ),
    path(
        "realms/fsp/protocol/openid-connect/certs", views.OidcJwksView.as_view(), name="oidc-jwks"
    ),
    path(
        "realms/fsp/protocol/openid-connect/auth",
        views.OidcAuthorizeView.as_view(),
        name="oidc-authorize",
    ),
    path(
        "realms/fsp/protocol/openid-connect/token", views.OidcTokenView.as_view(), name="oidc-token"
    ),
    path(
        "realms/fsp/protocol/openid-connect/userinfo",
        views.OidcUserinfoView.as_view(),
        name="oidc-userinfo",
    ),
]
