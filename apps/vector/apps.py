from django.apps import AppConfig


class VectorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.vector"
    label = "vector_store"  # avoid clashing with the SQL `vector` extension name
    verbose_name = "Vector Store"
