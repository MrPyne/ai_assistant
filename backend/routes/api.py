def register(app, ctx):
    # re-use original api_routes implementation by delegating to it
    from .. import api_routes as orig
    return orig.register(app, ctx)
