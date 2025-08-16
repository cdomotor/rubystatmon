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

  # Stations
  resources :stations do
    collection do
      post :import
      # future: get :export, delete :bulk_destroy, etc.
    end
    member do
      post :ping
      # future: get :status, put :reboot, etc.
    end
  end

  # Features (static-style)
  get "features", to: "features#index", as: :features
end
