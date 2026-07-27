from app.widgets.geomap import render


def context(state):
    return {"country_paths": render.country_paths()}
