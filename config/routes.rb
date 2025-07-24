Rails.application.routes.draw do
  devise_for :users

  namespace :api do
    resources :stations, only: [:index, :show] do
      post 'ping', on: :member
    end
  end

  namespace :admin do
    resources :stations do
      collection do
        post 'import'
      end
    end
  end

  root to: 'admin/stations#index'
end
