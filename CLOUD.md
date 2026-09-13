# Part 2 — Cloud scale sketch

**Assumptions.** Input CSVs arrive in S3 rather than a local directory, and intermediate
output lives there too. Each stage becomes a job handling **one file**, with the fan-out
moved into the scheduler instead of the `for` loop currently inside each stage. Aggregate
stays a single job, since it only reads small metrics files. The 30-second sleep stands in
for genuinely compute-bound work, so the constraint is CPU time, not I/O.

## Services

**S3** for all data, with input, converted and metrics files under separate prefixes.
Two things follow. There is no shared local disk between jobs, which is what forces the
per-file job model above. And S3 uploads are already atomic — an object appears complete
or not at all — so the temp-file-and-rename mechanism in `write_json_atomic` becomes
unnecessary and I would drop it rather than carry it.

**AWS Batch** (on Fargate) to run the containerised stages, with the image in **ECR**.
The stages are run-to-completion container jobs, which is what Batch is for: it takes a
queue of jobs, scales compute up to work through them, and scales back down when the queue
drains. No file depends on any other, so throughput becomes a function of how many jobs
run concurrently rather than of the number of files. Serially, 1,000 files at 30 seconds
each is over 8 hours; at 100 concurrent jobs it is roughly 5 minutes.

Stage ordering uses **Batch job dependencies** — each Process job depends on its own
Convert job, and Aggregate depends on all Process jobs completing. That is the same
guarantee as `condition: service_completed_successfully` in the compose file, and it keeps
the design to two services. Step Functions would be the answer if the workflow grew beyond
a linear three stages, but not on day one.

The code is already close to this shape: `convert_file` and `process_file` each handle a
single file and return success or failure, with a thin directory loop on top. Moving to
Batch replaces the loop with the scheduler; the stage logic does not change.

## What could go wrong

**Partial failure producing a summary that looks complete.** At thousands of files some
will fail — a truncated upload, a worker reclaimed mid-job, a transient S3 error — and
Aggregate would build a summary from 9,997 of 10,000 files with nothing in the output
saying so. A number quietly 0.03% short is more dangerous than a run that fails outright,
because it gets used. The pipeline already records `metrics_files_failed` for this reason;
at scale I would make it enforceable and fail the run when the failure rate crosses a
threshold, after bounded retries for the transient cases.

## What I would monitor

**Files landed in the input prefix versus files with a successful metrics object**,
alarmed when the gap persists beyond the expected processing window. One number, and it
catches the failures that do not announce themselves: dropped files, stuck jobs, a stage
that silently stopped being scheduled. I would also watch the skipped-row rate, currently
around 6%, as a data-quality signal — if it jumped to 60% nothing would crash, but
something upstream would have changed.
