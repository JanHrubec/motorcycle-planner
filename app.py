from io import BytesIO

from flask import Flask, jsonify, render_template, request, send_file

from route_planner.gpx import make_gpx
from route_planner.service import RequestError, RouteService, load_graph


def create_app(service: RouteService | None = None) -> Flask:
    app = Flask(__name__)
    if service is None:
        service = RouteService(load_graph())
    app.config["ROUTE_SERVICE"] = service

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/api/routes")
    def routes():
        planner = app.config["ROUTE_SERVICE"]
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise RequestError("Request body must be JSON")
        return jsonify(planner.route(data))

    @app.post("/api/gpx")
    def gpx():
        planner = app.config["ROUTE_SERVICE"]
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise RequestError("Export request must be JSON")
        edge_ids = data.get("edge_ids")
        if not isinstance(edge_ids, list):
            raise RequestError("Export request needs a list of route edges")
        name = str(data.get("name", "motorcycle-route"))[:80]
        coordinates = planner.edges_to_coordinates(edge_ids)
        content = make_gpx(coordinates, name)
        return send_file(
            BytesIO(content),
            mimetype="application/gpx+xml",
            as_attachment=True,
            download_name="motorcycle-route.gpx",
        )

    @app.errorhandler(RequestError)
    def request_error(error: RequestError):
        return jsonify({"error": str(error)}), 400

    return app
