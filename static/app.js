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
        ? `click the map to set ${which}`
        : "choose which point to set";
}

function insideKraj(point) {
    let inside = false;
    for (let i = 0, j = krajBorder.length - 1; i < krajBorder.length; j = i++) {
        const a = krajBorder[i];
        const b = krajBorder[j];
        if ((a[0] > point.lat) !== (b[0] > point.lat) && point.lng < (b[1] - a[1]) * (point.lat - a[0]) / (b[0] - a[0]) + a[1]) {
            inside = !inside;
        }
    }
    return inside;
}

map.on("click", (event) => {
    // ignore map clicks until one of the set buttons is active
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
        <div class="stats">
            <div class="stat"><b>${stats.distance_km} km</b><span>Distance</span></div>
            <div class="stat"><b>${stats.eta_minutes} min</b><span>ETA</span></div>
            <div class="stat"><b>+${stats.detour_percent}%</b><span>Detour</span></div>
            <div class="stat"><b>${stats.twistiness}</b><span>Bends</span></div>
            <div class="stat"><b>${stats.hilliness}</b><span>Hills</span></div>
            <div class="stat"><b>${stats.elevation_gain_m} m</b><span>Climb</span></div>
            <div class="stat"><b>${stats.major_road_percent}%</b><span>Major roads</span></div>
            <div class="stat"><b>${stats.town_road_percent}%</b><span>Town roads</span></div>
        </div>
        <div class="card-actions"><button class="export-button" type="button">GPX</button></div>`;
    card.addEventListener("click", () => setActiveRoute(index));
    card.querySelector("button").addEventListener("click", async (event) => {
        event.stopPropagation();
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
    const answer = [];
    const lines = text.trim().split(/\r?\n/);
    for (const line of lines.slice(2)) {
        if (line.trim() === "END") break;
        const bits = line.trim().split(/\s+/).map(Number);
        if (bits.length === 2) answer.push([bits[1], bits[0]]);
    }
    return answer;
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
        // cover everything outside the supported region
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
