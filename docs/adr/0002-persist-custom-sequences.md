# Persist custom chord sequences in SQLite, with a frozen snapshot for the six built-ins

The search-by-sequence feature only knew six progressions, hardcoded in `main.py` as a
dict of tag-to-id (`sequencias`) and matched against a precomputed `SEQ_FAMOSA` column in
`data/top/dataset_final.csv` rather than against the songs' actual chord lists. A visitor
could not add a seventh progression, a new one required a new deploy, and there was no
database at all — the CSV was the entire state. The task (see
`docs/features/sequencias-customizadas/00-enunciado.md`) requires an open, anonymous
catalog that survives container restarts, with the six existing sequences still producing
the same search results.

The first thing we checked was whether the tag column and a real-time sliding-window match
over `musica.cifra` agree, because if they did, the tag could simply be deleted. They do
not. For all six sequences the tagged set is a strict subset of what the sliding window
finds — 199 vs. 866 songs for `Bm,G,D,A`, 4 vs. 3,110 for `Em,G`, and so on (the
measurement and the script to reproduce it are in
`docs/features/sequencias-customizadas/01-research.md` and `02-proposal.md`).
`SEQ_FAMOSA` is a curation of the dataset, not a definition of "the song contains this
progression", so switching to real-time matching would visibly change the results of the
six sequences the task freezes as the regression criterion.

We decided to introduce a SQLite database, using the `sqlite3` module that already ships
with Python 3.9, holding two things: the ordered chord list of every sequence
(`sequencias`) and the set of songs each sequence matches (`sequencia_matches`). The
sequence rule itself is the sliding window from the research: a sequence appears in a song
iff its ordered chord list is a contiguous subsequence of `musica.cifra`, compared
case-sensitively, with no notation synonyms (`C7M` is not `Cmaj7`). Matches are computed
once, at write time, and reads become a lookup instead of a scan over ~67k songs. To
honour the frozen regression criterion, the six built-in sequences are seeded at bootstrap
with the exact song set their `SEQ_FAMOSA` tag produces today; only sequences created by
visitors go through the window at `POST` time. The catalog — not songs or genres — is what
moved to the database; the CSV is still loaded into memory at startup and remains the
source of truth for the music catalog.

SQLite was chosen over the alternatives for the reasons in the research: it adds no
dependency to the `Dockerfile`, it gives us real transactions under gunicorn (which a JSON
file or TinyDB would not), and it fits the single-container, local-only deployment from
ADR 0001 without introducing a database server. The database file lives at
`DECIFRAME_DB` (default `/app/var/deciframe.db`) and `/app/var` is the volume that must be
mounted: mounting `/app/data` instead would shadow `data/top/dataset_final.csv`, because
the Dockerfile does `COPY . .`, and the app would fail to boot.

The cost of this decision is that `sequencia_matches` is derived, persisted state, and the
six built-in rows are stale by design — they reflect the dataset's curation, not what the
window would find. If the CSV changes, the seeds have to be re-created (bootstrap inserts
only what is missing, it does not recompute); there is no recompute endpoint, and adding
one would need a policy for invalidating rows. Unifying the six built-ins with real-time
matching is a separate, visible behaviour change and deserves its own ADR, with the
product owner accepting the larger result sets. Until then, the two provenances coexist
behind one read path, and the regression test asserts equality, not containment, for the
six sequences. The catalog is open and anonymous, so the write path also validates input
(2–16 chords, known chord vocabulary, duplicate signature rejected, catalog capped at
1,000 sequences) — rate limiting remains out of reach in a single local container and is
left as a known gap.
