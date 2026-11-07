# Wright worker

`worker.py` is a standard-library-only private command worker deployed by the backend into a unique owner-only directory below `/home/export/taeholee/nova/backend-runs/`. The backend submits one Slurm job, then the job runs the worker through `srun`. Commands use a private append-only inbox over the existing SSH connection. Result readers wait for complete JSON; stable files and direct reads avoid shared-filesystem directory-cache delays. Raw launch and response artifacts are saved atomically. Model servers bind only to compute-node loopback.

The worker verifies target and runtime hashes, allocation GPU UUIDs, CPU assignment, free memory, and service settings. A one-second monitor enforces 1 GiB minimum GPU headroom (or the caller's higher floor) and an 80°C stop threshold. It terminates only its own process groups. Slurm lifetime is an additional hard bound.

Do not launch this worker on the login node or by direct SSH to a compute node. See `backend/README.md` for API launch and opt-in ByteShape rehearsal commands.
