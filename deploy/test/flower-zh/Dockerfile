# Flower(Celery 实时监控)+ flower-i18n-zh 中文界面补丁
# broker 由 compose 的 command 用 --broker 注入;监控依赖 worker 的 -E 事件(已开启)
# redis:kombu 连接 redis broker 所需的驱动(flower 默认不装)
FROM python:3.12-slim
RUN pip install --no-cache-dir flower flower-i18n redis \
    && flower-i18n-patch
EXPOSE 5555
CMD ["celery", "flower", "--address=0.0.0.0", "--port=5555"]
