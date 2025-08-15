# File: db/migrate/20250809_add_configured_parameters_to_stations.rb
# Full path: /db/migrate/20250809_add_configured_parameters_to_stations.rb

class AddConfiguredParametersToStations < ActiveRecord::Migration[7.1]
  def change
    # Store as JSON string in SQLite (or JSON in Postgres). Default to [].
    add_column :stations, :configured_parameters, :text, null: false, default: "[]"
  end
end
