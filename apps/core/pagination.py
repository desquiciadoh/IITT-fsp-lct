from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

class FSPPagination(PageNumberPagination):
    page_size = 20
    max_page_size = 100
    page_size_query_param = 'page_size'

    def get_paginated_response(self, data):
        return Response({
            'items': data,
            'total': self.page.paginator.count,
            'page': self.page.number,
            'pages': self.page.paginator.num_pages
        })
