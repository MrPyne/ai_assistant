def register(app, ctx):
    from . import _shared as shared

    @app.post('/api/node_test')
    def node_test(body: dict):
        return shared.node_test_impl(body)
