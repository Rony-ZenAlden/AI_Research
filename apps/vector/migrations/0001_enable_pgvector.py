"""Enable the pgvector PostgreSQL extension before any model uses VectorField.

Runs as the first migration in the vector app; the auto-generated 0002 (created
by `makemigrations vector`) will depend on this and create the actual tables.
"""
from django.db import migrations


class Migration(migrations.Migration):
    initial = True
    dependencies: list = []
    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS vector;",
            reverse_sql="DROP EXTENSION IF EXISTS vector;",
        ),
    ]
