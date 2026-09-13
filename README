# Variant Pipeline

A three-stage batch pipeline that reads variant CSV files, validates and converts them
to JSON, simulates a compute-intensive processing step, and aggregates the results into
a single run summary.

Written for the Identifai Genetics Software Engineering Intern home assessment.

---

## Quick start

Requires Docker only. No Python installation needed.

```bash
git clone https://github.com/davidtom1/variant-pipeline.git
cd variant-pipeline
./run.sh
```

**This takes about 3.5 minutes.** The Process stage sleeps 30 seconds per input file by
design (7 files = 210 seconds), and it produces no output while sleeping. It has not
hung. For a fast run:

```bash
PROCESS_SLEEP_SECONDS=1 ./run.sh
```

`run.sh` is a thin wrapper around `docker compose up --build` that passes your user and
group id into the containers (see *Running as the invoking user* below).

### Expected output

```
data/output/
├── converted/      one JSON per input CSV
├── processed/      one metrics JSON per input
├── history/        timestamped archive of past summaries
└── summary.json    the run summary
```

The pipeline processes whatever `*.csv` files are in `data/input/`, producing one
converted file and one metrics file per input, and a single summary for the run.

As a check that your run matched mine: the seven sample files currently in
`data/input/` produce **162 total variants** and **11 skipped rows** (6 in
`variants_1.csv` and 2 in `variants_5.csv`, all out-of-range positions, plus 3 in
`variants_messy.csv`).

### Running the tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pytest
pytest -q
```

72 test functions, several parametrized. The suite runs in about a second: every test
sets the sleep to zero.

---

## Stages

| Stage | Reads | Writes |
|---|---|---|
| **Convert** | `data/input/*.csv` | `data/output/converted/<name>.json` |
| **Process** | `data/output/converted/*.json` | `data/output/processed/<name>.json` |
| **Aggregate** | `data/output/processed/*.json` | `data/output/summary.json` + archive |

**Convert** parses each CSV, validates every row, skips invalid rows with a logged
warning naming the file, line number and reason, and writes the valid variants plus
counts.

**Process** reads a converted file, sleeps to simulate expensive computation, and writes
a metrics file with timing, the row counts carried through from Convert, and the variant
count per chromosome.

**Aggregate** reads only the metrics files and writes one summary: totals, per-chromosome
counts, and the list of inputs.

### The contract between stages

Convert's output:

```json
{
  "source_file": "variants_messy.csv",
  "rows_read": 6,
  "valid_count": 3,
  "skipped_count": 3,
  "variants": [
    {"index": "chr1:25071832_A/G", "chrom": "chr1", "pos": 25071832, "ref": "A", "alt": "G"}
  ]
}
```

Process's output:

```json
{
  "source_file": "variants_messy.csv",
  "converted_file": "variants_messy.json",
  "started_at": "2026-09-13T10:00:05.320+00:00",
  "ended_at": "2026-09-13T10:00:35.327+00:00",
  "duration_seconds": 30.007,
  "rows_read": 6,
  "valid_count": 3,
  "skipped_count": 3,
  "variants_per_chromosome": {"chr1": 1, "chr2": 1, "chrX": 1}
}
```

`pos` is stored as an integer, not a string: converting it is part of validation, so a
value that cannot become a number is caught there rather than downstream.

---

## Design decisions

### Language and dependencies

**Python, standard library only.** The runtime has no third-party dependencies; pytest
is used for tests and is not installed in the image.

**No pandas**, despite this being CSV work. Pandas would have made the error handling
harder, not easier. A single `not_a_number` in the POS column silently turns the whole
column to strings, and a missing ALT becomes `NaN`, so I would have been working
backwards to find which rows were bad. `csv.DictReader` gives me the row-level warnings
the brief asks for directly, and it keeps the image small.

**No database.** The brief describes file outputs throughout and requires the pipeline to
run with nothing but Docker. The outputs *are* the store. A database would mean another
container, a schema and a connection to configure, for data that is already structured —
and overwriting a file is naturally idempotent, where a database would need upserts and
partial-insert handling. At real scale I would want a metadata store indexing files in
object storage, but that is a scaling answer, not this exercise.

### Validation

Validation lives in its own module (`src/validation.py`) rather than inline in Convert.
That keeps Convert readable — open file, validate rows, write JSON — and lets me test
every rule without touching the filesystem.

The brief does not define what makes a row valid, so these are my rules:

| Field | Valid when |
|---|---|
| `index` | equals `CHROM:POS_REF/ALT` rebuilt from the other four columns, as written |
| `CHROM` | one of `chr1`–`chr22`, `chrX`, `chrY` |
| `POS` | digits only, ≥ 1, and ≤ that chromosome's length in GRCh38 |
| `REF` / `ALT` | one or more of A, C, G, T, uppercase; ALT must differ from REF |

All values are stripped of surrounding whitespace before checking. Any empty value, or
any missing required column, invalidates the row.

**Skip, never repair.** Two of the three bad rows in `variants_messy.csv` look fixable —
the malformed-POS row has a position inside its index, the empty-ALT row has an ALT
inside its index. I deliberately do not use them. When two parts of a row disagree there
is no way to tell which is correct, and in genetics a wrong variant is worse than a
missing one: a wrong one can reach a report, a skipped one is logged and can be
investigated.

**Multi-base REF and ALT are valid.** The data contains `GAAGTC/G`, `ATCG/T` and
`GCAT/A` — real deletions. The pattern is `[ACGT]+`, not `[ACGT]`. A single-base rule
reads correctly and would silently discard three valid rows, which is exactly the failure
mode this domain cares about most.

**Positions are bounds-checked against GRCh38.** This is the decision with the largest
visible effect: it is why 8 rows across `variants_1.csv` and `variants_5.csv` are
skipped. Without it, zero rows would be skipped in those files. `chr3:456789123` is
impossible — chr3 is about 198 million bases long. **This assumes the GRCh38 assembly.**
If the data were aligned to a different build the lengths would need to change; the
lengths are in one dict in `validation.py`.

**Deliberate rejections:** lowercase bases, `N` (an unknown base is not actionable),
`chrM`, and bare chromosome numbers like `7` without the `chr` prefix. None appear in the
sample data; they are defensive.

**Extra columns are tolerated and column order does not matter**, because rows are read
by header name. Real files gain columns over time and rejecting a file for that would be
brittle. A *missing* required column, an empty file, or an unreadable file causes that
file to be skipped with an error — and the rest of the run continues. That is why the
per-file functions return a boolean rather than raising.

### Where the counting happens

Process computes the per-chromosome counts, not Aggregate. This means Aggregate only ever
reads small metrics files and never touches variant data, so its cost grows with the
number of files rather than the number of variants. It matters more at scale than here.

### Timing

Two clocks, because they answer different questions. `started_at` and `ended_at` are
wall-clock UTC timestamps for the report. `duration_seconds` is computed from
`time.monotonic()`, which only ever moves forward, so a clock correction cannot produce a
negative or wrong duration.

**Total processing time is the sum of per-file durations**, not the wall-clock span of the
run. Today they are the same because stages run serially; they diverge the moment work is
parallelised, and the sum is the number that stays meaningful.

### The sleep

Configurable via `PROCESS_SLEEP_SECONDS`, defaulting to 30 as the brief requires. An
environment variable is the natural choice because it works identically locally and in
Docker, and it lets the whole test suite run with the sleep at zero.

A non-numeric or negative value logs a warning and falls back to 30 rather than failing
the run. This is arguable — a config error being loud and fatal is also defensible — but
I would rather a typo not kill a three-minute job.

### Idempotency and crash safety

The brief requires that running twice produces correct results. Three things deliver that:

1. **Overwrite, never append.** Every stage rewrites its output completely.
2. **Aggregate rebuilds from scratch.** It never adds to existing totals, which is the
   obvious way to accidentally double every count.
3. **Atomic writes.** `write_json_atomic` writes to a temporary file *in the same
   directory* as the target, fsyncs it, then `os.replace`s it into position. A rename
   within a filesystem is atomic, so the target filename always holds either the previous
   complete version or the new complete version — never a half-written file that the next
   stage would parse as valid.

The same-directory detail matters in Docker specifically: the output directory is a
mounted volume and `/tmp` is not, and a rename across filesystems is not atomic.

I got an unplanned demonstration of this during development — the VM's disk filled
mid-run and Convert died partway through writing. No corrupt JSON was left behind.

`write_json_atomic` also sets mode 0644 explicitly before the rename. `tempfile.mkstemp`
creates files as 0600 by design, and without the chmod every pipeline output was
owner-only — invisible to a later stage running as a different user.

### The history archive

`summary.json` is overwritten each run. A timestamped copy also goes to
`data/output/history/`, which is an **append-only audit log, deliberately outside the
idempotency contract**: two runs leave two archives, by design. Aggregate writes there
and never reads from it, so it cannot aggregate its own output.

Archive names use `summary_YYYYMMDDTHHMMSS_ffffffZ.json` — compact ISO basic format
because colons are not safe in filenames, and microsecond precision because two runs
within the same second would otherwise overwrite one archive (which they did, in testing).

### The summary states its own coverage

If some metrics files cannot be read, Aggregate still writes a summary from the rest — but
records `metrics_files_failed`. Without that field, `files_processed: 5` looks
authoritative and nothing in the file tells a later reader that two inputs were dropped.
A summary that hides its own incompleteness is worse than one that fails loudly.

### Chromosome ordering

Chromosomes sort in genomic order (chr1, chr2, … chr22, chrX, chrY) rather than
alphabetically, where chr10 would sit between chr1 and chr2. The ordering is derived from
the `CHROM_LENGTHS` dict, which is already declared in genomic order, so there is a single
source of truth. Unknown names sort last, alphabetically, so output stays deterministic
even for a chromosome outside the reference set.

### Output formatting

JSON is written with `indent=2` and a trailing newline. This costs roughly 20–30% in file
size and would be pointless for machine-read data at scale, but these files are small and
being readable during review is worth more.

### Containers

**One image, three services.** The Dockerfile's `CMD` runs Convert; compose overrides the
command per service. Three near-identical Dockerfiles would be duplication.

**Layer ordering.** There are no runtime dependencies today, but the Dockerfile is
ordered so that dependency installation would come before `COPY src/`, so editing code
would not invalidate the dependency layer.

**Non-root.** The image creates `appuser` with a pinned uid.

**Input mounted read-only.** Convert has no business writing to the input directory and
the `:ro` flag enforces that. Process and Aggregate do not mount the input directory at
all — each stage gets only what it needs.

**Stage ordering.** `depends_on` with `condition: service_completed_successfully`. Plain
`depends_on` only waits for a container to *start*, which would let Process begin reading
converted files while Convert was still writing them. This waits for a clean exit, which
is why each stage's `main()` returns a meaningful exit code.

### Running as the invoking user

`compose.yaml` sets `user: "${UID:-1000}:${GID:-1000}"` and `run.sh` supplies those
values. This exists because of a bug that only appeared when I tested the way a reviewer
would — see the AI section below for how I found it.

`data/output/` is tracked in git as an empty directory (via `.gitkeep`, with its contents
gitignored) because Docker creates a missing bind-mount directory **as root**, which a
non-root container then cannot write to.

### Input data

The brief shows `variants_clean.csv` and `variants_messy.csv` and says both must be
processed in the same run, but the provided zip contained `variants_1.csv` through
`variants_5.csv` instead. I recreated the two sample files from the brief and kept all
seven inputs, so the run covers both the supplied data and the specific malformed cases
the brief calls out.

### Line endings

The input CSVs use CRLF line endings. `.gitattributes` explicitly exempts `*.csv` from
normalisation so they stay exactly as supplied — they are test data, and the parser should
prove it handles them. Everything else is normalised to LF.

---

## AI workflow

I used AI throughout, in two distinct roles.

**Claude (chat) as a design reviewer and teaching partner.** This is where most of the
value was. I used it to think through decisions I had not met before — what makes a
variant row valid, how to guarantee idempotency, why `os.replace` is atomic and `mkstemp`
needs a `dir` argument, what `depends_on` actually waits for. The working pattern was:
confirm my understanding of the file I was about to write, have Claude generate a
skeleton of it (imports and function signatures), then write the code myself, consulting
Claude when I ran into trouble. After finishing a file I would ask for a code review. For
areas I was weaker in — parsing, for example — I asked for assistance up front. Every rule in `validation.py`, and the bodies of `convert.py`, `process.py`
and `aggregate.py`, I wrote and debugged myself. The review cycles caught real bugs:
`time.timezone.utc` instead of `timezone.utc`, a nested loop that would have processed
every file seven times, unpacking a single return value into two variables, counters I
had incremented but never initialised.

**Claude Code in VS Code for mechanical work.** The project skeleton, `io_utils.py`, all
five test files, and batches of small fixes applied from an explicit numbered list.
Test-writing is where it earned its place: the cases are repetitive, and once I had
decided the rules, enumerating them as tests is exactly the kind of work worth delegating.

I put a `CLAUDE.md` in the repo root setting the rules for it: never run git, standard
library plus pytest only, implement only what the current prompt asks, ask before creating
files outside the named paths. I added that after Claude Code committed on its own and
wrote a `.claude/settings.json` that pre-approved `git add` and `git commit` — I untracked
that file and took git back under manual control, because the commit history is something
I want to be able to explain line by line.

### Where I had to correct or override the AI

**The permission bug on a clean clone.** This is the most important one. The
containerisation worked on my machine through every test I ran. Then I cloned the repo
into a fresh directory and ran it the way a reviewer would, and Convert died immediately
with `PermissionError: '/app/data/output/converted'`. The cause: `data/output/` was
gitignored, so it does not exist in a clone; Docker creates a missing bind-mount directory
as root; and the container runs as a non-root user. It had worked for me only because that
directory already existed locally, created by me. Neither I nor the AI review caught it
from reading the code, because it is not visible in the code — it is a property of the
environment. The fix was two parts: track the directory (empty) so it exists after
cloning, and run the containers as the invoking user rather than a hardcoded uid. The
lesson I took from it is that AI review is not a substitute for running the thing the way
the next person will run it.

**An AI-written test that asserted the implementation instead of the intent.** A generated
test checked `list(keys) == sorted(keys)` for the per-chromosome counts. That passes, but
it only restates what Python's default sort does — it does not express what I wanted. When
I switched to genomic ordering the test failed, and the correct fix was to the test, not
the code. I replaced it with the explicit expected order, `["chr1", "chr2", "chr10"]`,
which says chr10 comes after chr2 as a deliberate assertion. I have been more careful
since about generated tests that compare against a recomputation rather than a stated
expectation — they pass, they look like coverage, and they verify nothing.

**File permissions in generated code.** `write_json_atomic` was generated and got the hard
parts right, but every file it produced came out mode 0600, because that is what
`tempfile.mkstemp` does and nothing had overridden it. I only noticed by running `ls -ln`
on the container's output. It would have broken the pipeline the moment two stages ran as
different users.

**Scaffolding left in a deliverable.** I committed a Dockerfile that still had the
template's instructional comments in it, including one that referred to the assessment's
own rubric. I cleaned it up in a later commit. Generated scaffolding is written for the
person building the thing, not for the person reading it afterwards.

### What AI is good and bad at, for this kind of work

**Good at:** filling in domain knowledge I simply do not have. I know essentially nothing
about genetics, and the AI is where I learned what REF and ALT mean, why a multi-base REF
represents a deletion, and that chromosome lengths come from a named reference assembly —
which is what led to the bounds check being a deliberate decision rather than something I
never thought of. I am relying on it for that, which is a real dependency: for anything
going to production I would verify the chromosome lengths against an authoritative source
rather than take them on trust.

Also good at: project scaffolding; enumerating repetitive test cases once the rules are
decided; mechanical refactors applied from an explicit list; recalling exact library
semantics (`mkstemp`, `os.replace`, `csv.DictReader`'s behaviour on short rows); and
catching inconsistencies across files that I would have skimmed past — unused imports,
a value computed and then never used, an f-string in a logging call where the rest of the
codebase uses lazy formatting.

**Bad at:** knowing which things are decisions. Asked to write the validation rules, it
will happily pick the reasonable-looking option and move on, and the reasoning — the part
I actually need to be able to defend — never gets written down. It is also bad at anything
that depends on the target environment rather than the source code, which is how the
permission bug survived. And it drifts out of scope unless constrained: it adds files you
did not ask for, expands a small fix into a refactor, and tidies things you were about to
change. Most of what I learned about using it well was about narrowing the request:
name the file, name the change, and say what not to touch.

---

## Known limitations, and what I would do with more time

**Convert builds each file's variants in memory before writing.** For the sample data
that is nothing, but real variant files run to millions of rows. The production version
would stream: Convert appends one variant per line to JSONL as each row validates, so
memory stays constant. The counts cannot go in that file because they are only known at
the end, so they would move to a small companion metadata file per input. I kept the
single self-contained JSON here because it makes the stage contract and the tests
simpler, and because the inputs are 30–53 rows.

**Crash granularity is a whole file.** Atomic writes mean an interrupted run loses the
file it was working on, not a corrupt fragment — but it does lose the whole file. The
real answer is not streaming (a streamed file that survives a crash is silently short,
which is worse) but **chunking**: split a large input into chunks, make each chunk its own
atomic unit, and a crash costs one chunk. That is also what makes the work distributable,
so it is the same change that answers the scaling question.

**Processing is serial.** Seven files at 30 seconds each is 210 seconds, one after
another. This is the honest simulation of a compute-bound step, and parallelising it is
the substance of the cloud-scale design rather than something to bolt on locally.

**`history/` grows without bound.** Nothing prunes it. Production would need a retention
policy.

**Duplicate `source_file` values are not deduplicated.** If two metrics files somehow
carried the same source name, it would appear twice in `input_files` and count twice in
the totals. It cannot happen with the current pipeline, since metrics files are named
after their inputs, but nothing enforces it.

**A duplicate column name in a header is silently collapsed.** `csv.DictReader` keeps only
the last of two identically-named columns. A three-line check would catch it.

**Nothing verifies REF against the actual reference genome.** That would need the ~3 GB
GRCh38 FASTA. "Valid" here means well-formed and plausible, not true.

**`run.sh` assumes a POSIX shell.** A Windows reviewer would need to run `docker compose
up --build` directly with UID and GID set, or accept the 1000 default.

---

## Repository layout

```
src/
  validation.py    row rules and chromosome lengths (GRCh38)
  convert.py       stage 1
  process.py       stage 2
  aggregate.py     stage 3
  io_utils.py      atomic JSON writes, logging setup
  paths.py         all data paths, overridable for tests
tests/             one test file per module
data/input/        the seven input CSVs
Dockerfile         single image for all three stages
compose.yaml       stage ordering, mounts, user mapping
run.sh             one-command entry point
CLAUDE.md          working agreement for the AI tooling
```