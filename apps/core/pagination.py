from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

class FSPPagination(PageNumberPagination):
    page_size = 20
    max_page_size = 100
    page_size_query_param = 'page_size'

    def get_page_size(self, request):
        if 'size' in request.query_params and 'page_size' not in request.query_params:
            try:
                size = int(request.query_params['size'])
                if size > 0:
                    return min(size, self.max_page_size)
            except (ValueError, TypeError):
                pass
        return super().get_page_size(request)

    def get_paginated_response(self, data):
        return Response({
            'items': data,
            'total': self.page.paginator.count,
            'page': self.page.number,
            'pages': self.page.paginator.num_pages
        })
