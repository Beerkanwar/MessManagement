"""
Pagination classes for standard API listing endpoints.
Enforces default 50 items and maximum 200 items cap per ImplementationGuide Phase 1.
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPageNumberPagination(PageNumberPagination):
    """
    Standard pagination class used across all resource list endpoints.
    Default page size: 50. Max page size: 200.
    """
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data):
        return Response({
            "count": self.page.paginator.count,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "results": data,
        })
