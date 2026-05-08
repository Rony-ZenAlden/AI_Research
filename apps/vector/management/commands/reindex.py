"""Re-chunk and re-embed every Document.

Run after swapping the embedder model or chunker, since old chunks are stored
in a different vector space (or with different boundaries) and would mix
poorly with new ones.

Usage:
    docker compose exec web python manage.py reindex
    docker compose exec web python manage.py reindex --owner rony@neuroseek.ai
    docker compose exec web python manage.py reindex --dry-run
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.vector.models import Chunk, Document
from apps.vector.services.chunker import chunk_text
from apps.vector.services.embedder import embedding_service


class Command(BaseCommand):
    help = "Re-chunk + re-embed all Documents (or one user's). Skips docs without raw_text."

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner",
            help="Only reindex docs owned by this user (email). Default: all users.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would happen, change nothing.",
        )

    def handle(self, *args, **opts):
        qs = Document.objects.exclude(raw_text="").exclude(raw_text__isnull=True).order_by("id")
        if opts["owner"]:
            qs = qs.filter(owner__email=opts["owner"])
        total = qs.count()
        if total == 0:
            self.stdout.write("No documents with raw_text to reindex.")
            return

        self.stdout.write(self.style.NOTICE(
            f"Re-indexing {total} document(s) using model={embedding_service.model_name} dim={embedding_service.dimension}"
        ))
        if opts["dry_run"]:
            self.stdout.write("(dry-run — no changes will be persisted)")

        succeeded, skipped, failed = 0, 0, 0
        for i, doc in enumerate(qs.iterator(), start=1):
            try:
                pieces = chunk_text(doc.raw_text)
                if not pieces:
                    self.stdout.write(self.style.WARNING(
                        f"  [{i}/{total}] doc {doc.id}: no chunks produced — skipped"
                    ))
                    skipped += 1
                    continue

                if opts["dry_run"]:
                    self.stdout.write(
                        f"  [{i}/{total}] doc {doc.id} {doc.title[:60]!r:60s}  → would write {len(pieces)} chunks"
                    )
                    succeeded += 1
                    continue

                vectors = embedding_service.embed_documents(pieces)
                with transaction.atomic():
                    Chunk.objects.filter(document=doc).delete()
                    Chunk.objects.bulk_create([
                        Chunk(
                            document=doc,
                            position=p,
                            text=t,
                            char_count=len(t),
                            embedding=v,
                        )
                        for p, (t, v) in enumerate(zip(pieces, vectors))
                    ])
                    doc.status = Document.STATUS_READY
                    doc.error_message = ""
                    doc.save(update_fields=["status", "error_message", "updated_at"])

                self.stdout.write(
                    f"  [{i}/{total}] doc {doc.id} {doc.title[:60]!r:60s}  → {len(pieces)} chunks"
                )
                succeeded += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f"  [{i}/{total}] doc {doc.id}: {e}"
                ))
                failed += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Done. succeeded={succeeded} skipped={skipped} failed={failed}"
        ))
