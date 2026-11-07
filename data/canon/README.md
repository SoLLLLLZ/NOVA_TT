# CANON evidence

- [CANON.csv](CANON.csv): 163 configuration records and 18 qualitative lessons (181 rows, 83 columns).
- [CANON_GUIDE.md](CANON_GUIDE.md): interpretation, comparison rules and provenance.
- [CANON_VALIDATION.json](CANON_VALIDATION.json): validation receipt for the published snapshot.
- [qualitative_lessons.json](qualitative_lessons.json): supporting evidence for the lesson rows.

The November 7 campaigns add 15 ByteShape and 20 Glimmer completed-essay observations, plus device-ownership and fixed-seed reproducibility lessons. [ByteShape evidence](experiments/wright-byteshape-industrial-20261107.json) and [Glimmer evidence](experiments/wright-glimmer-industrial-20261107.json) embed native requests/responses and provenance. Read the guide before ranking records. Historical raw-data paths refer to the original research workspace, not this directory; do not rewrite those paths to imply raw files were published here.

Keep generated logs, new unreviewed measurements and retrieval caches in `var/`, not in the curated table. Deployable configuration manifests belong in `configs/profiles/` at repository root.
