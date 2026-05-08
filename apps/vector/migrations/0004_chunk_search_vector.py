"""Add a Postgres-managed tsvector column for keyword search.

We use a GENERATED column so we never have to maintain it from app code —
Postgres recomputes the tsvector whenever ``text`` changes. A GIN index on top
makes ``@@`` queries fast.

``state_operations`` tells Django the field exists in the schema state, so
later ``makemigrations`` runs don't try to add a duplicate column.
"""
from django.contrib.postgres.search import SearchVectorField
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("vector_store", "0003_document_error_message_document_file_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE vector_chunk "
                "ADD COLUMN IF NOT EXISTS search_vector tsvector "
                "GENERATED ALWAYS AS (to_tsvector('english', coalesce(text, ''))) STORED;"
                "CREATE INDEX IF NOT EXISTS vector_chunk_search_gin "
                "ON vector_chunk USING GIN(search_vector);"
            ),
            reverse_sql=(
                "DROP INDEX IF EXISTS vector_chunk_search_gin;"
                "ALTER TABLE vector_chunk DROP COLUMN IF EXISTS search_vector;"
            ),
            state_operations=[
                migrations.AddField(
                    model_name="chunk",
                    name="search_vector",
                    field=SearchVectorField(editable=False, null=True),
                ),
            ],
        ),
    ]
