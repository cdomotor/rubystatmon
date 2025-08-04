# File: config/routes.rb
Rails.application.routes.draw do
  root 'dashboard#index' # sets Dashboard as entry point
  get '/dashboard', to: 'dashboard#index' # sets Dashboard as entry point
  resources :stations do
    collection do
      post :import  # creates import_stations_path
    end

    member do      
      post :ping # creates ping_stations_path
    end
  end
end

