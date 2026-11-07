# Local runtime output

Reserved for local run state, manifests, logs, measurements and caches. Everything here except this README is ignored by Git. Future code may create subdirectories as needed; no runtime state has been created by this scaffold.

Never treat local cache/log contents as safe to publish. Keep secrets in Keychain/backend secret storage, not here. Model weights should remain in the existing remote storage or another external cache.
