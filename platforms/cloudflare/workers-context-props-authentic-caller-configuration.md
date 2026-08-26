# Workers ctx.props Authentic Caller Configuration

**Issue:** `ctx.props` can carry permissions and resource scope across Service Bindings, but confusing deployment-authentic configuration with end-user identity creates an authorization bypass.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Define a schema for each entrypoint's props and declare `WorkerEntrypoint<Env, Props>`; generate current types with `wrangler types`.
- Treat regular Service Binding props as authentic assertions by an actor allowed to edit and deploy the receiving configuration. They do not require an additional signature for authenticity.
- Use props for fixed caller identity, permissions, or resource scoping, then intersect them with current resource policy and any separately authenticated user context.
- Never copy request-controlled JSON directly into an authorization-bearing props object. Validate allowed values and apply least privilege.
- Remember that loopback bindings from `ctx.exports` can set props dynamically because the caller is the same Worker. Audit any such binding passed onward over RPC as a delegated capability.
- Minimize props and avoid secrets even though persistently serializable values may include structured-clonable data and Service Bindings. Context is stateless and is not Durable Object state.

## Verification
- Attempt to escalate a user-supplied permission and confirm it cannot override deployment-defined props.
- Exercise direct Service Binding, `ctx.exports`, and forwarded-binding paths and confirm the same schema and policy intersection apply.
- Check the required `enable_ctx_exports` compatibility flag and generated types in deployment CI.

## Gotchas
Authentic means the platform controls who can set the value; it does not mean every configured permission is safe, current, or appropriate for the end user.

## Official sources
- https://developers.cloudflare.com/workers/runtime-apis/context/
