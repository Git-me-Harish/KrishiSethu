"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet-draw";
import "leaflet-draw/dist/leaflet.draw.css";
import { MapPin, Trash2, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { GeoJSONPolygon } from "@/lib/api/types";

// Fix Leaflet's default icon paths (broken in webpack)
// We use empty icons since we use custom markers
delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

interface PlotBoundaryEditorProps {
  /** Initial boundary to display (for edit mode) */
  initialBoundary?: GeoJSONPolygon | null;
  /** Initial center point [lat, lon] */
  initialCenter?: [number, number];
  /** Initial zoom level */
  initialZoom?: number;
  /** Called when the user finishes drawing a boundary */
  onBoundaryChange: (boundary: GeoJSONPolygon | null) => void;
  /** Show a search box for locating places */
  enableSearch?: boolean;
}

/**
 * Plot boundary editor using Leaflet + leaflet-draw.
 *
 * Allows the farmer to:
 * 1. Search for their village/location (Phase 2 — uses Nominatim)
 * 2. Pan/zoom to locate their plot
 * 3. Draw a polygon boundary by clicking points on the map
 * 4. Edit the polygon vertices
 * 5. Delete and redraw
 *
 * The drawn boundary is returned as a GeoJSON Polygon in WGS84 (EPSG:4326).
 */
export function PlotBoundaryEditor({
  initialBoundary,
  initialCenter = [20.5937, 78.9629], // Center of India
  initialZoom = 5,
  onBoundaryChange,
  enableSearch = true,
}: PlotBoundaryEditorProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const drawnItemsRef = useRef<L.FeatureGroup | null>(null);
  const [hasBoundary, setHasBoundary] = useState(false);
  const [area, setArea] = useState<number | null>(null);

  // Initialize map
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = L.map(mapContainerRef.current, {
      center: initialCenter,
      zoom: initialZoom,
      scrollWheelZoom: true,
    });

    // OpenStreetMap tiles
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map);

    // ESRI satellite layer (toggle option)
    const satellite = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      {
        attribution: "&copy; Esri, Maxar, Earthstar Geographics",
        maxZoom: 19,
      },
    );

    // Layer control: street vs satellite
    L.control.layers(
      {
        "Street Map": L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"),
        Satellite: satellite,
      },
      undefined,
      { position: "topright" },
    ).addTo(map);

    // Feature group for drawn items
    const drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);
    drawnItemsRef.current = drawnItems;

    // Draw control
    const drawControl = new L.Control.Draw({
      position: "topleft",
      draw: {
        polygon: {
          allowIntersection: false,
          showArea: true,
          shapeOptions: {
            color: "#4CAF50",
            weight: 3,
            fillOpacity: 0.2,
          },
        },
        polyline: false,
        rectangle: false,
        circle: false,
        circlemarker: false,
        marker: false,
      },
      edit: {
        featureGroup: drawnItems,
        edit: true,
        remove: true,
      },
    });
    map.addControl(drawControl);

    // Handle draw:created event
    map.on(L.Draw.Event.CREATED, (event: L.LeafletEvent) => {
      const layer = (event as L.DrawEvents.Created).layer;
      drawnItems.clearLayers(); // Only one polygon at a time
      drawnItems.addLayer(layer);

      const geoJSON = layer.toGeoJSON();
      if (geoJSON.geometry && geoJSON.geometry.type === "Polygon") {
        const polygon = geoJSON.geometry as GeoJSONPolygon;
        // Ensure ring is closed
        const ring = polygon.coordinates[0];
        if (ring.length > 0 && ring[0] !== ring[ring.length - 1]) {
          ring.push(ring[0]);
        }
        onBoundaryChange(polygon);
        setHasBoundary(true);
        // Compute approximate area (Leaflet's showArea uses geodesic math)
        const latlngs = ring.map(([lon, lat]) => L.latLng(lat, lon));
        const computedArea = L.GeometryUtil.geodesicArea(latlngs);
        setArea(computedArea / 10000); // m² to hectares
      }
    });

    // Handle edit: save (after vertex drag)
    map.on(L.Draw.Event.EDITED, (event: L.LeafletEvent) => {
      const layers = (event as L.DrawEvents.Edited).layers;
      layers.eachLayer((layer) => {
        const geoJSON = (layer as L.Polygon).toGeoJSON();
        if (geoJSON.geometry && geoJSON.geometry.type === "Polygon") {
          const polygon = geoJSON.geometry as GeoJSONPolygon;
          const ring = polygon.coordinates[0];
          if (ring.length > 0 && ring[0] !== ring[ring.length - 1]) {
            ring.push(ring[0]);
          }
          onBoundaryChange(polygon);
          const latlngs = ring.map(([lon, lat]) => L.latLng(lat, lon));
          const computedArea = L.GeometryUtil.geodesicArea(latlngs);
          setArea(computedArea / 10000);
        }
      });
    });

    // Handle delete
    map.on(L.Draw.Event.DELETED, () => {
      onBoundaryChange(null);
      setHasBoundary(false);
      setArea(null);
    });

    mapRef.current = map;

    // Load initial boundary if provided
    if (initialBoundary) {
      const geoJSONLayer = L.geoJSON(initialBoundary as unknown as GeoJSON.Feature);
      const layers = geoJSONLayer.getLayers();
      if (layers.length > 0) {
        const layer = layers[0] as L.Polygon;
        drawnItems.addLayer(layer);
        onBoundaryChange(initialBoundary);
        setHasBoundary(true);
        // Fit map to the boundary
        map.fitBounds(layer.getBounds(), { padding: [50, 50] });
        // Compute area
        const latlngs = (layer.getLatLngs()[0] as L.LatLng[]).map((ll) =>
          L.latLng(ll.lat, ll.lng),
        );
        const computedArea = L.GeometryUtil.geodesicArea(latlngs);
        setArea(computedArea / 10000);
      }
    }

    // Cleanup on unmount
    return () => {
      map.remove();
      mapRef.current = null;
      drawnItemsRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleClear = useCallback(() => {
    if (drawnItemsRef.current) {
      drawnItemsRef.current.clearLayers();
      onBoundaryChange(null);
      setHasBoundary(false);
      setArea(null);
    }
  }, [onBoundaryChange]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-slate-700">
          <MapPin className="h-4 w-4" />
          <span>
            {hasBoundary
              ? `Boundary drawn: ${area?.toFixed(2)} hectares`
              : "Click the polygon tool (top-left) to draw your plot boundary"}
          </span>
        </div>
        {hasBoundary && (
          <Button variant="ghost" size="sm" onClick={handleClear}>
            <Trash2 className="h-4 w-4" />
            Clear
          </Button>
        )}
      </div>

      <div
        ref={mapContainerRef}
        className="h-[400px] w-full rounded-md border border-slate-200"
        style={{ zIndex: 0 }}
      />

      <p className="text-xs text-slate-500">
        Tip: Use the layer toggle (top-right) to switch between street map and
        satellite view. Satellite view helps identify your plot boundaries more
        accurately.
      </p>
    </div>
  );
}
