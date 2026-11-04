import L from "leaflet";
import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";

import { formatDayTime } from "../format";
import { riskStyle } from "../risk";
import type { Heatmap, HeatmapCell } from "../types";

const PANE = "heatmap";
const LOW_OPACITY = 0.08;
const RISK_OPACITY = 0.45;

interface Props {
  heatmap: Heatmap;
  hour: number; // integer hour offset from departure
  visible: boolean;
}

/**
 * Corridor weather heatmap drawn on its own canvas pane.
 *
 * Rectangles are created once per plan; moving the slider only restyles them
 * (no React re-render, no DOM churn), which keeps scrubbing at 60 fps even
 * with a few hundred cells.
 */
export function HeatmapLayer({ heatmap, hour, visible }: Props) {
  const map = useMap();
  const groupRef = useRef<L.LayerGroup | null>(null);
  const cellsRef = useRef<L.Rectangle[]>([]);
  const hourRef = useRef(hour);

  useEffect(() => {
    if (!map.getPane(PANE)) {
      const pane = map.createPane(PANE);
      pane.style.zIndex = "350"; // below routes (overlayPane = 400)
    }
    const renderer = L.canvas({ pane: PANE, padding: 0.5 });
    const { dlat, dlon } = heatmap;
    const group = L.layerGroup();
    cellsRef.current = heatmap.cells.map((cell) => {
      const rect = L.rectangle(
        [
          [cell.lat - dlat / 2, cell.lon - dlon / 2],
          [cell.lat + dlat / 2, cell.lon + dlon / 2],
        ],
        { renderer, pane: PANE, stroke: false, fillOpacity: 0, interactive: true },
      );
      rect.bindTooltip(() => tooltip(cell, hourRef.current, heatmap.start), { sticky: true, className: "cell-tip" });
      group.addLayer(rect);
      return rect;
    });
    groupRef.current = group;
    paint(cellsRef.current, heatmap.cells, hourRef.current);
    return () => {
      group.remove();
      groupRef.current = null;
    };
  }, [heatmap, map]);

  useEffect(() => {
    hourRef.current = hour;
    paint(cellsRef.current, heatmap.cells, hour);
  }, [hour, heatmap]);

  useEffect(() => {
    const group = groupRef.current;
    if (!group) return;
    if (visible) group.addTo(map);
    else group.remove();
  }, [visible, map, heatmap]);

  return null;
}

function paint(rects: L.Rectangle[], cells: HeatmapCell[], hour: number) {
  for (let i = 0; i < rects.length; i++) {
    const level = Number(cells[i].levels[hour] ?? 0);
    rects[i].setStyle({ fillColor: riskStyle(level).color, fillOpacity: level === 0 ? LOW_OPACITY : RISK_OPACITY });
  }
}

function tooltip(cell: HeatmapCell, hour: number, start: string): string {
  const level = Number(cell.levels[hour] ?? 0);
  const when = new Date(new Date(start).getTime() + hour * 3600_000);
  const s = riskStyle(level);
  return `
    <div class="tip-title">${formatDayTime(when)} <span class="tip-badge" style="background:${s.color};color:${s.text}">${s.label}</span></div>
    <div>Wind <b>${cell.wind[hour]} mph</b> · Rain <b>${cell.rain[hour].toFixed(2)}"/h</b> · Snow <b>${cell.snow[hour].toFixed(2)}"/h</b></div>`;
}
