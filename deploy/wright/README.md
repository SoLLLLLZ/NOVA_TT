# Wright deployment

Reserved for future Slurm job templates, allocation checks and private model-service launch helpers. No runnable deployment is included yet.

Use the [API resource contract](../../docs/api/endpoint.md) and [model requirements](../../docs/demo/DEMO_MODELS.md). Respect the live Slurm allocation/device mask; no inference on the headnode. Reuse staged models and the pinned compatible runtime/library bundles. Credentials and SSH control sockets stay outside the repository.

Add real deployment commands and dependencies when implemented. Files in this folder must distinguish preparation, allocation, launch and cleanup so selecting a profile does not accidentally start unrelated work.
