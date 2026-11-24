"""Guards a class of outage: a router registered without being imported.

Adding `app.include_router(quote_profiles.router)` without the matching import raised NameError at
module load, so the API would not start at all — a total outage. Importing the app is the strongest
form of this test: if any registered name is missing, this file fails instead of production.
"""


def test_the_app_imports_and_exposes_the_new_routes():
    import app.main

    assert app.main.app is not None
    # openapi() flattens included routers; app.routes keeps them nested in this FastAPI version.
    paths = set(app.main.app.openapi()["paths"])
    assert not [p for p in paths if "/owner/designs" in p or "/owner/quote-profiles" in p], "3D/designs routes must stay removed"
