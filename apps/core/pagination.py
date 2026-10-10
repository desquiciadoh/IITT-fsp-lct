from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class PaginationQuerySerializer(serializers.Serializer):
    """Validates pagination query params: page >= 1, 1 <= size <= 100 (R18)."""

    page = serializers.IntegerField(required=False, default=1, min_value=1)
    size = serializers.IntegerField(required=False, default=20, min_value=1, max_value=100)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)

    def validate(self, attrs):
        if "size" not in attrs and "page_size" in attrs:
            attrs["size"] = attrs["page_size"]
        elif "size" not in attrs:
            attrs["size"] = 20
        return attrs


class FSPPagination(PageNumberPagination):
    page_size = 20
    max_page_size = 100
    page_size_query_param = "page_size"

    def get_page_size(self, request):
        if "size" in request.query_params and "page_size" not in request.query_params:
            try:
                size = int(request.query_params["size"])
                if size > 0:
                    return min(size, self.max_page_size)
            except (ValueError, TypeError):
                pass
        return super().get_page_size(request)

    def get_paginated_response(self, data):
        return Response(
            {
                "items": data,
                "total": self.page.paginator.count,
                "page": self.page.number,
                "pages": self.page.paginator.num_pages,
            }
        )
