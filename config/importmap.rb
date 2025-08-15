# File: config/importmap.rb
# Full path: /config/importmap.rb

# --- Core app entrypoint ---
pin "application"

# --- Turbo (Hotwire) ---
# If you already have this pinned, keep your existing line; this is safe.
pin "@hotwired/turbo-rails", to: "turbo.min.js", preload: true

# --- Stimulus controllers (optional; safe even if none exist) ---
pin_all_from "app/javascript/controllers", under: "controllers"

# --- Charting stack ---
# Chart.js core (UMD)
pin "chart.js", to: "https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.js"

# Time scale adapter (date-fns bundle); required for time-series axes
pin "chartjs-adapter-date-fns", to: "https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"

# Zoom & pan plugin
pin "chartjs-plugin-zoom", to: "https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.umd.js"

# --- Local modules ---
# Our station charts module (lives in /app/javascript/station_charts.js)
pin "station_charts", to: "station_charts.js"
