// File: app/javascript/station_charts.js
// Full path: /app/javascript/station_charts.js

// This module renders the Battery and Parameter charts on the Station show page.
// It uses Chart.js + chartjs-plugin-zoom. It also paints a "low voltage" band.

import {
  Chart,
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  TimeSeriesScale,
  TimeScale,
  Title,
  Tooltip,
  Legend,
  Filler,
  CategoryScale
} from "chart.js";
import zoomPlugin from "chartjs-plugin-zoom";

// If you use Luxon/Adapter for time parsing, pin and import it too (importmap step below)
// But Chart.js 4 allows string timestamps; we’ll keep it simple.

Chart.register(
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  TimeScale,
  TimeSeriesScale,
  Title,
  Tooltip,
  Legend,
  Filler,
  CategoryScale,
  zoomPlugin
);

// Helper to get JSON data embedded in the view
function readJson(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  try {
    return JSON.parse(el.textContent);
  } catch {
    return null;
  }
}

// Custom plugin to shade below a threshold (e.g., low battery)
const lowBandPlugin = {
  id: "lowBandPlugin",
  beforeDraw(chart, args, opts) {
    const { ctx, chartArea, scales } = chart;
    if (!chartArea || !scales?.y) return;

    const yLow = opts?.low; // numeric value
    if (typeof yLow !== "number") return;

    const yLowPx = scales.y.getPixelForValue(yLow);
    const bottom = chartArea.bottom;
    const top = Math.min(Math.max(yLowPx, chartArea.top), chartArea.bottom);

    ctx.save();
    ctx.fillStyle = "rgba(255, 99, 132, 0.08)"; // subtle red tint
    ctx.fillRect(chartArea.left, top, chartArea.right - chartArea.left, bottom - top);
    ctx.restore();
  }
};

Chart.register(lowBandPlugin);

// Render battery chart
function renderBatteryChart() {
  const canvas = document.getElementById("batteryChart");
  if (!canvas) return;

  const pairs = readJson("battery-data-json") || [];
  const thresholds = readJson("battery-thresholds-json") || { low: null };

  const labels = pairs.map(p => p[0]); // timestamps
  const values = pairs.map(p => p[1]); // numeric

  new Chart(canvas.getContext("2d"), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Battery Voltage (V)",
          data: values,
          borderWidth: 2,
          tension: 0.25,
          pointRadius: 0,
          fill: false
        }
      ]
    },
    options: {
      maintainAspectRatio: false,
      responsive: true,
      parsing: false,
      scales: {
        x: {
          type: "time",
          time: { tooltipFormat: "yyyy-MM-dd HH:mm" },
          ticks: { autoSkip: true, maxTicksLimit: 8 }
        },
        y: {
          beginAtZero: false,
          title: { display: true, text: "Volts" }
        }
      },
      plugins: {
        legend: { display: true },
        tooltip: { mode: "index", intersect: false },
        zoom: {
          zoom: {
            wheel: { enabled: true },
            pinch: { enabled: true },
            mode: "x"
          },
          pan: {
            enabled: true,
            mode: "x"
          },
          limits: {
            x: { min: "original", max: "original" },
            y: { min: "original", max: "original" }
          }
        },
        lowBandPlugin: {
          low: typeof thresholds.low === "number" ? thresholds.low : null
        }
      },
      interaction: { mode: "nearest", intersect: false }
    }
  });
}

// Render multi-series param chart
function renderParamChart() {
  const canvas = document.getElementById("paramsChart");
  if (!canvas) return;

  const paramHash = readJson("params-data-json") || {};
  const paramNames = Object.keys(paramHash);

  const datasets = paramNames.map((name, i) => {
    const pairs = paramHash[name] || [];
    return {
      label: name,
      data: pairs.map(p => ({ x: p[0], y: p[1] })),
      borderWidth: 2,
      tension: 0.25,
      pointRadius: 0,
      fill: false
    };
  });

  new Chart(canvas.getContext("2d"), {
    type: "line",
    data: { datasets },
    options: {
      maintainAspectRatio: false,
      responsive: true,
      parsing: false,
      scales: {
        x: {
          type: "time",
          time: { tooltipFormat: "yyyy-MM-dd HH:mm" },
          ticks: { autoSkip: true, maxTicksLimit: 8 }
        },
        y: {
          beginAtZero: false,
          title: { display: true, text: "Value" }
        }
      },
      plugins: {
        legend: { display: true },
        tooltip: { mode: "index", intersect: false },
        zoom: {
          zoom: {
            wheel: { enabled: true },
            pinch: { enabled: true },
            mode: "x"
          },
          pan: {
            enabled: true,
            mode: "x"
          },
          limits: {
            x: { min: "original", max: "original" },
            y: { min: "original", max: "original" }
          }
        }
      },
      interaction: { mode: "nearest", intersect: false }
    }
  });
}

// Init
document.addEventListener("DOMContentLoaded", () => {
  renderBatteryChart();
  renderParamChart();
});
// Ensure the charts are rendered after the DOM is fully loaded
// This is important to ensure the canvas elements are available    