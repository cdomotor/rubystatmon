# File: config/routes.rb
# Path: /config/routes.rb
Rails.application.routes.draw do
  # Entry point
  root "dashboard#index"

  # Dashboard + JSON-ish metrics
  get "dashboard", to: "dashboard#index"
  namespace :dashboard do
    get  "metrics/latency",                 to: "metrics#latency"
    get  "metrics/health",                  to: "metrics#health"
    get  "metrics/stations/:id/latency24h", to: "metrics#station_latency_24h", as: :station_latency_24h
    post "spotlight/:id/mark_reviewed",     to: "spotlight#mark_reviewed",     as: :mark_reviewed
  end

  # --- CSV Import (declare BEFORE resources :stations to avoid /stations/:id capture) ---
  get  "stations/import",           to: "stations_imports#new",      as: :import_stations
  post "stations/import_preview",   to: "stations_imports#preview",  as: :import_preview_stations
  post "stations/import_commit",    to: "stations_imports#commit",   as: :import_commit_stations
  get  "stations/import_template",  to: "stations_imports#template", as: :import_template_stations

  # Stations (single declaration)
  resources :stations, constraints: { id: /\d+/ } do
    collection do
      # (keep space for future: get :export, delete :bulk_destroy, etc.)
    end
    member do
      post :ping
      # future: get :status, put :reboot, etc.
    end
  end

  # Features (static-style)
  get "features", to: "features#index", as: :features

  # Daemon log viewer
  get  "daemon_logs",          to: "daemon_logs#show",     as: :daemon_logs
  get  "daemon_logs/stream",   to: "daemon_logs#stream",   as: :daemon_logs_stream
  get  "daemon_logs/download", to: "daemon_logs#download", as: :daemon_logs_download
end
