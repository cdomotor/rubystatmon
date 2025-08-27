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
  get  "stations/import",           to: "stations_imports#new",      as: :import_stations,  constraints: ->(r){ defined?(StationsImportsController) }
  post "stations/import_preview",   to: "stations_imports#preview",  as: :import_preview_stations, constraints: ->(r){ defined?(StationsImportsController) }
  post "stations/import_commit",    to: "stations_imports#commit",   as: :import_commit_stations,  constraints: ->(r){ defined?(StationsImportsController) }

  # Stations
  resources :stations do
    collection do
      post :import
    end
    member do
      post  :ping
      patch :toggle_active
    end
  end

  # Daemon logs placeholder
  get "daemon_logs", to: "daemon_logs#index", as: :daemon_logs

  # Features (static-style)
  get "features", to: "features#index", as: :features
end
