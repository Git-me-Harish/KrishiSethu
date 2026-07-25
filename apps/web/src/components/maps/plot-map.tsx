"use client";

import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { GeoJSONPolygon } from "@/lib/api/types";

// Fix Leaflet's default icon paths
delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

interface PlotMapProps {
  boundary: GeoJSONPolygon;
  centroid?: { lon: number; lat: number } | null;
  /** NDVI overlay (Phase 2) */
  ndviRasterUrl?: string | null;
  /** Color for the polygon stroke */
  strokeColor?: string;
  height?: string;
}

/**
 * Read-only map showing a plot boundary.
 *
 * Used on the plot detail page. In Phase 2, this will also overlay NDVI
 * raster tiles to show vegetation health within the boundary.
 */
export function PlotMap({
  boundary,
  centroid,
  ndviRasterUrl,
  strokeColor = "#4CAF50",
  height = "400px",
}: PlotMapProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = L.map(mapContainerRef.current, {
      scrollWheelZoom: true,
    });

    // Street map (default)
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map);

    // Satellite layer (toggle)
    const satellite = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      {
        attribution: "&copy; Esri, Maxar, Earthstar Geographics",
        maxZoom: 19,
      },
    );

    L.control.layers(
      {
        "Street Map": L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"),
        Satellite: satellite,
      },
      undefined,
      { position: "topright" },
    ).addTo(map);

    // Add plot boundary
    const geoJSONLayer = L.geoJSON(boundary as unknown as GeoJSON.Feature, {
      style: {
        color: strokeColor,
        weight: 3,
        fillOpacity: 0.2,
      },
    }).addTo(map);

    // Fit map to boundary
    const bounds = geoJSONLayer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [50, 50] });
    } else if (centroid) {
      map.setView([centroid.lat, centroid.lon], 15);
    } else {
      map.setView([20.5937, 78.9629], 5); // Center of India
    }

    // Add NDVI raster overlay (Phase 2)
    if (ndviRasterUrl) {
      L.imageOverlay(ndviRasterUrl, bounds, { opacity: 0.6 }).addTo(map);
    }

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [boundary, centroid, ndviRasterUrl, strokeColor]);

  return (
    <div
      ref={mapContainerRef}
      className="w-full rounded-md border border-slate-200"
      style={{ height, zIndex: 0 }}
    />
  );
}
