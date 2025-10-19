def register(app, ctx):
    # Delegate to smaller route modules for improved organization.
    # Each module registers related endpoints when called.
    from . import api_common
    from . import secrets as secrets_mod
    from . import providers as providers_mod
    from . import workflows as workflows_mod
    from . import webhooks as webhooks_mod
    from . import audit as audit_mod

    # call each register function; they will use ctx to access shared state
    secrets_mod.register(app, ctx)
    providers_mod.register(app, ctx)
    workflows_mod.register(app, ctx)
    webhooks_mod.register(app, ctx)
    audit_mod.register(app, ctx)
    return None
