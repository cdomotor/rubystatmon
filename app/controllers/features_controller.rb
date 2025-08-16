# File: app/controllers/features_controller.rb
# Path: /app/controllers/features_controller.rb
class FeaturesController < ApplicationController
  # GET /features
  def index
    require "yaml"

    # Load features from YAML file
    features = YAML.load_file(Rails.root.join("config", "features.yml")).symbolize_keys
    @current_features = features[:current] || []
    @planned_features = features[:planned] || []
  end
end
