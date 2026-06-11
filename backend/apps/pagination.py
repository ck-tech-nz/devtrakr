from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """全局默认分页:支持客户端 page_size 参数(原生 PageNumberPagination 会静默忽略)。

    看板视图等场景需要用大 page_size 全量拉取,max_page_size 防止恶意/失控的超大请求。
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200
