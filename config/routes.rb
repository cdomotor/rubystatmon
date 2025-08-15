# File: config/routes.rb
Rails.application.routes.draw do
  root 'dashboard#index' # sets Dashboard as entry point
  
  get 'dashboard', to: 'dashboard#index'
  namespace :dashboard do
    get  'metrics/latency',                         to: 'metrics#latency'
    get  'metrics/health',                          to: 'metrics#health'
    get  'metrics/stations/:id/latency24h',         to: 'metrics#station_latency_24h', as: :station_latency_24h
    post 'spotlight/:id/mark_reviewed',             to: 'spotlight#mark_reviewed',     as: :mark_reviewed
  end

  resources :stations do
    collection do
      post :import  # creates import_stations_path
    end
    member do      
      post :ping # creates ping_stations_path
    end
  end

end