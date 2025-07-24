# File: config/routes.rb

Rails.application.routes.draw do
  root "stations#index"

  resources :stations do
    collection { post :import }
  end
end
