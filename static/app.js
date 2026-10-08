const colors = [
    "#d96732", "#416a4b", "#5967a6", "#8b5c8e",
    "#b28a35", "#2f7b78", "#8a5448"
];
const map = L.map("map", { zoomControl: true, maxBoundsViscosity: 1 });
const mapTiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    noWrap: true,
    attribution: "&copy; OpenStreetMap contributors"
});

let startPoint = null;
let targetPoint = null;
let startMarker = null;
let targetMarker = null;
let routeLayers = [];
let pickMode = null;
let krajBorder = [];

const byId = (id) => document.getElementById(id);

function showError(message) {
    byId("errorBox").textContent = message;
    byId("errorBox").classList.remove("hidden");
}

function clearError() {
    byId("errorBox").classList.add("hidden");
}

function pointText(point) {
    return point ? `${point.lat.toFixed(5)}, ${point.lng.toFixed(5)}` : "Not selected";
}

function updatePointLabels() {
    byId("startText").textContent = pointText(startPoint);
    byId("targetText").textContent = pointText(targetPoint);
}

function clearRoutes() {
    routeLayers.forEach((layer) => layer.remove());
    routeLayers = [];
    byId("routeCards").replaceChildren();
}

function clearAll() {
    startPoint = null;
    targetPoint = null;
    if (startMarker) startMarker.remove();
    if (targetMarker) targetMarker.remove();
    startMarker = null;
    targetMarker = null;
    clearRoutes();
    clearError();
    updatePointLabels();
    choosePoint(null);
}

function choosePoint(which) {
    pickMode = which;
    byId("startPick").classList.toggle("active", which === "start");
    byId("targetPick").classList.toggle("active", which === "target");
    byId("map").classList.toggle("picking", which !== null);
    byId("mapHelp").textContent = which
        ? `Click the map to set ${which === "start" ? "the start" : "the destination"}`
        : "Click Set to choose a start or destination";
}

function insideKraj(point) {
    // each crossing flips inside/outside
    let inside = false;
    for (let i = 0, j = krajBorder.length - 1; i < krajBorder.length; j = i++) {
        const a = krajBorder[i];
        const b = krajBorder[j];
        const crossesLatitude = (a[0] > point.lat) !== (b[0] > point.lat);
        if (!crossesLatitude) continue;
        const crossingLongitude = (b[1] - a[1]) *
            (point.lat - a[0]) / (b[0] - a[0]) + a[1];
        if (point.lng < crossingLongitude) {
            inside = !inside;
        }
    }
    return inside;
}

map.on("click", (event) => {
    if (!pickMode) return;
    if (!insideKraj(event.latlng)) {
        showError("Choose a point inside Kraj Vysočina.");
        return;
    }

    clearError();
    clearRoutes();
    if (pickMode === "start") {
        startPoint = event.latlng;
        if (startMarker) startMarker.remove();
        startMarker = L.circleMarker(startPoint, {
            radius: 7, color: "#fff", weight: 2,
            fillColor: "#304f3a", fillOpacity: 1
        }).addTo(map);
    } else {
        targetPoint = event.latlng;
        if (targetMarker) targetMarker.remove();
        targetMarker = L.circleMarker(targetPoint, {
            radius: 7, color: "#fff", weight: 2,
            fillColor: "#d96732", fillOpacity: 1
        }).addTo(map);
    }
    choosePoint(null);
    updatePointLabels();
});

function setActiveRoute(index) {
    routeLayers.forEach((layer, layerIndex) => {
        layer.setStyle({
            weight: layerIndex === index ? 7 : 4,
            opacity: layerIndex === index ? 0.95 : 0.55
        });
        if (layerIndex === index) layer.bringToFront();
    });
    document.querySelectorAll(".route-card").forEach((card, cardIndex) => {
        card.classList.toggle("active", cardIndex === index);
    });
}

async function exportRoute(route) {
    const response = await fetch("/api/gpx", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ edge_ids: route.edge_ids })
    });
    if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || "GPX export failed");
    }
    // temporary link for the download
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "motorcycle-route.gpx";
    link.click();
    URL.revokeObjectURL(link.href);
}

function addRouteCard(route, index) {
    const stats = route.stats;
    const card = document.createElement("article");
    card.className = "route-card";
    card.style.setProperty("--route-color", colors[index % colors.length]);
    card.innerHTML = `
        <h3 class="route-title">Route ${index + 1}${index === 0 ? " (fastest)" : ""}</h3>
        <table class="stats" aria-label="Route ${index + 1} details">
            <tbody>
                <tr><th scope="row">Distance</th><td>${stats.distance_km} km</td></tr>
                <tr><th scope="row">Estimated time</th><td>${stats.eta_minutes} min</td></tr>
                <tr><th scope="row">Extra time</th><td>+${stats.detour_percent}%</td></tr>
                <tr><th scope="row">Bends</th><td>${stats.twistiness}</td></tr>
                <tr><th scope="row">Hills</th><td>${stats.hilliness}</td></tr>
                <tr><th scope="row">Climb</th><td>${stats.elevation_gain_m} m</td></tr>
                <tr><th scope="row">Major roads</th><td>${stats.major_road_percent}%</td></tr>
                <tr><th scope="row">Town roads</th><td>${stats.town_road_percent}%</td></tr>
            </tbody>
        </table>
        <div class="card-actions">
            <button class="select-button" type="button">Show on map</button>
            <button class="export-button" type="button">Download GPX</button>
        </div>`;
    card.addEventListener("click", () => setActiveRoute(index));
    card.querySelector(".select-button").addEventListener("click", () => setActiveRoute(index));
    card.querySelector(".export-button").addEventListener("click", async (event) => {
        event.stopPropagation(); // export without selecting the card
        try {
            await exportRoute(route);
        } catch (error) {
            showError(error.message);
        }
    });
    byId("routeCards").append(card);
}

function drawResults(data) {
    clearRoutes();
    data.routes.forEach((route, index) => {
        const layer = L.polyline(route.coordinates, {
            color: colors[index % colors.length], weight: 4, opacity: 0.65
        }).addTo(map);
        routeLayers.push(layer);
        addRouteCard(route, index);
    });
    if (routeLayers.length) {
        map.fitBounds(L.featureGroup(routeLayers).getBounds(), { padding: [30, 30] });
        setActiveRoute(0);
    }
}

byId("routeForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    if (!startPoint || !targetPoint) {
        showError("Choose both a start and destination on the map.");
        return;
    }
    const button = byId("generateButton");
    button.disabled = true;
    button.textContent = "Searching…";
    try {
        const response = await fetch("/api/routes", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                start: { lat: startPoint.lat, lon: startPoint.lng },
                target: { lat: targetPoint.lat, lon: targetPoint.lng },
                detour_percent: Number(byId("detour").value),
                curve_preference: Number(byId("curve").value),
                hill_preference: Number(byId("hill").value),
                road_preference: Number(byId("road").value),
                town_preference: Number(byId("town").value),
                avoid_motorways: byId("motorways").checked
            })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Route search failed");
        drawResults(data);
    } catch (error) {
        showError(error.message);
    } finally {
        button.disabled = false;
        button.textContent = "Find routes";
    }
});

byId("clearButton").addEventListener("click", clearAll);
byId("startPick").onclick = () => choosePoint(pickMode === "start" ? null : "start");
byId("targetPick").onclick = () => choosePoint(pickMode === "target" ? null : "target");

document.querySelectorAll('input[type="range"]').forEach((slider) => {
    slider.oninput = function () {
        const ending = slider.id === "detour" ? "%" : "";
        byId(`${slider.id}Output`).textContent = slider.value + ending;
    };
});

function readPoly(text) {
    const coordinates = [];
    const lines = text.trim().split(/\r?\n/);
    for (const line of lines.slice(2)) {
        if (line.trim() === "END") break;
        const values = line.trim().split(/\s+/).map(Number);
        // swap longitude and latitude
        if (values.length === 2) coordinates.push([values[1], values[0]]);
    }
    return coordinates;
}

fetch("/static/vysocina.poly")
    .then((response) => response.text())
    .then((polyText) => {
        krajBorder = readPoly(polyText);
        const supported = L.latLngBounds(krajBorder);
        mapTiles.options.bounds = supported;
        mapTiles.addTo(map);
        map.setMaxBounds(supported);
        map.fitBounds(supported, { padding: [10, 10] });
        map.setMinZoom(map.getZoom());

        const world = [[-90, -180], [-90, 180], [90, 180], [90, -180]];
        // hide the map outside the region
        L.polygon([world, krajBorder], {
            stroke: false,
            fillColor: "#f4f3ee",
            fillOpacity: 1,
            fillRule: "evenodd",
            interactive: false
        }).addTo(map);
        L.polyline(krajBorder, { color: "#304f3a", weight: 2, interactive: false }).addTo(map);
    })
    .catch(() => {
        mapTiles.addTo(map);
        map.setView([49.4, 15.6], 10);
        showError("The graph information could not be loaded.");
    });
