from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """全局默认分页:支持客户端 page_size 参数(原生 PageNumberPagination 会静默忽略)。

    调用方按需覆盖每页条数(如看板每列 20 条续取),max_page_size 防止恶意/失控的
    超大请求(超过上限时 DRF 静默截断到 200,全量拉取必须跟随 next 链接翻页)。
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200
