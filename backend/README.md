# Backend

Owner: Taeho. Future implementation code goes in `src/`; agent instructions live in [prompts/OPTIMIZER_AGENT.md](prompts/OPTIMIZER_AGENT.md).

Implement the [v2 API contract](../docs/api/endpoint.md): CANON retrieval, OpenRouter calls, capability/profile resolution, private Wright execution, measurements, run state, repair and rollback. Read evidence from `data/canon/` relative to the repository root, and resolve paths from application configuration rather than assuming the shell working directory.

Model/runtime profile definitions belong in [configs/profiles](../configs/profiles/). Slurm and remote launch helpers belong in [deploy/wright](../deploy/wright/). Local outputs belong in [var](../var/). Credentials stay outside source control.

No backend framework, dependency manifest or runnable server has been added yet. Add package setup and real run commands here when implementing.
